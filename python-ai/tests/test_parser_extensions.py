"""Batch 4 解析扩展单元测试：PPTX / HTML / 图片 OCR 门控 + 表格感知分块。

PPTX 用测试内构造的最小 OOXML zip 包验证（无需真实 PowerPoint 文件）；
HTML 直接喂字符串；图片解析只测门控（OCR 子进程不进单测）。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from app.core.chunker.text_chunker import TextChunker
from app.core.parser.base import BaseParser, BlockType, ParsedBlock
from app.core.parser.html_parser import HtmlParser
from app.core.parser.pptx_parser import PptxParser

# ── 工厂注册 ───────────────────────────────────────────────────────────────


class TestFactory:
    def test_new_types_registered(self):
        assert isinstance(BaseParser.get_parser("pptx"), PptxParser)
        assert isinstance(BaseParser.get_parser("html"), HtmlParser)
        assert isinstance(BaseParser.get_parser("htm"), HtmlParser)
        from app.core.parser.image_parser import ImageParser

        assert isinstance(BaseParser.get_parser("png"), ImageParser)
        assert isinstance(BaseParser.get_parser("jpg"), ImageParser)
        assert isinstance(BaseParser.get_parser("jpeg"), ImageParser)


# ── PPTX ───────────────────────────────────────────────────────────────────

_SLIDE_XML = """<?xml version="1.0"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld><p:spTree>
    <p:sp>
      <p:nvSpPr><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>
      <p:txBody><a:p><a:r><a:t>年度销售报告</a:t></a:r></a:p></p:txBody>
    </p:sp>
    <p:sp>
      <p:txBody>
        <a:p><a:r><a:t>第一页正文内容。</a:t></a:r></a:p>
        <a:p><a:r><a:t>第二段说明文字。</a:t></a:r></a:p>
      </p:txBody>
    </p:sp>
    <p:graphicFrame>
      <a:tbl>
        <a:tr>
          <a:tc><a:txBody><a:p><a:r><a:t>产品</a:t></a:r></a:p></a:txBody></a:tc>
          <a:tc><a:txBody><a:p><a:r><a:t>销量</a:t></a:r></a:p></a:txBody></a:tc>
        </a:tr>
        <a:tr>
          <a:tc><a:txBody><a:p><a:r><a:t>音箱 S1</a:t></a:r></a:p></a:txBody></a:tc>
          <a:tc><a:txBody><a:p><a:r><a:t>1200</a:t></a:r></a:p></a:txBody></a:tc>
        </a:tr>
      </a:tbl>
    </p:graphicFrame>
  </p:spTree></p:cSld>
</p:sld>
"""

_NOTES_XML = """<?xml version="1.0"?>
<p:notes xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
         xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:txBody><a:p><a:r><a:t>备注：强调 Q4 增长。</a:t></a:r></a:p></p:txBody>
</p:notes>
"""


def _make_pptx(tmp_path: Path) -> Path:
    path = tmp_path / "deck.pptx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")  # 解析器不读，仅仿真
        archive.writestr("ppt/slides/slide1.xml", _SLIDE_XML)
        archive.writestr("ppt/notesSlides/notesSlide1.xml", _NOTES_XML)
    return path


class TestPptxParser:
    def test_extracts_title_paragraph_table_notes(self, tmp_path):
        blocks = PptxParser().parse(str(_make_pptx(tmp_path)))

        headings = [b for b in blocks if b.block_type == BlockType.HEADING]
        paragraphs = [b for b in blocks if b.block_type == BlockType.PARAGRAPH]
        tables = [b for b in blocks if b.block_type == BlockType.TABLE]
        notes = [b for b in paragraphs if b.metadata.get("source") == "speaker_notes"]

        assert len(headings) == 1 and headings[0].content == "年度销售报告"
        assert headings[0].metadata["slide"] == 1
        assert "第一页正文内容。" in [p.content for p in paragraphs]
        assert len(tables) == 1
        rows = tables[0].content.split("\n")
        assert rows[0] == "产品\t销量"
        assert rows[1] == "音箱 S1\t1200"
        assert notes and "Q4 增长" in notes[0].content

    def test_empty_presentation_raises(self, tmp_path):
        path = tmp_path / "empty.pptx"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("ppt/slides/slide1.xml",
                             '<p:sld xmlns:p="http://schemas.openxmlformats.org/'
                             'presentationml/2006/main"/>')
        with pytest.raises(ValueError):
            PptxParser().parse(str(path))


# ── HTML ───────────────────────────────────────────────────────────────────

_HTML_DOC = """
<html><head><title>ignore</title><style>.x{color:red}</style></head>
<body>
  <h1>退款政策</h1>
  <p>自购买之日起 <b>30 天</b>内可申请退款。</p>
  <h2>特殊条款</h2>
  <ul><li>拆封商品不支持</li><li>赠品需退回</li></ul>
  <table>
    <tr><th>档位</th><th>时限</th></tr>
    <tr><td>A</td><td>7 天</td></tr>
  </table>
  <script>alert('skip me');</script>
