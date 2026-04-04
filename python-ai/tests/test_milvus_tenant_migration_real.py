"""REAL Milvus Lite versioned-migration integration tests (temp ``milvus_data.db``).

The embedded Milvus Lite backend cannot ALTER a collection in place
(``add_collection_field`` is UNIMPLEMENTED), so the store runs a VERSIONED
OFFLINE COPY: legacy rows are copied into ``<name>_v2`` stamped ``tenant_id=1``,
validated, and the active collection is atomically switched while the legacy
collection is kept as a rollback backup.  A fresh database (no collection, no
marker) creates the initial tenant-keyed collection directly.

These tests pin that real behaviour:

1. Fresh deployment auto-creates the tenant-keyed collection and serves writes.
2. After migration, tenant 1 retrieves the legacy rows and tenant 2 does not
   (verified through the store-level ``search()`` on the switched ``*_v2``).
3. A migration interrupted mid-copy does NOT switch the read path.
"""

import json

import pytest

from app.core.chunker.text_chunker import VectorChunk
from app.core.vectorstore.milvus_lite import MilvusLiteStore


@pytest.fixture
def real_lite_db(tmp_path, monkeypatch):
    """Isolated real Milvus Lite database file (temp milvus_data.db)."""
    import app.core.vectorstore.milvus_lite as ml
    import app.core.vectorstore.milvus_store as ms
    from app.core.vectorstore import factory

    factory.reset_vector_store()

    db_file = tmp_path / "milvus_data.db"

    _orig_ml_path = ml.MILVUS_LITE_PATH
    _orig_ms_path = ms.MILVUS_LITE_PATH

    monkeypatch.setattr(ml, "MILVUS_LITE_PATH", db_file.resolve())
    monkeypatch.setattr(ms, "MILVUS_LITE_PATH", db_file.resolve())

    store = MilvusLiteStore()
    store._client = None
    yield db_file, store

    monkeypatch.setattr(ml, "MILVUS_LITE_PATH", _orig_ml_path)
    monkeypatch.setattr(ms, "MILVUS_LITE_PATH", _orig_ms_path)
    factory.reset_vector_store()


def _embedding(i, dim):
    """A distinct sparse direction per record so cosine search is discriminative."""
    return [0.01 * (i + 1)] + [0.0] * (dim - 1)


def _legacy_record(i):
    """A row exactly as it exists in a PRE-tenant_id collection."""
    from app.core.vectorstore import milvus_lite as ml
    return {
        "chunk_id": f"legacy-{i}",
        "document_id": f"doc-{i % 3}",
        "knowledge_base_id": 1,
        "content": f"legacy content {i}",
        "block_type": "text",
        "outline_path": json.dumps(["doc"]),
        "metadata": json.dumps({"idx": i}),
        "embedding": _embedding(i, ml.config.EMBEDDING_DIMENSION),
    }


def _create_legacy_collection(client, collection):
    """Create a collection WITHOUT the tenant_id field and load legacy data."""
    from pymilvus import CollectionSchema, DataType, FieldSchema
    from app.core.vectorstore import milvus_lite as ml
    dim = ml.config.EMBEDDING_DIMENSION

    fields = [
        FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, is_primary=True, max_length=128),
        FieldSchema(name="document_id", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="knowledge_base_id", dtype=DataType.INT64),
        FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="block_type", dtype=DataType.VARCHAR, max_length=20),
        FieldSchema(name="outline_path", dtype=DataType.VARCHAR, max_length=2000),
        FieldSchema(name="metadata", dtype=DataType.VARCHAR, max_length=4000),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim),
    ]
    schema = CollectionSchema(fields=fields, description="legacy chunks")
    index_params = client.prepare_index_params()
    index_params.add_index(field_name="embedding", metric_type="COSINE",
                           index_type="IVF_FLAT", params={"nlist": 16})
    client.create_collection(collection_name=collection, schema=schema,
                             index_params=index_params)
    client.load_collection(collection)
    client.insert(collection_name=collection,
                  data=[_legacy_record(i) for i in range(3)])


def _set_tenant(tenant_id):
    from app.core.tenant.context import set_tenant_id
    set_tenant_id(tenant_id)


def _clear_tenant():
    from app.core.tenant.context import clear_tenant_id
    clear_tenant_id()


# ── P0: fresh deployment auto-creates the tenant-keyed collection ────────────


