from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.chat import active_requests
from app.main import create_app


def test_cancel_registered_stream_task():
    app = create_app()
    client = TestClient(app, headers={"X-Internal-Token": "test-internal-token"})
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
    client = TestClient(app, headers={"X-Internal-Token": "test-internal-token"})

    response = client.post("/api/chat/cancel?request_id=missing-request")

    assert response.status_code == 200
    assert response.json()["status"] == "not_found"
