"""Regression tests for the evidence-first chat contract."""

import pytest

from app.core.agent.react import NO_SUFFICIENT_EVIDENCE_REPLY, ReactAgent
from app.core.rag.postprocessor import Postprocessor


class _EmptyRetriever:
    def __init__(self):
        self.knowledge_base_ids = []

    async def retrieve(self, **kwargs):
        self.knowledge_base_ids.append(kwargs["knowledge_base_id"])

        class _Result:
            results = []

        return _Result()


class _NoDecomposition:
    async def decompose(self, *args, **kwargs):
        return None


class _ChitchatIntent:
    intent = "chitchat"


class _ChitchatClassifier:
    async def classify(self, *args, **kwargs):
        return _ChitchatIntent()


class _StreamingLlm:
    async def chat_stream(self, *args, **kwargs):
        yield "普通对话"


@pytest.mark.asyncio
async def test_selected_knowledge_base_requires_retrieved_evidence(monkeypatch):
    """A selected KB is the only retrieval scope and empty recall does not call the LLM."""
    import app.core.agent.react as react_module
    import app.core.rag as rag_module

    retriever = _EmptyRetriever()
    monkeypatch.setattr(react_module, "get_retriever", lambda: retriever)
    monkeypatch.setattr(rag_module, "get_query_decomposer", lambda: _NoDecomposition())

    agent = ReactAgent(knowledge_base_id=7)
    chunks = [chunk async for chunk in agent.run_stream("文档里的发布日期是什么？")]

    # The streaming protocol now emits a retrieval lifecycle event before the
    # final plain-text evidence warning.  The warning remains the only answer
    # content and the LLM must still not be called.
    assert chunks[-1] == NO_SUFFICIENT_EVIDENCE_REPLY
    assert len(chunks) == 2
    import json
    event = json.loads(chunks[0])
    assert event["event"] == "step_completed"
    assert event["step_type"] == "retrieval"
    assert retriever.knowledge_base_ids == [7]


@pytest.mark.asyncio
async def test_general_chat_never_calls_retriever_without_a_selected_kb(monkeypatch):
    import app.core.agent.react as react_module
    import app.core.rag as rag_module

    retriever = _EmptyRetriever()
    monkeypatch.setattr(react_module, "get_retriever", lambda: retriever)
    monkeypatch.setattr(rag_module, "get_intent_classifier", lambda: _ChitchatClassifier())
    monkeypatch.setattr(react_module, "get_llm", lambda: _StreamingLlm())

    agent = ReactAgent()
    chunks = [chunk async for chunk in agent.run_stream("你好")]

    assert chunks == ["普通对话"]
    assert retriever.knowledge_base_ids == []


@pytest.mark.asyncio
async def test_general_chat_bypasses_retrieval_with_a_selected_kb(monkeypatch):
    """Selecting a KB narrows retrieval but does not turn greetings into RAG queries."""
    import app.core.agent.react as react_module
    import app.core.rag as rag_module

    retriever = _EmptyRetriever()
    monkeypatch.setattr(react_module, "get_retriever", lambda: retriever)
    monkeypatch.setattr(rag_module, "get_intent_classifier", lambda: _ChitchatClassifier())
    monkeypatch.setattr(react_module, "get_llm", lambda *args, **kwargs: _StreamingLlm())

    agent = ReactAgent(knowledge_base_id=7)
    chunks = [chunk async for chunk in agent.run_stream("你好")]

    assert chunks == ["普通对话"]
    assert retriever.knowledge_base_ids == []


def test_postprocessor_rejects_low_confidence_context():
    processor = Postprocessor(min_score=0.35)

    results = processor.process([
        {"content": "不相关片段", "score": 0.34, "document_id": "1"},
        {"content": "有依据片段", "score": 0.35, "document_id": "2"},
    ])

    assert [result.document_id for result in results] == ["2"]


def test_rrf_rank_does_not_bypass_the_evidence_threshold():
    """RRF ordering and P0's evidence safety gate use distinct scores."""
    processor = Postprocessor(min_score=0.35)

    results = processor.process([
        {
            "content": "keyword-only but well supported",
            "score": 0.30,
            "document_id": "1",
            "metadata": {"evidence_score": 0.91},
        },
        {
            "content": "weak raw evidence",
            "score": 0.99,
            "document_id": "2",
            "metadata": {"evidence_score": 0.20},
        },
    ])

    assert [result.document_id for result in results] == ["1"]


# ---- 后处理回归：输出约束剥离 + 跨通道互认 + 短查询降门槛 ----


