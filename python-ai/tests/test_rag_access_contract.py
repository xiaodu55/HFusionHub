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

    assert chunks == [NO_SUFFICIENT_EVIDENCE_REPLY]
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


def test_postprocessor_rejects_low_confidence_context():
    processor = Postprocessor(min_score=0.35)

    results = processor.process([
        {"content": "不相关片段", "score": 0.34, "document_id": "1"},
        {"content": "有依据片段", "score": 0.35, "document_id": "2"},
    ])

    assert [result.document_id for result in results] == ["2"]
