import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.chat import (
    CHAT_HISTORY_MAX_ITEMS,
    CHAT_MESSAGE_MAX_LENGTH,
    SYSTEM_PROMPT_MAX_LENGTH,
    _agent_chunk_to_sse,
    _build_history_with_system_prompt,
    active_requests,
)
from app.main import create_app


def _sse_payload(event: str):
    assert event.startswith("data: ")
    return json.loads(event.removeprefix("data: ").strip())


def test_agent_chunk_to_sse_wraps_content():
    event = _agent_chunk_to_sse("hello")

    assert _sse_payload(event) == {"content": "hello"}


def test_agent_chunk_to_sse_preserves_sources():
    event = _agent_chunk_to_sse('{"sources":[{"document_id":1}]}')

    assert _sse_payload(event) == {"sources": [{"document_id": 1}]}


def test_agent_chunk_to_sse_drops_evaluation_events():
    event = _agent_chunk_to_sse('{"content":"","evaluation":{"score":0.9}}')

    assert event is None


def test_cancel_registered_stream_task():
    app = create_app()
    client = TestClient(app, headers={"X-Internal-Token": "test-internal-token", "X-Tenant-Id": "1"})
    task = MagicMock()
    task.done.return_value = False
    active_requests["test-request"] = task

    response = client.post("/api/chat/cancel?request_id=test-request")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    task.cancel.assert_called_once()
    assert "test-request" not in active_requests


def test_cancel_unknown_stream_task_returns_not_found():
    app = create_app()
    client = TestClient(app, headers={"X-Internal-Token": "test-internal-token", "X-Tenant-Id": "1"})

    response = client.post("/api/chat/cancel?request_id=missing-request")

    assert response.status_code == 200
    assert response.json()["status"] == "not_found"


def test_chat_rejects_oversized_message():
    app = create_app()
    client = TestClient(app, headers={"X-Internal-Token": "test-internal-token", "X-Tenant-Id": "1"})

    response = client.post("/api/chat", json={"message": "x" * (CHAT_MESSAGE_MAX_LENGTH + 1)})

    assert response.status_code == 422


def test_chat_rejects_oversized_history():
    app = create_app()
    client = TestClient(app, headers={"X-Internal-Token": "test-internal-token", "X-Tenant-Id": "1"})
    history = [{"role": "user", "content": "hello"}] * (CHAT_HISTORY_MAX_ITEMS + 1)

    response = client.post("/api/chat", json={"message": "hello", "history": history})

    assert response.status_code == 422


def test_history_drops_only_the_duplicate_current_user_turn():
    history = [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "first answer"},
        {"role": "user", "content": "current question"},
    ]

    result = _build_history_with_system_prompt(history, None, "current question")

    assert result == history[:-1]


def test_history_keeps_a_previous_matching_question():
    history = [
        {"role": "user", "content": "repeat question"},
        {"role": "assistant", "content": "previous answer"},
    ]

    result = _build_history_with_system_prompt(history, None, "repeat question")

    assert result == history


# ── system_prompt contract (max 8000, bypasses 4000-char ChatMessage limit) ──

@pytest.fixture
def mock_agent(monkeypatch):
    """Replace the agent factory so tests never hit a real LLM/Milvus."""
    from app.core.agent import AgentResponse

    captured = {"history": None}

    class _MockAgent:
        async def run(self, **kwargs):
            captured["history"] = kwargs.get("history")
            return AgentResponse(content="ok", model="deepseek-v4-flash", token_count=1)

        async def run_stream(self, **kwargs):
            yield "data: ok"

    monkeypatch.setattr("app.api.chat.get_agent", lambda **kw: _MockAgent())
    return captured


def test_chat_accepts_8000_char_system_prompt(mock_agent):
    """The exact 8000-char boundary must be accepted (was 422 before fix)."""
    app = create_app()
    client = TestClient(app, headers={"X-Internal-Token": "test-internal-token", "X-Tenant-Id": "1"})
    sp = "A" * SYSTEM_PROMPT_MAX_LENGTH

    response = client.post("/api/chat", json={"message": "hi", "system_prompt": sp, "history": []})

    assert response.status_code == 200
    # system_prompt must reach the agent as a system message, intact
    assert mock_agent["history"] is not None
    assert mock_agent["history"][0]["role"] == "system"
    assert mock_agent["history"][0]["content"] == sp


def test_chat_accepts_4001_char_system_prompt(mock_agent):
    """The 4001-8000 band that used to fail must now pass via system_prompt."""
    app = create_app()
    client = TestClient(app, headers={"X-Internal-Token": "test-internal-token", "X-Tenant-Id": "1"})

    response = client.post("/api/chat", json={"message": "hi", "system_prompt": "B" * 4001, "history": []})

    assert response.status_code == 200


def test_chat_rejects_8001_char_system_prompt():
    """Over the 8000 boundary → 422."""
    app = create_app()
    client = TestClient(app, headers={"X-Internal-Token": "test-internal-token", "X-Tenant-Id": "1"})

    response = client.post("/api/chat", json={"message": "hi", "system_prompt": "C" * (SYSTEM_PROMPT_MAX_LENGTH + 1), "history": []})

    assert response.status_code == 422


def test_chat_still_rejects_oversized_history_entry():
    """The 4000-char limit on regular history entries must be preserved."""
    app = create_app()
    client = TestClient(app, headers={"X-Internal-Token": "test-internal-token", "X-Tenant-Id": "1"})
    history = [{"role": "user", "content": "E" * (CHAT_MESSAGE_MAX_LENGTH + 1)}]

    response = client.post("/api/chat", json={"message": "hi", "history": history})

    assert response.status_code == 422


def test_agent_v1_accepts_8000_char_system_prompt(mock_agent):
    """Agent V1 endpoint must accept the full 8000-char system_prompt."""
    app = create_app()
    client = TestClient(app, headers={"X-Internal-Token": "test-internal-token", "X-Tenant-Id": "1"})

    response = client.post("/api/agent/v1/chat", json={
        "message": "hi",
        "knowledge_base_id": 1,
        "user_id": 1,
        "system_prompt": "D" * SYSTEM_PROMPT_MAX_LENGTH,
        "history": [],
    })

    assert response.status_code == 200
    assert mock_agent["history"][0]["role"] == "system"
    assert len(mock_agent["history"][0]["content"]) == SYSTEM_PROMPT_MAX_LENGTH