def test_output_constraint_stripped_from_query_terms():
    """格式指令不应参与查询覆盖率计算。"""
    processor = Postprocessor(min_score=0.0)

    # 模拟：输出格式指令 + 实际查询内容
    results, decisions = processor.process_with_debug(
        [
            {
                "content": "The test token is 1785288404409",
                "score": 0.72,
                "document_id": "1",
                "source": "vector",
                "metadata": {"chunk_id": "4_chunk_0000", "evidence_score": 0.72},
            }
        ],
        query="exact number answer only the test token",
    )

    accepted_ids = [d["chunk_id"] for d in decisions if d["decision"] != "filtered_query_mismatch"]
    assert "4_chunk_0000" in accepted_ids, (
        f"应通过（输出约束已剥离），实际决策: {decisions}"
    )


def test_cross_channel_corroboration_bypasses_query_coverage():
    """向量+关键词双通道命中 → 跨通道互认绕过覆盖率（覆盖率本应失败时）。"""
    processor = Postprocessor(min_score=0.0, strong_evidence_score=0.85)

    content = "The test token is 1785288404409"
    chunk_metadata = {"chunk_id": "4_chunk_0000", "evidence_score": 0.5}

    # 查询中包含不会匹配 chunk 的非输出词，确保覆盖率本应失败
    results, decisions = processor.process_with_debug(
        [
            {
                "content": content,
                "score": 0.5,
                "document_id": "1",
                "source": "vector",
                "metadata": chunk_metadata,
            },
            {
                "content": content,
                "score": 0.4,
                "document_id": "1",
                "source": "keyword",
                "metadata": chunk_metadata,
            },
        ],
        query="python framework architecture design pattern deployment",
    )

    accepted = [d for d in decisions if d["decision"] not in ("filtered_low_evidence", "filtered_query_mismatch")]
    assert len(accepted) >= 1, (
        f"双通道命中应有跨通道互认通过，实际决策: {decisions}"
    )
    bypass_reasons = {d.get("bypass_reason", "") for d in accepted if "bypass_reason" in d}
    assert "cross_channel_corroboration" in bypass_reasons, (
        f"应包含跨通道互认标记，实际理由: {bypass_reasons}"
    )


def test_short_query_lenient_coverage():
    """短查询（≤3 词）应使用更宽松的覆盖率阈值。"""
    processor = Postprocessor(min_score=0.0)

    # Query 只有 3 个有效词，但 content 只匹配 1 个 → 覆盖 0.33 ≥ 新阈值 0.33
    results, decisions = processor.process_with_debug(
        [
            {
                "content": "token is 1785288404409",
                "score": 0.6,
                "document_id": "1",
                "source": "vector",
                "metadata": {"chunk_id": "chunk_1", "evidence_score": 0.6},
            }
        ],
        query="document test token",
    )

    accepted = [d for d in decisions if d["decision"] not in ("filtered_low_evidence", "filtered_query_mismatch")]
    assert len(accepted) == 1, (
        f"短查询应通过，实际决策: {decisions}"
    )


def test_exact_token_number_preserved_after_output_stripping():
    """核心回归：指定 token 数字的查询 → 分块通过，不被 postprocessor 过滤。"""
    processor = Postprocessor(min_score=0.35)

    content = "The test token is 1785288404409"
    chunk_metadata = {"chunk_id": "4_chunk_0000", "evidence_score": 0.72}

    results, decisions = processor.process_with_debug(
        [
            {
                "content": content,
                "score": 0.72,
                "document_id": "1",
                "source": "vector",
                "metadata": chunk_metadata,
            },
            {
                "content": content,
                "score": 0.45,
                "document_id": "1",
                "source": "keyword",
                "metadata": chunk_metadata,
            },
        ],
        query="Answer only the number. What is the test token in the document?",
    )

    accepted = [d for d in decisions if d["decision"] not in ("filtered_low_evidence", "filtered_query_mismatch")]
    assert len(accepted) >= 1, (
        f"token 精确查询应通过后处理，实际决策: {decisions}"
    )
    # 验证分块内容完整保留
    assert results and results[0].content == content


def test_strong_evidence_bypasses_coverage():
    """强通道分数（≥0.65）应绕过查询覆盖率。"""
    processor = Postprocessor(min_score=0.0, strong_evidence_score=0.65)

    results, decisions = processor.process_with_debug(
        [
            {
                "content": "1785288404409",
                "score": 0.90,
                "document_id": "1",
                "source": "vector",
                "metadata": {"chunk_id": "chunk_s", "evidence_score": 0.90},
            }
        ],
        query="some unrelated words that do not match anything here at all",
    )

    accepted = [d for d in decisions if d["decision"] not in ("filtered_low_evidence", "filtered_query_mismatch")]
    assert len(accepted) == 1, (
        f"强证据分应绕过覆盖率，实际决策: {decisions}"
    )
    assert any(
        d.get("bypass_reason") == "strong_channel_score" for d in accepted
    ), f"缺少 strong_channel_score 标记: {decisions}"