def test_real_fresh_deployment_creates_tenant_keyed_collection(real_lite_db):
    """A brand-new DB must auto-create the initial collection (WITH tenant_id)
    and be able to serve chunk inserts/reads — it must not return None."""
    db_file, store = real_lite_db
    store._base_collection = "chunks"
    store._collection_name = "chunks"
    client = store._get_client()
    assert client is not None
    assert not client.has_collection("chunks")  # pristine DB

    migrated_client = store.ensure_collection()
    assert migrated_client is client

    # Initial collection created with tenant_id, marker persisted to base name.
    assert client.has_collection("chunks")
    schema = client.describe_collection("chunks")
    assert "tenant_id" in {f.get("name") for f in schema.get("fields", [])}
    assert store._collection_name == "chunks"
    assert "chunks" in store._marker_path().read_text(encoding="utf-8")

    # New deployment serves writes + tenant-scoped reads immediately.
    _set_tenant(1)
    try:
        ok = store.insert_chunks(
            chunks=[VectorChunk(chunk_id="fresh-1", index=0, content="hello",
                                block_type="text", outline_path=["doc"])],
            embeddings=[_embedding(1, schema_emb_dim())],
            document_id="doc-fresh",
            knowledge_base_id=10,
        )
        assert ok
        hits = store.search(query_embedding=_embedding(1, schema_emb_dim()), top_k=5)
        assert any(h["chunk_id"] == "fresh-1" for h in hits)
    finally:
        _clear_tenant()


def schema_emb_dim():
    from app.core.vectorstore import milvus_lite as ml
    return ml.config.EMBEDDING_DIMENSION


# ── migration + store-level tenant isolation search ──────────────────────────


def test_real_migration_serves_legacy_rows_via_store_search(real_lite_db):
    """After migration the ACTIVE collection is switched to ``*_v2`` and the
    store's real ``search()`` read path honours tenant isolation: tenant 1
    returns the legacy rows, tenant 2 returns none."""
    db_file, store = real_lite_db
    store._base_collection = "chunks"
    store._collection_name = "chunks"
    client = store._get_client()
    assert client is not None

    _create_legacy_collection(client, "chunks")

    migrated_client = store.ensure_collection()
    assert migrated_client is client

    # Active collection switched to <name>_v2; legacy kept as backup.
    assert store._collection_name == "chunks_v2"
    assert client.has_collection("chunks")      # rollback backup retained
    assert client.has_collection("chunks_v2")   # active migrated collection
    schema_after = client.describe_collection("chunks_v2")
    assert "tenant_id" in {f.get("name") for f in schema_after.get("fields", [])}

    query_vec = _embedding(3, schema_emb_dim())  # closest to nothing/legacy-2

    _set_tenant(1)
    try:
        hits = store.search(query_embedding=query_vec, top_k=5)
        legacy_ids = sorted(h["chunk_id"] for h in hits)
        # The switched v2 read path returns all three migrated legacy rows.
        assert legacy_ids == ["legacy-0", "legacy-1", "legacy-2"]
    finally:
        _clear_tenant()

    _set_tenant(2)
    try:
        hits_2 = store.search(query_embedding=query_vec, top_k=5)
        assert hits_2 == []
    finally:
        _clear_tenant()


def test_real_migration_is_idempotent_on_restart(real_lite_db):
    """A second ensure_collection must reuse the validated v2, not re-migrate."""
    db_file, store = real_lite_db
    store._base_collection = "chunks"
    store._collection_name = "chunks"
    client = store._get_client()

    _create_legacy_collection(client, "chunks")

    assert store.ensure_collection() is client
    assert store._collection_name == "chunks_v2"

    # Simulate restart: a NEW store instance must pick up the persisted marker.
    fresh = MilvusLiteStore()
    fresh._client = client
    assert fresh._collection_name == "chunks_v2"
    assert fresh.ensure_collection() is client
    assert fresh._collection_name == "chunks_v2"


def test_real_interrupted_migration_does_not_switch_read_path(real_lite_db):
    """If the copy is interrupted, the active collection must stay on legacy."""
    db_file, store = real_lite_db
    store._base_collection = "chunks"
    store._collection_name = "chunks"
    client = store._get_client()

    _create_legacy_collection(client, "chunks")

    # Simulate an interruption: inserts into v2 fail part-way.
    original_insert = client.insert

    def _boom_insert(collection_name, data):
        if collection_name == "chunks_v2":
            raise RuntimeError("simulated interruption during migration")
        return original_insert(collection_name, data)

    client.insert = _boom_insert
    try:
        result = store.ensure_collection()
    finally:
        client.insert = original_insert

    assert result is None
    assert "tenant_id migration failed" in (store._last_error or "")
    # Read path NOT switched: still the legacy collection (marker not written).
    assert store._collection_name == "chunks"
    marker = store._marker_path()
    assert not marker.exists() or "chunks_v2" not in marker.read_text(encoding="utf-8")