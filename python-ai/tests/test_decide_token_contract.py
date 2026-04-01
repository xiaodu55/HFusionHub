"""Decide-endpoint execution-token contract — exactly-once across replicas.

MySQL is the single source of truth.  The /decide endpoint must consume the
one-time execution token BEFORE executing the approved tool; any replay /
cross-replica attempt is rejected with 409 and the tool is not run.
"""

import hashlib
import json
import uuid
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.chat import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def _approved_payload(**overrides):
    tool_input = {"content": "note body"}
    canonical = json.dumps(tool_input, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"))
    payload = {
        "approval_id": str(uuid.uuid4()),
        "decision": "approved",
        "user_id": 1,
        "knowledge_base_id": 10,
        "tool_name": "write_note",
        "tool_input": tool_input,
        "expected_tool_input_hash": hashlib.sha256(
            canonical.encode("utf-8")).hexdigest(),
        "query": "please write a note",
        "history": [],
        "execution_token": "tok-0001",
    }
    payload.update(overrides)
    return payload


def test_approved_without_token_is_rejected():
    payload = _approved_payload(execution_token=None)
    resp = client.post("/api/agent/v1/chat/decide", json=payload)
    assert resp.status_code == 409
    assert "execution token" in resp.json()["detail"]


def test_approved_consumes_token_and_executes_once():
    with patch("app.core.tools.execution_token.consume_execution_token",
               return_value=True) as consume:
        resp = client.post("/api/agent/v1/chat/decide", json=_approved_payload())
    consume.assert_called_once()
    # write_note's durable persistence is not configured → tool_error, but the
    # point is the approved flow was allowed to proceed (HTTP 200).
    assert resp.status_code == 200
    assert resp.json()["status"] in ("tool_error", "completed")


def test_replay_cross_replica_rejected():
    # First replica consumes → executes.  Second replica sees consumed=false
    # (MySQL is shared) → 409, never reaches the tool.
    with patch("app.core.tools.execution_token.consume_execution_token",
               side_effect=[True, False]):
        first = client.post("/api/agent/v1/chat/decide", json=_approved_payload())
        second = client.post("/api/agent/v1/chat/decide", json=_approved_payload())
    assert first.status_code == 200
    assert second.status_code == 409


def test_approved_with_bad_hash_rejected_before_consume():
    with patch("app.core.tools.execution_token.consume_execution_token") as consume:
        resp = client.post(
            "/api/agent/v1/chat/decide",
            json=_approved_payload(expected_tool_input_hash="0" * 64),
        )
    consume.assert_not_called()
    assert resp.status_code == 409
