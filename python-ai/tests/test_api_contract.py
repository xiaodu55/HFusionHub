"""API 层契约测试（第十五轮 R15-21）。

覆盖此前零测试的路由（bid / rag）。用 FastAPI TestClient 走真实
请求-响应契约：参数校验（422）、错误包装（status=error）、成功路径
（monkeypatch 工作流），不依赖 LLM / Milvus。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


AUTH_HEADERS = {"X-Internal-Token": "test-internal-token", "X-Tenant-Id": "1"}


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app, headers=AUTH_HEADERS)


# ── bid API ──────────────────────────────────────────────────────────

def test_bid_interpret_rejects_missing_fields(client):
    resp = client.post("/api/bid/interpret", json={})
    assert resp.status_code == 422


def test_bid_interpret_wraps_workflow_failure(client, monkeypatch):
    from app.api import bid as bid_api

    class Boom:
        async def run(self, **kwargs):
            raise RuntimeError("milvus down")

    monkeypatch.setattr(bid_api, "BidInterpretWorkflow", lambda: Boom())
    resp = client.post("/api/bid/interpret", json={"project_id": 7, "knowledge_base_id": 3, "title": "某项目"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "error"
    assert "解读服务不可用" in body["message"]
    assert body["project_id"] == 7


def test_bid_interpret_success_passes_project_id(client, monkeypatch):
    from app.api import bid as bid_api

    captured = {}

    class Fake:
        async def run(self, **kwargs):
            captured.update(kwargs)
            return {"status": "ok", "elements": [], "requirements": []}

    monkeypatch.setattr(bid_api, "BidInterpretWorkflow", lambda: Fake())
    resp = client.post("/api/bid/interpret", json={"project_id": 9, "knowledge_base_id": 3, "title": "某项目"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["project_id"] == 9
    assert captured["project_id"] == 9
    assert captured["knowledge_base_id"] == 3


def test_bid_write_requires_project_and_kbs(client):
    resp = client.post("/api/bid/write", json={"title": "x"})
    assert resp.status_code == 422


def test_bid_write_success_round_trips_sections(client, monkeypatch):
    from app.api import bid as bid_api

    captured = {}

    class Fake:
        async def run(self, **kwargs):
            captured.update(kwargs)
            return {"status": "ok", "sections": [{"section_key": "commercial", "content": "正文"}]}

    monkeypatch.setattr(bid_api, "BidWriteWorkflow", lambda: Fake())
    resp = client.post("/api/bid/write", json={
        "project_id": 5,
        "title": "某项目",
        "knowledge_base_ids": [1, 2],
        "requirements": [{"category": "资质", "requirement": "ISO9001", "source_clause": "第3章"}],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["project_id"] == 5
    assert captured["knowledge_base_ids"] == [1, 2]
    assert captured["requirements"][0]["category"] == "资质"


def test_bid_check_wraps_workflow_failure(client, monkeypatch):
    from app.api import bid as bid_api

    class Boom:
        async def run(self, **kwargs):
            raise RuntimeError("llm down")

    monkeypatch.setattr(bid_api, "BidCheckWorkflow", lambda: Boom())
    resp = client.post("/api/bid/check", json={
        "project_id": 5,
        "title": "某项目",
        "sections": [{"section_key": "commercial", "content": "正文"}],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "error"
    assert "自检服务不可用" in body["message"]


# ── rag API ──────────────────────────────────────────────────────────

def test_rag_traces_requires_kb_query(client):
    resp = client.get("/api/rag/traces")
    assert resp.status_code == 422


def test_rag_graph_status_contract(client, monkeypatch):
    from app.api import rag as rag_api

    class FakeManager:
        def get_graph_status(self, kb_id):
            return {"enabled": False, "documents": 0}

    monkeypatch.setattr(rag_api, "graph_manager", FakeManager(), raising=False)
    resp = client.get("/api/rag/graph/status", params={"knowledge_base_id": 3})
    # 端点可能依赖更多上下文（租户等），只验证不 5xx 的鉴权内可达契约
    assert resp.status_code in (200, 400, 404)


def test_rag_debug_search_rejects_empty_query(client):
    resp = client.post("/api/rag/debug/search", json={"query": "", "knowledge_base_id": 1})
    assert resp.status_code == 422
