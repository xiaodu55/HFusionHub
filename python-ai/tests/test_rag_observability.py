import pytest
from fastapi.testclient import TestClient

from app.api import rag as rag_api
from app.core.rag.evaluation import EvaluationCase, RetrievalEvaluator
from app.core.rag.evaluation_runs import EvaluationRunStore
from app.core.rag.observability import RetrievalTrace, get_trace_store, reset_trace_store
from app.core.rag.postprocessor import Postprocessor, ProcessedResult, get_postprocessor
from app.core.rag.query_router import ChannelType, MergedResult, SearchResult
from app.core.rag.retriever import MultiChannelRetriever, RetrievalResult
from app.core.rag.reranker import LexicalReranker
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
                },
                "channel_candidates": {
                    "vector": [{
                        "rank": 1,
                        "chunk_id": "chunk-42",
                        "document_id": 42,
                        "knowledge_base_id": knowledge_base_id,
                        "score": 0.92,
                    }]
                },
                "channel_latencies_ms": {"vector": 1.5},
                "router_latency_ms": 2.0,
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
                source="hybrid",
                metadata={"channels": ["vector", "graph"]},
            )],
        )


class FakeMultimodalRetriever:
    async def retrieve(self, query, **kwargs):
        return RetrievalResult(
            query=query,
            results=[ProcessedResult(
                content="[Image OCR] revenue 42",
                score=0.9,
                document_id="doc-visual",
                source="vector",
                metadata={"multimodal": {"kind": "image_ocr", "page_number": 1}},
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
    assert traces[0]["debug"]["channel_candidates"][0]["candidates"]["vector"][0]["chunk_id"] == "chunk-42"
    assert traces[0]["debug"]["postprocessing"][0]["decision"] == "accepted"
    assert traces[0]["debug"]["stage_timings_ms"]["postprocess"] >= 0


@pytest.mark.asyncio
async def test_retriever_records_optional_reranker_decision():
    reset_trace_store()
    retriever = MultiChannelRetriever(postprocessor=get_postprocessor(), reranker=LexicalReranker())
    retriever.router = FakeRouter()

    result = await retriever.retrieve("RAG observability", knowledge_base_id=7, top_k=3)
    trace = get_trace_store().get(result.metadata["trace_id"])

    assert trace["debug"]["reranker"]["applied"] is True
    assert trace["debug"]["reranker"]["reranker"] == "lexical"
    assert "rerank" in trace["debug"]["stage_timings_ms"]


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
    assert report["summary"]["graph_hit_rate"] == 1.0


@pytest.mark.asyncio
async def test_retrieval_evaluator_records_multimodal_hits():
    evaluator = RetrievalEvaluator(FakeMultimodalRetriever())

    report = await evaluator.evaluate(
        cases=[EvaluationCase(query="What is in the diagram?", expected_document_ids=["doc-visual"])],
        knowledge_base_id=1,
        top_k=3,
    )

    assert report["summary"]["multimodal_hit_rate"] == 1.0
    assert report["cases"][0]["multimodal_hit"] is True


def test_trace_api_exposes_trace_and_stats():
    reset_trace_store()
    trace = get_trace_store().record(RetrievalTrace(
        query="trace test",
        knowledge_base_id=1,
        top_k=3,
        latency_ms=12.5,
    ))
    client = TestClient(create_app(), headers={"X-Internal-Token": "test-internal-token", "X-Tenant-Id": "1"})

    listed = client.get("/api/rag/traces", params={"knowledge_base_id": 1})
    detail = client.get(f"/api/rag/traces/{trace.trace_id}", params={"knowledge_base_id": 1})
    stats = client.get("/api/rag/traces/stats", params={"knowledge_base_id": 1})

    assert listed.status_code == 200
    assert listed.json()["traces"][0]["trace_id"] == trace.trace_id
    assert detail.status_code == 200
    assert stats.json()["total_traces"] == 1


def test_postprocessor_filters_low_query_coverage_false_positive():
    postprocessor = Postprocessor(min_score=0.0)
    processed, decisions = postprocessor.process_with_debug([
        {
            "content": "虚拟机管理软件安装成功之后，就可以新建虚拟机了。",
            "score": 0.72,
            "document_id": "linux",
            "source": "vector",
            "metadata": {"chunk_id": "linux-1", "evidence_score": 0.72},
        },
        {
            "content": "Java 虚拟线程是 JDK 提供的轻量级线程，用于降低并发任务创建成本。",
            "score": 0.7,
            "document_id": "java",
            "source": "vector",
            "metadata": {"chunk_id": "java-1", "evidence_score": 0.7},
        },
    ], top_k=3, query="Java 虚拟线程是什么")

    assert [result.document_id for result in processed] == ["java"]
    assert decisions[0]["decision"] == "filtered_query_mismatch"
    assert decisions[1]["decision"] == "accepted"


def test_debug_search_api_returns_a_scoped_full_trace(monkeypatch):
    reset_trace_store()
    retriever = MultiChannelRetriever(postprocessor=get_postprocessor())
    retriever.router = FakeRouter()
    monkeypatch.setattr(rag_api, "get_retriever", lambda: retriever)
    client = TestClient(create_app(), headers={"X-Internal-Token": "test-internal-token", "X-Tenant-Id": "1"})

    response = client.post("/api/rag/debug/search", json={
        "query": "What is RAG?",
        "knowledge_base_id": 7,
        "top_k": 3,
        "enable_rewrite": False,
    })

    assert response.status_code == 200
    payload = response.json()
    assert payload["knowledge_base_id"] == 7
    assert payload["debug"]["channel_candidates"][0]["candidates"]["vector"][0]["chunk_id"] == "chunk-42"
    assert payload["debug"]["postprocessing"][0]["decision"] == "accepted"


def test_trace_api_filters_paginates_and_exports_records():
    reset_trace_store()
    trace_store = get_trace_store()
    trace_store.record(RetrievalTrace(
        query="vector search",
        knowledge_base_id=1,
        top_k=3,
        latency_ms=10,
        results=[{"source": "vector", "document_id": 1}],
    ))
    trace_store.record(RetrievalTrace(
        query="broken graph search",
        knowledge_base_id=2,
        top_k=3,
        latency_ms=20,
        error="graph unavailable",
        results=[{"source": "graph", "document_id": 2}],
    ))
    client = TestClient(create_app(), headers={"X-Internal-Token": "test-internal-token", "X-Tenant-Id": "1"})

    listed = client.get("/api/rag/traces", params={
        "query": "vector",
        "knowledge_base_id": 1,
        "source": "vector",
        "limit": 1,
        "offset": 0,
    })
    stats = client.get("/api/rag/traces/stats", params={"days": 3, "knowledge_base_id": 1})
    exported_json = client.get("/api/rag/traces/export", params={"format": "json", "error_only": "true", "knowledge_base_id": 2})
    exported_csv = client.get("/api/rag/traces/export", params={"format": "csv", "knowledge_base_id": 1})

    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["traces"][0]["query"] == "vector search"
    assert stats.json()["hit_traces"] == 1
    assert stats.json()["hit_rate"] == 1.0
    assert len(stats.json()["daily_metrics"]) == 3
    assert stats.json()["recent_failures"] == []
    assert exported_json.json()["filename"].endswith(".json")
    assert "broken graph search" in exported_json.json()["content"]
    assert exported_csv.json()["filename"].endswith(".csv")
    assert "trace_id" in exported_csv.json()["content"]


def test_evaluation_api_uses_retrieval_evaluator(monkeypatch):
    monkeypatch.setattr(rag_api, "get_retriever", lambda: FakeRetriever())
    store = EvaluationRunStore(":memory:")
    monkeypatch.setattr(rag_api, "get_evaluation_run_store", lambda: store)
    client = TestClient(create_app(), headers={"X-Internal-Token": "test-internal-token", "X-Tenant-Id": "1"})

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
    assert response.json()["run"]["case_count"] == 1

    history = client.get("/api/rag/evaluation-runs", params={"knowledge_base_id": 1})
    assert history.status_code == 200
    assert history.json()["runs"][0]["run_id"] == response.json()["run"]["run_id"]