</body></html>
"""


class TestHtmlParser:
    def test_extracts_headings_paragraphs_list_table(self, tmp_path):
        path = tmp_path / "doc.html"
        path.write_text(_HTML_DOC, encoding="utf-8")
        blocks = HtmlParser().parse(str(path))

        headings = [b for b in blocks if b.block_type == BlockType.HEADING]
        lists = [b for b in blocks if b.block_type == BlockType.LIST]
        tables = [b for b in blocks if b.block_type == BlockType.TABLE]
        paragraphs = [b for b in blocks if b.block_type == BlockType.PARAGRAPH]

        assert [h.level for h in headings] == [1, 2]
        assert headings[0].content == "退款政策"
        assert "自购买之日起 30 天内可申请退款。" in [p.content for p in paragraphs]
        assert "拆封商品不支持" in [li.content for li in lists]
        assert len(tables) == 1
        assert tables[0].content.split("\n")[0] == "档位\t时限"
        assert tables[0].content.split("\n")[1] == "A\t7 天"
        # script/style/head 内容不进块
        assert not any("alert" in b.content or "color:red" in b.content for b in blocks)

    def test_empty_html_raises(self, tmp_path):
        path = tmp_path / "empty.html"
        path.write_text("<html><body><script>var a=1;</script></body></html>", encoding="utf-8")
        with pytest.raises(ValueError):
            HtmlParser().parse(str(path))


# ── 图片 OCR 门控 ──────────────────────────────────────────────────────────


class TestImageParserGate:
    def test_disabled_ocr_raises_with_hint(self, tmp_path, monkeypatch):
        from app.core.parser.image_parser import ImageParser
        from app.utils.config import config

        monkeypatch.setattr(config, "RAG_MULTIMODAL_OCR_ENABLED", False)
        path = tmp_path / "pic.png"
        path.write_bytes(b"\x89PNG fake")

        with pytest.raises(ValueError, match="OCR"):
            ImageParser().parse(str(path))

    def test_unsupported_suffix_rejected_when_ocr_enabled(self, tmp_path, monkeypatch):
        from app.core.parser.image_parser import ImageParser
        from app.utils.config import config

        monkeypatch.setattr(config, "RAG_MULTIMODAL_OCR_ENABLED", True)
        path = tmp_path / "pic.bmp"
        path.write_bytes(b"BM fake")

        with pytest.raises(ValueError, match="Unsupported image"):
            ImageParser().parse(str(path))


# ── 表格感知分块 ───────────────────────────────────────────────────────────


class TestTableAwareChunking:
    def _table_block(self, rows: int) -> ParsedBlock:
        lines = ["产品\t销量\t备注"]
        for i in range(rows):
            lines.append(f"产品-{i}\t{100 + i}\t备注说明文字{i}")
        return ParsedBlock(content="\n".join(lines), block_type=BlockType.TABLE)

    def test_small_table_single_chunk(self):
        chunker = TextChunker(chunk_size=2000, chunk_overlap=50)
        chunks = chunker.chunk([self._table_block(3)], "doc-1")
        assert len(chunks) == 1
        assert chunks[0].block_type == "TABLE"

    def test_large_table_aligns_to_rows_with_header_prefix(self):
        chunker = TextChunker(chunk_size=300, chunk_overlap=0)
        chunks = chunker.chunk([self._table_block(60)], "doc-2")

        assert len(chunks) > 1
        original_rows = {line for line in self._table_block(60).content.split("\n")}
        for i, chunk in enumerate(chunks):
            assert chunk.metadata.get("table_row_aligned") is True
            lines = chunk.content.split("\n")
            if i > 0:
                # 续块自带表头前缀
                assert lines[0] == "产品\t销量\t备注"
                assert "（表格续" in lines[1]
                body_lines = lines[2:]
            else:
                body_lines = lines
            for line in body_lines:
                assert line in original_rows  # 任何一行都未被切断

    def test_oversized_single_row_hard_split_fallback(self):
        huge_row = "X" * 500
        block = ParsedBlock(
            content=f"表头\t列2\n{huge_row}", block_type=BlockType.TABLE)
        chunker = TextChunker(chunk_size=200, chunk_overlap=0)
        chunks = chunker.chunk([block], "doc-3")
        assert len(chunks) >= 3  # 表头 + 长行硬切多块
        assert chunks[0].content.startswith("表头")
