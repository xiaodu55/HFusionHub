from zipfile import ZipFile

from app.core.parser.base import BlockType, ParsedBlock
from app.core.parser.multimodal_evidence import MultimodalEvidenceExtractor
from app.core.rag.query_router import ChannelType, QueryRouter, SearchResult


def _extractor(**overrides):
    options = {
        "enabled": True,
        "ocr_enabled": True,
        "ocr_command": "tesseract",
        "ocr_language": "eng",
        "max_images_per_document": 2,
        "max_image_bytes": 1024,
        "max_ocr_characters": 32,
        "ocr_timeout_seconds": 3,
    }
    options.update(overrides)
    return MultimodalEvidenceExtractor(**options)


def _docx_with_images(path, images):
    with ZipFile(path, "w") as archive:
        for name, content in images:
            archive.writestr(f"word/media/{name}", content)


def test_disabled_multimodal_leaves_parser_blocks_unmodified(tmp_path):
    blocks = [ParsedBlock("a table", BlockType.TABLE, metadata={"rows": 1})]

    enriched, report = _extractor(enabled=False).enrich(str(tmp_path / "any.docx"), "docx", blocks)

    assert enriched == blocks
    assert "multimodal" not in blocks[0].metadata
    assert report.to_dict() == {
        "enabled": False,
        "table_blocks": 0,
        "image_candidates": 0,
        "image_blocks": 0,
        "ocr_characters": 0,
        "vlm_blocks": 0,
        "skipped": {},
    }


def test_native_tables_and_docx_ocr_become_source_backed_blocks(tmp_path, monkeypatch):
    source = tmp_path / "report.docx"
    _docx_with_images(source, [("diagram.png", b"image-bytes")])
    extractor = _extractor()
    monkeypatch.setattr(extractor, "_ocr_available", lambda: True)
    monkeypatch.setattr(extractor, "_ocr", lambda image, suffix: ("Quarterly revenue: 42", None))
    table = ParsedBlock("| Quarter | Revenue |\n| Q1 | 42 |", BlockType.TABLE, metadata={"rows": 1})

    enriched, report = extractor.enrich(str(source), "docx", [table])

    assert enriched[0].metadata["multimodal"] == {"kind": "table", "extraction": "native"}
    assert "multimodal" not in table.metadata
    image = enriched[1]
    assert image.block_type == BlockType.IMAGE
    assert "Quarterly revenue: 42" in image.content
    assert image.metadata["multimodal"]["source_file_type"] == "docx"
    assert image.metadata["multimodal"]["image_part"] == "word/media/diagram.png"
    assert len(image.metadata["multimodal"]["image_sha256"]) == 64
    assert report.to_dict()["image_blocks"] == 1
    assert report.to_dict()["ocr_characters"] == len("Quarterly revenue: 42")


def test_ocr_unavailable_safely_preserves_text_and_reports_reason(tmp_path, monkeypatch):
    source = tmp_path / "report.docx"
    _docx_with_images(source, [("diagram.png", b"image-bytes")])
    extractor = _extractor()
    monkeypatch.setattr(extractor, "_ocr_available", lambda: False)

    enriched, report = extractor.enrich(str(source), "docx", [ParsedBlock("text", BlockType.PARAGRAPH)])

    assert [item.content for item in enriched] == ["text"]
    assert report.to_dict()["skipped"] == {"ocr_unavailable": 1}


def test_image_limits_and_ocr_output_limits_are_enforced(tmp_path, monkeypatch):
    source = tmp_path / "report.docx"
    _docx_with_images(source, [("first.png", b"a"), ("second.png", b"b"), ("third.png", b"c")])
    extractor = _extractor(max_images_per_document=2, max_ocr_characters=4)
    monkeypatch.setattr(extractor, "_ocr_available", lambda: True)
    monkeypatch.setattr(extractor, "_ocr", lambda image, suffix: ("abcdef", None))

    enriched, report = extractor.enrich(str(source), "docx", [])

    assert [item.content for item in enriched] == ["[Image OCR]\nabcd", "[Image OCR]\nabcd"]
    assert report.to_dict()["skipped"] == {"image_limit": 1}


def test_debug_candidates_include_multimodal_source_metadata():
    router = QueryRouter(channels={})
    candidates = router._debug_candidates({
        ChannelType.VECTOR: [SearchResult(
            content="[Image OCR] quarterly revenue",
            score=0.9,
            source=ChannelType.VECTOR,
            document_id="doc-1",
            metadata={
                "chunk_id": "doc-1_chunk_0001",
                "knowledge_base_id": 1,
                "multimodal": {"kind": "image_ocr", "page_number": 2},
            },
        )],
    })

    assert candidates["vector"][0]["multimodal"] == {"kind": "image_ocr", "page_number": 2}


