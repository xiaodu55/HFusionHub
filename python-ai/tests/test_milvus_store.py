"""Tests for the milvus_store backward-compatible facade and vector store status."""

from app.core.vectorstore import milvus_store
from app.core.vectorstore import factory
from app.core.vectorstore.milvus_lite import MilvusLiteStore


def test_vector_store_status_reports_connection_failure(monkeypatch):
    """When the underlying store cannot connect, status reports the error."""
    monkeypatch.setattr(milvus_store, "_last_connection_error", "directory is locked")
    monkeypatch.setattr(milvus_store, "get_milvus_client", lambda: None)

    status = milvus_store.vector_store_status()

    assert status["ready"] is False
    assert status["error"] == "directory is locked"


def test_create_collection_reuses_compatible_collection():
    """create_collection returns existing client when schema is compatible."""
    factory.reset_vector_store()

    class FakeClient:
        create_calls = 0

        def has_collection(self, name):
            return True

        def describe_collection(self, name):
            return {
                "fields": [
                    {"name": "chunk_id"},
                    {"name": "document_id"},
                    {"name": "knowledge_base_id"},
                    {"name": "content"},
                    {
                        "name": "embedding",
                        "params": {"dim": milvus_store.config.EMBEDDING_DIMENSION},
                    },
                ]
            }

        def create_collection(self, **kwargs):
            self.create_calls += 1

    client = FakeClient()
    store = MilvusLiteStore()
    store._client = client
    factory._store = store

    try:
        result = store.ensure_collection()

        assert result is client
        assert client.create_calls == 0
    finally:
        factory.reset_vector_store()


def test_create_collection_refuses_to_drop_incompatible_collection():
    """create_collection returns None when schema is incompatible (no drop)."""
    factory.reset_vector_store()

    class FakeIndexParams:
        def add_index(self, **kwargs):
            return None

    class FakeClient:
        def __init__(self):
            self.exists = True
            self.drop_calls = 0
            self.create_calls = 0

        def has_collection(self, name):
            return self.exists

        def describe_collection(self, name):
            return {
                "fields": [
                    {"name": "chunk_id"},
                    {"name": "document_id"},
                    {"name": "knowledge_base_id"},
                    {"name": "content"},
                ]
            }

        def drop_collection(self, name):
            self.drop_calls += 1
            self.exists = False

        def prepare_index_params(self):
            return FakeIndexParams()

        def create_collection(self, **kwargs):
            self.create_calls += 1
            self.exists = True

    client = FakeClient()
    store = MilvusLiteStore()
    store._client = client
    factory._store = store

    try:
        result = store.ensure_collection()

        assert result is None
        assert client.drop_calls == 0
        assert client.create_calls == 0
    finally:
        factory.reset_vector_store()
