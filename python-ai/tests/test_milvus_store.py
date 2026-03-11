from app.core.vectorstore import milvus_store


def test_vector_store_status_reports_connection_failure(monkeypatch):
    monkeypatch.setattr(milvus_store, "get_milvus_client", lambda: None)
    monkeypatch.setattr(milvus_store, "_last_connection_error", "directory is locked")

    status = milvus_store.vector_store_status()

    assert status["ready"] is False
    assert status["error"] == "directory is locked"


def test_create_collection_reuses_compatible_collection(monkeypatch):
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
    monkeypatch.setattr(milvus_store, "get_milvus_client", lambda: client)

    result = milvus_store.create_collection()

    assert result is client
    assert client.create_calls == 0


def test_create_collection_recreates_incompatible_collection(monkeypatch):
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
    monkeypatch.setattr(milvus_store, "get_milvus_client", lambda: client)

    result = milvus_store.create_collection()

    assert result is client
    assert client.drop_calls == 1
    assert client.create_calls == 1
