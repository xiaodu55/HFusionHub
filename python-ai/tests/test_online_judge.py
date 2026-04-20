"""
Tests for C3 — online answer judge endpoint (LLM-as-judge).
"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.utils.config import config


@pytest.fixture
def client():
    config.INTERNAL_API_TOKEN = "test-internal-token"
    return TestClient(create_app())


def _fake_result(status):
    _Result = type("_Result", (), {
        "status": status,
        "overall_score": 0.85,
        "scores": {"completeness": 0.9, "accuracy": 0.8, "clarity": 0.85},
        "strategy_used": "llm_based",
        "error_message": None,
    })
    return _Result()


def _headers():
    return {"X-Internal-Token": "test-internal-token", "X-Tenant-Id": "1"}


def test_judge_answer_scores_with_mock_evaluator(client, monkeypatch):
    from app.core.rag import answer_quality_evaluator as aqe

    class FakeEvaluator:
        async def evaluate(self, sample):
            assert sample.ground_truth is None
            assert sample.query == "什么是虚拟线程？"
            assert sample.response == "虚拟线程是 Java 的轻量级线程。"
            return _fake_result(aqe.EvaluationStatus.COMPLETED)

    monkeypatch.setattr(aqe, "get_evaluator", lambda *a, **k: FakeEvaluator())

    response = client.post(
        "/api/rag/evaluate/answer-judge",
        headers=_headers(),
        json={
            "query": "什么是虚拟线程？",
            "answer": "虚拟线程是 Java 的轻量级线程。",
            "context": "虚拟线程是 JEP 444 引入的轻量级线程。",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["overall_score"] == 0.85
    assert payload["verdict"] == "good"
    assert payload["scores"]["accuracy"] == 0.8


def test_judge_answer_requires_query_and_answer(client):
    response = client.post(
        "/api/rag/evaluate/answer-judge",
        headers=_headers(),
        json={"query": "", "answer": "x"},
    )

    assert response.status_code == 422


def test_judge_answer_requires_internal_token(client):
    response = client.post(
        "/api/rag/evaluate/answer-judge",
        json={"query": "q", "answer": "a"},
    )

    assert response.status_code in (401, 403)
