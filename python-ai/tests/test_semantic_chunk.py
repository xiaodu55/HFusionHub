"""语义分块（RAG_SEMANTIC_CHUNK_ENABLED）回归测试。

覆盖：flag 关直通固定窗口 / 语义断点命中与句子完整性 / embedding 失败回退 /
最小块长度推迟断点 / TABLE 块不走语义 / 单句超限硬切 / 零向量余弦。
"""

import pytest

from app.core.chunker.text_chunker import _cosine, chunk_blocks
from app.core.parser.base import BlockType, ParsedBlock
from app.utils.config import config


def _block(content: str, block_type: BlockType = BlockType.PARAGRAPH) -> ParsedBlock:
    return ParsedBlock(content=content, block_type=block_type, level=None, metadata={})


class _FakeEmbeddingService:
    """按主题返回 3 维向量：组内同向（cos=1，不断），组间正交（cos=0，断）。"""

    def __init__(self, topic_of, fail: bool = False):
        self._topic_of = topic_of
        self._fail = fail
        self.calls: list[list[str]] = []

    def get_embedding_batch(self, texts):
        if self._fail:
            raise RuntimeError("embedding provider down")
        self.calls.append(list(texts))
        return [[1.0, 0.0, 0.0] if self._topic_of(t) == "a" else [0.0, 1.0, 0.0] for t in texts]


@pytest.fixture()
def enable_semantic(monkeypatch):
    monkeypatch.setattr(config, "RAG_SEMANTIC_CHUNK_ENABLED", True)
    monkeypatch.setattr(config, "RAG_SEMANTIC_SIM_THRESHOLD", 0.55)
    monkeypatch.setattr(config, "RAG_SEMANTIC_MIN_CHUNK", 1)


def test_flag_off_uses_fixed_windows(monkeypatch):
    monkeypatch.setattr(config, "RAG_SEMANTIC_CHUNK_ENABLED", False)
    long_text = "".join(f"这是第{i}句话，讲述一个固定的主题内容。" for i in range(60))
    chunks = chunk_blocks([_block(long_text)], "doc-flag-off")
    assert len(chunks) > 1
    # 固定窗口路径不产生语义标记
    assert all("semantic_boundary" not in c.metadata for c in chunks)


def test_semantic_boundary_splits_at_topic_change(enable_semantic, monkeypatch):
    monkeypatch.setattr(config, "CHUNK_SIZE", 35)
    # 主题 A 三个句子（30 字）+ 主题 B 三个句子（31 字），交界处应断开
    topic_a = "猫是常见的家庭宠物。猫喜欢在白天睡觉。猫的祖先来自沙漠。"
    topic_b = "股票市场今天大幅波动。投资者担心利率上升。分析师建议分散配置。"
    fake = _FakeEmbeddingService(lambda t: "a" if t[:5] in topic_a else "b")
    monkeypatch.setattr("app.core.embedding.get_embedding_service", lambda: fake)

    chunks = chunk_blocks([_block(topic_a + topic_b)], "doc-semantic")
    assert len(chunks) == 2
    assert all(c.metadata.get("semantic_boundary") for c in chunks)
    # 句子完整性：每块都以句末标点收尾
    assert chunks[0].content.endswith("。")
    assert chunks[1].content.endswith("。")
    # 断点在主题交界：块 0 全部来自主题 A，块 1 全部来自主题 B
    assert chunks[0].content.startswith("猫")
    assert chunks[1].content.startswith("股票")
    # embedding 一次批量调用，句子数 = 6
    assert len(fake.calls[0]) == 6


def test_embedding_failure_falls_back_to_fixed_windows(enable_semantic, monkeypatch):
    monkeypatch.setattr(
        "app.core.embedding.get_embedding_service",
        lambda: _FakeEmbeddingService(lambda t: "a", fail=True),
    )
    long_text = "".join(f"这是第{i}个语义完整的句子，用来撑长度。" for i in range(60))
    chunks = chunk_blocks([_block(long_text)], "doc-fallback")
    assert len(chunks) > 1
    assert all("semantic_boundary" not in c.metadata for c in chunks)


def test_min_chunk_length_defers_boundary(enable_semantic, monkeypatch):
    sentence = "这一句有十七个字测语义。"  # 12 字
    text = "".join(sentence if i % 2 == 0 else "换个主题写句子内容。" for i in range(16))
    monkeypatch.setattr(config, "CHUNK_SIZE", 100)
    monkeypatch.setattr("app.core.embedding.get_embedding_service", lambda: _FakeEmbeddingService(lambda t: "a" if t == sentence else "b"))

    # MIN_CHUNK=1：每个句间都是断点 → 逐句成块
    monkeypatch.setattr(config, "RAG_SEMANTIC_MIN_CHUNK", 1)
    eager = chunk_blocks([_block(text)], "doc-eager")
    # MIN_CHUNK=10000：相似度断点全部被最小长度压住 → 只剩硬上限分块
    monkeypatch.setattr(config, "RAG_SEMANTIC_MIN_CHUNK", 10_000)
    deferred = chunk_blocks([_block(text)], "doc-deferred")

    assert len(eager) > len(deferred)
    # 推迟后每块至少合并 2 句（≥ 24 字）
    assert all(len(c.content) >= 24 for c in deferred)


def test_table_block_never_goes_semantic(enable_semantic, monkeypatch):
    rows = "列A,列B\n" + "".join(f"值{i},数据{i}\n" for i in range(120))
    fake = _FakeEmbeddingService(lambda t: "a")
    monkeypatch.setattr("app.core.embedding.get_embedding_service", lambda: fake)
    chunks = chunk_blocks([_block(rows, BlockType.TABLE)], "doc-table")
    assert len(chunks) > 1
    assert all("semantic_boundary" not in c.metadata for c in chunks)
    assert fake.calls == []  # 表格路径不触发 embedding


def test_overlong_single_sentence_hard_split(enable_semantic, monkeypatch):
    monkeypatch.setattr(config, "CHUNK_SIZE", 50)
    # 161 字单句 + 短句：语义路径放行，超长句在落块时硬切兜底
    content = "这" * 160 + "。" + "结尾。"
    fake = _FakeEmbeddingService(lambda t: "a")
    monkeypatch.setattr("app.core.embedding.get_embedding_service", lambda: fake)

    chunks = chunk_blocks([_block(content)], "doc-hard")
    assert len(chunks) >= 3
    assert all(len(c.content) <= 50 for c in chunks)


def test_cosine_handles_zero_vectors():
    assert _cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert _cosine([0.0, 0.0], [1.0, 0.0]) == 0.0
    assert _cosine([1.0, 1.0], [1.0, 1.0]) == pytest.approx(1.0)


def test_short_content_single_chunk_untouched(enable_semantic):
    chunks = chunk_blocks([_block("短文本，无需切分。")], "doc-short")
    assert len(chunks) == 1
    assert all("semantic_boundary" not in c.metadata for c in chunks)
