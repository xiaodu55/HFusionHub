"""Regression tests for MilvusClusterStore.all_chunks() pagination.

Previously ``limit``/``offset`` were embedded inside the Milvus filter
expression (invalid) and ``offset`` was not advanced when a knowledge_base_id
filter was present, so paginating >1000 chunks would fail or loop forever.
"""
import json

from app.core.vectorstore.milvus_cluster import MilvusClusterStore


class FakeMilvusClient:
    """In-memory stand-in for the pymilvus MilvusClient.query()."""

    def __init__(self, records):
        self.records = records
        self.calls = []

    def has_collection(self, name):
        return True

    def load_collection(self, name):
        return None

    def query(self, collection_name, filter, output_fields, limit=1000, offset=0):
        self.calls.append(
            {"filter": filter, "limit": limit, "offset": offset}
        )
        start = offset
        end = min(offset + limit, len(self.records))
        return self.records[start:end]


def _record(i, kb=1):
    return {
        "chunk_id": f"chunk-{i}",
        "document_id": i % 3,
        "knowledge_base_id": kb,
        "content": f"content {i}",
        "block_type": "text",
        "outline_path": json.dumps(["doc"]),
        "metadata": json.dumps({"idx": i}),
    }


def _store_with(records):
    client = FakeMilvusClient(records)
    store = MilvusClusterStore()
    store._client = client
    store._collection_name = "chunks"
    return store, client


def test_all_chunks_paginates_with_kb_filter():
    """Over 1000 chunks with a KB filter must paginate with advancing offset."""
    records = [_record(i, 7) for i in range(1500)]
    store, client = _store_with(records)

    grouped = store.all_chunks(knowledge_base_id=7)

    # All records must be returned exactly once.
    all_chunk_ids = [
        c["chunk_id"] for doc_chunks in grouped.values() for c in doc_chunks
    ]
    assert len(all_chunk_ids) == 1500
    assert len(set(all_chunk_ids)) == 1500

    # filter must remain a pure expression (no limit/offset embedded) and
    # must scope to the active tenant (hard isolation boundary).
    assert all(call["filter"] == "tenant_id == 1 and knowledge_base_id == 7" for call in client.calls)
    # offsets must advance: 0 then 1000.
    offsets = [call["offset"] for call in client.calls]
    assert offsets == [0, 1000]
    # limit passed as a query parameter.
    assert all(call["limit"] == 1000 for call in client.calls)


def test_all_chunks_paginates_without_filter():
    """Without a KB filter, offset must also advance across pages."""
    records = [_record(i, 1) for i in range(1200)]
    store, client = _store_with(records)

    grouped = store.all_chunks()
    all_chunk_ids = [
        c["chunk_id"] for doc_chunks in grouped.values() for c in doc_chunks
    ]
    assert len(all_chunk_ids) == 1200
    assert [call["offset"] for call in client.calls] == [0, 1000]


def test_all_chunks_single_page():
    """Fewer than one page requires a single query call."""
    records = [_record(i, 2) for i in range(10)]
    store, client = _store_with(records)

    grouped = store.all_chunks(knowledge_base_id=2)
    all_chunk_ids = [
        c["chunk_id"] for doc_chunks in grouped.values() for c in doc_chunks
    ]
    assert len(all_chunk_ids) == 10
    assert len(client.calls) == 1
    assert client.calls[0]["offset"] == 0
