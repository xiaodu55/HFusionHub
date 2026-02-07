import pytest
from fastapi.testclient import TestClient

from app.api import rag as rag_api
from app.core.rag.evaluation import EvaluationCase, RetrievalEvaluator
from app.core.rag.observability import RetrievalTrace, get_trace_store, reset_trace_store
from app.core.rag.postprocessor import ProcessedResult, get_postprocessor
from app.core.rag.query_router import ChannelType, MergedResult, SearchResult
from app.core.rag.retriever import MultiChannelRetriever, RetrievalResult
from app.main import create_app


class FakeRouter:
    async def search(self, query, knowledge_base_id, top_k):
        return MergedResult(
            results=[SearchResult(
                content="RAG observability document",
                score=0.92,
                source=ChannelType.VECTOR,
                document_id=42,
                metadata={"knowledge_base_id": knowledge_base_id},
            )],
            total_count=1,
            channels_used=[ChannelType.VECTOR],
            metadata={
                "route_result": {
                    "query_type": "factual",
                    "strategy": "multi",
                    "confidence": 0.8,
                    "selected_channels": ["vector"],
                }
            },
        )


class FakeRetriever:
    async def retrieve(self, query, **kwargs):
        return RetrievalResult(
            query=query,
            results=[ProcessedResult(
                content="expected content",
                score=0.9,
                document_id="doc-1",
            )],
        )


@pytest.mark.asyncio
async def test_retriever_records_route_and_result_trace():
    reset_trace_store()
    retriever = MultiChannelRetriever(postprocessor=get_postprocessor())
    retriever.router = FakeRouter()

    result = await retriever.retrieve("What is RAG?", knowledge_base_id=7, top_k=3)
    traces = get_trace_store().list()

    assert result.results[0].document_id == 42
    assert len(traces) == 1
    assert traces[0]["knowledge_base_id"] == 7
    assert traces[0]["routes"][0]["selected_channels"] == ["vector"]
    assert traces[0]["results"][0]["document_id"] == 42


@pytest.mark.asyncio
async def test_retrieval_evaluator_calculates_rank_metrics():
    evaluator = RetrievalEvaluator(FakeRetriever())

    report = await evaluator.evaluate(
        cases=[EvaluationCase(query="test", expected_document_ids=["doc-1"])],
        knowledge_base_id=1,
        top_k=3,
    )

    assert report["summary"]["precision_at_k"] == 1.0
    assert report["summary"]["recall_at_k"] == 1.0
    assert report["summary"]["mean_reciprocal_rank"] == 1.0


def test_trace_api_exposes_trace_and_stats():
    reset_trace_store()
    trace = get_trace_store().record(RetrievalTrace(
        query="trace test",
        knowledge_base_id=1,
        top_k=3,
        latency_ms=12.5,
    ))
    client = TestClient(create_app())

    listed = client.get("/api/rag/traces")
    detail = client.get(f"/api/rag/traces/{trace.trace_id}")
    stats = client.get("/api/rag/traces/stats")

    assert listed.status_code == 200
    assert listed.json()["traces"][0]["trace_id"] == trace.trace_id
    assert detail.status_code == 200
    assert stats.json()["total_traces"] == 1


def test_evaluation_api_uses_retrieval_evaluator(monkeypatch):
    monkeypatch.setattr(rag_api, "get_retriever", lambda: FakeRetriever())
    client = TestClient(create_app())

    response = client.post("/api/rag/evaluate", json={
        "knowledge_base_id": 1,
        "top_k": 3,
        "cases": [{
            "case_id": "case-1",
            "query": "test",
            "expected_document_ids": ["doc-1"],
        }],
    })

    assert response.status_code == 200
    assert response.json()["summary"]["recall_at_k"] == 1.0
