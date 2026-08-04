"""Parent-Child 父子分块检索（实验特性 RAG_PARENT_CHILD_ENABLED）测试。

覆盖：chunker 父内容附着（多窗口块才附着 / 预算守卫降级）、
postprocessor 父展开（内容替换 / 同父去重 / flag 关闭直通）。
"""

import json

from app.core.chunker.text_chunker import TextChunker, chunk_blocks
from app.core.parser.base import BlockType, ParsedBlock
from app.core.rag.postprocessor import Postprocessor
from app.utils.config import config

LONG_TEXT = "这是用于父子分块测试的资料段落，" * 60  # 远超 chunk_size，必产出多窗口


def _parse_block(content: str, block_type: BlockType = BlockType.PARAGRAPH) -> ParsedBlock:
    return ParsedBlock(content=content, block_type=block_type, level=None, metadata={})


def _enable(monkeypatch, value=True):
    monkeypatch.setattr(config, "RAG_PARENT_CHILD_ENABLED", value)


# ── chunker：父内容附着 ────────────────────────────────────────────────


def test_chunker_attaches_parent_to_multi_window_blocks(monkeypatch):
    _enable(monkeypatch)
    chunker = TextChunker(chunk_size=200, chunk_overlap=20)
    chunks = chunker.chunk([_parse_block(LONG_TEXT)], "doc_pc_1")

    assert len(chunks) > 1, "长文本应切出多个窗口"
    parent_ids = {c.metadata.get("parent_id") for c in chunks}
    assert len(parent_ids) == 1
    assert chunks[0].metadata["parent_id"] == "doc_pc_1_parent_000"
    # 父内容一致且非空
    contents = {c.metadata.get("parent_content") for c in chunks}
    assert len(contents) == 1
    assert next(iter(contents)).startswith("这是用于父子分块测试")


def test_chunker_single_window_block_has_no_parent(monkeypatch):
    _enable(monkeypatch)
    chunker = TextChunker(chunk_size=200, chunk_overlap=20)
    chunks = chunker.chunk([_parse_block("短内容，无需父块。")], "doc_pc_2")

    assert len(chunks) == 1
    assert "parent_id" not in chunks[0].metadata


def test_chunker_parent_disabled_when_flag_off(monkeypatch):
    _enable(monkeypatch, False)
    chunker = TextChunker(chunk_size=200, chunk_overlap=20)
    chunks = chunker.chunk([_parse_block(LONG_TEXT)], "doc_pc_3")

    assert all("parent_id" not in c.metadata for c in chunks)


def test_chunker_metadata_budget_guard_drops_parent_content(monkeypatch):
    """block.metadata 本身巨大时，附着父内容会撑爆 Milvus metadata(4000)——
    预算守卫应丢弃 parent_content（parent_id 保留，降级为无父正文）。"""
    _enable(monkeypatch)
    block = _parse_block(LONG_TEXT)
    block.metadata["huge_field"] = "x" * 3800
    chunker = TextChunker(chunk_size=200, chunk_overlap=20)
    chunks = chunker.chunk([block], "doc_pc_4")

    assert len(chunks) > 1
    for c in chunks:
        assert len(json.dumps(c.metadata, ensure_ascii=False)) <= 4000
        assert "parent_content" not in c.metadata


def test_chunk_blocks_entry_keeps_parent_attachment(monkeypatch):
    _enable(monkeypatch)
    chunker_blocks = [_parse_block(LONG_TEXT)]
    chunks = chunk_blocks(chunker_blocks, "doc_pc_5")
    assert any(c.metadata.get("parent_id") == "doc_pc_5_parent_000" for c in chunks)


# ── postprocessor：父展开与同父去重 ────────────────────────────────────


def _processed(content, score, parent_id=None, parent_content=None, chunk_id="c"):
    from app.core.rag.postprocessor import ProcessedResult

    metadata = {"chunk_id": chunk_id}
    if parent_id:
        metadata["parent_id"] = parent_id
    if parent_content:
        metadata["parent_content"] = parent_content
    return ProcessedResult(content=content, score=score, document_id="1", metadata=metadata)


def _enable_pp(monkeypatch, value=True):
    from app.core.rag import postprocessor as pp_mod

    monkeypatch.setattr(pp_mod.config, "RAG_PARENT_CHILD_ENABLED", value)


def test_expand_replaces_child_content_with_parent(monkeypatch):
    _enable_pp(monkeypatch)
    pp = Postprocessor()
    results = [
        _processed("窗口片段甲", 0.9, parent_id="p1", parent_content="完整的父上下文内容"),
    ]
    expanded = pp._expand_parents(results)
    assert expanded[0].content == "完整的父上下文内容"
    assert expanded[0].metadata["parent_expanded"] is True


def test_expand_dedups_same_parent_children(monkeypatch):
    _enable_pp(monkeypatch)
    pp = Postprocessor()
    results = [
        _processed("高分窗口片段", 0.9, parent_id="p1", parent_content="父上下文"),
        _processed("低分窗口片段", 0.7, parent_id="p1", parent_content="父上下文"),
    ]
    expanded = pp._expand_parents(results)
    assert len(expanded) == 1
    assert expanded[0].content == "父上下文"
    assert expanded[0].metadata["parent_id"] == "p1"


def test_expand_keeps_children_without_parent(monkeypatch):
    _enable_pp(monkeypatch)
    pp = Postprocessor()
    results = [_processed("无父块的普通结果", 0.8)]
    expanded = pp._expand_parents(results)
    assert len(expanded) == 1
    assert expanded[0].content == "无父块的普通结果"


def test_expand_disabled_passthrough(monkeypatch):
    """flag 关闭时走 process_with_debug 全流程：不做父展开。"""
    _enable_pp(monkeypatch, False)
    pp = Postprocessor()
    child = {
        "content": "窗口片段：弹性工作制时间为 09:30-18:30",
        "score": 0.9,
        "chunk_id": "c1",
        "metadata": {"parent_id": "p1", "parent_content": "父上下文"},
    }
    accepted, _ = pp.process_with_debug([child], top_k=5, query="弹性工作制")
    assert len(accepted) == 1
    assert accepted[0].content == "窗口片段：弹性工作制时间为 09:30-18:30"
    assert accepted[0].metadata.get("parent_expanded") is None


def test_expand_via_process_with_debug(monkeypatch):
    """flag 开启时同父子块去重 + 内容替换为父正文。"""
    _enable_pp(monkeypatch)
    pp = Postprocessor()
    children = [
        {
            "content": "窗口片段一：弹性工作制时间为 09:30-18:30",
            "score": 0.9,
            "chunk_id": "c1",
            "metadata": {"parent_id": "p1", "parent_content": "完整的父上下文：弹性工作制度全文说明"},
        },
        {
            "content": "窗口片段二：到岗时间为 09:00-10:00",
            "score": 0.8,
            "chunk_id": "c2",
            "metadata": {"parent_id": "p1", "parent_content": "完整的父上下文：弹性工作制度全文说明"},
        },
    ]
    accepted, _ = pp.process_with_debug(children, top_k=5, query="弹性工作制")
    # 同父去重：两条子块由一条父正文代表（top_k 名额让给更多样的证据）
    assert len(accepted) == 1
    assert accepted[0].content == "完整的父上下文：弹性工作制度全文说明"
    assert accepted[0].metadata["parent_expanded"] is True
