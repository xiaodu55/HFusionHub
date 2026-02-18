from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import create_app
from app.utils.config import config
from app.utils.validators import validate_file_path


def test_business_routes_require_the_java_service_token():
    client = TestClient(create_app())

    assert client.get("/health").status_code == 200
    assert client.get("/api/rag/traces").status_code == 401
    assert client.get(
        "/api/rag/traces", headers={"X-Internal-Token": "test-internal-token"}
    ).status_code == 422  # Authenticated, but the required KB scope is absent.


def test_vectorization_path_must_stay_under_document_storage(tmp_path, monkeypatch):
    root = tmp_path / "uploads"
    root.mkdir()
    allowed = root / "allowed.md"
    allowed.write_text("safe", encoding="utf-8")
    outside = tmp_path / "outside.md"
    outside.write_text("private", encoding="utf-8")
    monkeypatch.setattr(config, "DOCUMENT_STORAGE_ROOT", str(root))

    assert validate_file_path(str(allowed)) == str(allowed.resolve())
    try:
        validate_file_path(str(outside))
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("files outside DOCUMENT_STORAGE_ROOT must be rejected")
