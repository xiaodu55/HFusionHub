from fastapi.testclient import TestClient

from app.main import create_app
from app.utils.config import config


def test_runtime_overview_requires_the_internal_token():
    client = TestClient(create_app())

    assert client.get("/api/runtime/overview").status_code == 401


def test_runtime_overview_is_safe_and_reports_runtime_state(monkeypatch):
    import app.api.runtime as runtime

    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(config, "DEEPSEEK_MODEL", "deepseek-test")
    monkeypatch.setattr(config, "EMBEDDING_ALLOW_FALLBACK", False)
    monkeypatch.setattr(runtime, "_probe_ollama", lambda: (True, {"qwen2.5:latest", "qwen3-embedding:8b-fp16"}))
    monkeypatch.setattr(
        runtime,
        "vector_store_status",
        lambda: {"ready": True, "collection": "test_chunks", "collection_exists": True},
    )

    client = TestClient(create_app())
    response = client.get(
        "/api/runtime/overview",
        headers={"X-Internal-Token": "test-internal-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["llm"]["model"] == "deepseek-test"
    assert payload["embedding"]["state"] == "ready"
    assert payload["vector_store"]["ready"] is True
    assert "test-key" not in str(payload)
