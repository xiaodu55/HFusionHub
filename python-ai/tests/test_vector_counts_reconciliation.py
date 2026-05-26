"""Tests for the vector-store reconciliation endpoint /api/stats/vector-counts.

The Java backend polls this endpoint to compare Milvus entity counts against
its durable ``document_chunk`` table, so the endpoint must stay tenant-scoped
(fail-closed) and must never turn a transient Milvus read failure into a
fabricated zero (which would trigger a false drift alarm).
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app

TOKEN = {"X-Internal-Token": "test-internal-token", "X-Tenant-Id": "1"}


def test_vector_counts_requires_internal_token_and_tenant():
    client = TestClient(create_app())
    # No token -> 401.
    assert client.post("/api/stats/vector-counts", json={"knowledge_base_ids": [1]}).status_code == 401
    # Token but no tenant context -> fail-closed 400.
    assert (
        client.post(
            "/api/stats/vector-counts",
            headers={"X-Internal-Token": "test-internal-token"},
            json={"knowledge_base_ids": [1]},
        ).status_code
        == 400
    )


@patch("app.core.vectorstore.milvus_store.count_chunks")
def test_vector_counts_returns_per_kb_entity_counts(mock_count):
    mock_count.side_effect = lambda knowledge_base_id: knowledge_base_id * 10
    client = TestClient(create_app())
    resp = client.post(
        "/api/stats/vector-counts",
        headers=TOKEN,
        json={"knowledge_base_ids": [1, 2, 3]},
    )
    assert resp.status_code == 200
    assert resp.json()["counts"] == {"1": 10, "2": 20, "3": 30}


@patch("app.core.vectorstore.milvus_store.count_chunks")
def test_vector_counts_marks_read_failure_as_minus_one(mock_count):
    def boom(**kwargs):
        raise RuntimeError("milvus unavailable")

    mock_count.side_effect = boom
    client = TestClient(create_app())
    resp = client.post(
        "/api/stats/vector-counts",
        headers=TOKEN,
        json={"knowledge_base_ids": [7]},
    )
    # Still 200 with an explicit failure marker — never a silent zero.
    assert resp.status_code == 200
    assert resp.json()["counts"] == {"7": -1}


def test_vector_counts_rejects_non_integer_kb_ids():
    client = TestClient(create_app())
    resp = client.post(
        "/api/stats/vector-counts",
        headers=TOKEN,
        json={"knowledge_base_ids": ["not-a-number"]},
    )
    assert resp.status_code == 422