# ── P8 vision-LLM 路线（2026-08-29）：VLM 优先、OCR 兜底 ──────────────────


def test_vlm_caption_takes_priority_over_ocr(tmp_path, monkeypatch):
    source = tmp_path / "report.docx"
    _docx_with_images(source, [("chart.png", b"chart-bytes")])
    extractor = _extractor(
        vlm_enabled=True,
        vlm_model="qwen2.5vl:3b",
        vlm_base_url="http://localhost:11434",
    )
    monkeypatch.setattr(extractor, "_ocr_available", lambda: True)
    monkeypatch.setattr(extractor, "_ocr", lambda image, suffix: ("should not be used", None))
    monkeypatch.setattr(
        extractor, "_vlm_caption",
        lambda image: ("图表显示 2026 年 Q1 营收为 42 万", None),
    )

    enriched, report = extractor.enrich(str(source), "docx", [])

    image = enriched[-1]
    assert image.content.startswith("[Image description]")
    assert "42 万" in image.content
    meta = image.metadata["multimodal"]
    assert meta["kind"] == "image_vlm"
    assert meta["vlm_model"] == "qwen2.5vl:3b"
    assert report.to_dict()["vlm_blocks"] == 1
    assert report.to_dict()["ocr_characters"] == 0


def test_vlm_failure_falls_back_to_ocr(tmp_path, monkeypatch):
    source = tmp_path / "report.docx"
    _docx_with_images(source, [("scan.png", b"scan-bytes")])
    extractor = _extractor(
        vlm_enabled=True,
        vlm_model="qwen2.5vl:3b",
        vlm_base_url="http://localhost:11434",
    )
    monkeypatch.setattr(extractor, "_ocr_available", lambda: True)
    monkeypatch.setattr(extractor, "_ocr", lambda image, suffix: ("Quarterly revenue: 42", None))
    monkeypatch.setattr(extractor, "_vlm_caption", lambda image: ("", "vlm_timeout"))

    enriched, report = extractor.enrich(str(source), "docx", [])

    image = enriched[-1]
    assert image.content.startswith("[Image OCR]")
    assert image.metadata["multimodal"]["kind"] == "image_ocr"
    report_dict = report.to_dict()
    assert report_dict["vlm_blocks"] == 0
    assert report_dict["skipped"] == {"vlm_timeout": 1}


def test_vlm_unavailable_model_fails_without_blocking(tmp_path, monkeypatch):
    """VLM 配置了模型但 HTTP 失败 → 只跳过，文本索引不受影响。"""
    source = tmp_path / "report.docx"
    _docx_with_images(source, [("photo.png", b"photo-bytes")])
    extractor = _extractor(
        ocr_enabled=False,
        vlm_enabled=True,
        vlm_model="qwen2.5vl:3b",
        vlm_base_url="http://localhost:11434",
    )

    import httpx

    def _raise_timeout(url, **kwargs):
        raise httpx.TimeoutException("boom")

    monkeypatch.setattr("app.core.parser.multimodal_evidence.httpx.post", _raise_timeout)

    enriched, report = extractor.enrich(str(source), "docx", [ParsedBlock("text", BlockType.PARAGRAPH)])

    assert [item.content for item in enriched] == ["text"]
    report_dict = report.to_dict()
    assert report_dict["image_blocks"] == 0
    assert report_dict["skipped"] == {"vlm_timeout": 1}


def test_real_vlm_caption_uses_ollama_images_contract(tmp_path, monkeypatch):
    """_vlm_caption 必须按 Ollama /api/chat 的 images(base64) 契约发请求。"""
    captured = {}

    class _Response:
        status_code = 200

        def json(self):
            return {"message": {"content": " 一张营收缩线图 "}}

    def _fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("app.core.parser.multimodal_evidence.httpx.post", _fake_post)

    extractor = _extractor(
        vlm_enabled=True,
        vlm_model="qwen2.5vl:3b",
        vlm_base_url="http://localhost:11434/",
        max_ocr_characters=100,
    )
    caption, reason = extractor._vlm_caption(b"img")

    assert reason is None
    assert caption == "一张营收缩线图"
    assert captured["url"] == "http://localhost:11434/api/chat"
    assert captured["json"]["model"] == "qwen2.5vl:3b"
    assert captured["json"]["stream"] is False
    import base64
    assert captured["json"]["messages"][0]["images"] == [base64.b64encode(b"img").decode("ascii")]
