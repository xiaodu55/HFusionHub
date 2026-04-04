"""Regression tests for the tenant_id migration.

Two backends migrate differently:
- ``MilvusClusterStore`` (real Milvus server) ALTERs in place via
  ``add_collection_field`` + backfill to tenant 1.
- ``MilvusLiteStore`` (embedded, cannot ALTER) runs a VERSIONED OFFLINE COPY:
  legacy rows are copied into ``<name>_v2`` stamped ``tenant_id=1``, validated
  (row/pk parity + tenant-1 retrieval), and only then is the active collection
  switched.  The legacy collection is retained as a rollback backup.

Both must make legacy rows tenant-1 retrievable and never leak to tenant 2.
"""

import json

import pytest

from app.core.vectorstore.milvus_lite import MilvusLiteStore
from app.core.vectorstore.milvus_cluster import MilvusClusterStore


class FakeMigrationClient:
    """In-memory Milvus stand-in exercising pagination, upsert and validation
    for the CLUSTER-style in-place ALTER migration."""

    def __init__(self, legacy_records):
        self.records = [dict(r) for r in legacy_records]
        self.added = []
        self.upserts = []

    def add_collection_field(self, collection_name, field_name, data_type):
        self.added.append({"field": field_name, "type": data_type})

    def load_collection(self, collection_name):
        return None

    def query(self, collection_name, filter, output_fields, limit=1000, offset=0):
        if "tenant_id == 0" in filter or "tenant_id == null" in filter:
            return [
                {"chunk_id": r["chunk_id"]}
                for r in self.records
                if r.get("tenant_id") is None
            ][:limit]
        start = offset
        end = min(offset + limit, len(self.records))
        return [dict(r) for r in self.records[start:end]]

    def upsert(self, collection_name, data):
        self.upserts.append(list(data))
        by_id = {r["chunk_id"]: r for r in self.records}
        for row in data:
            by_id[row["chunk_id"]] = row
        self.records = list(by_id.values())


class FakeV2Client:
    """In-memory Milvus stand-in for the LITE versioned offline copy migration."""

    def __init__(self, legacy_records, collection):
        self.legacy_records = [dict(r) for r in legacy_records]
        self.collection = collection
        self.v2 = collection + "_v2"
        self.v2_records = []          # rows currently stored in v2
        self.creates = []
        self.drops = []
        self.inserts = []
        self.v2_exists = False

    def has_collection(self, name):
        if name == self.v2:
            return self.v2_exists
        if name == self.collection:
            return True
        return False

    def describe_collection(self, name):
        if name == self.v2:
            return {"fields": [
                {"name": "chunk_id"},
                {"name": "document_id"},
                {"name": "knowledge_base_id"},
                {"name": "tenant_id"},
                {"name": "content"},
                {"name": "embedding"},
            ]}
        return {"fields": [
            {"name": "chunk_id"},
            {"name": "document_id"},
            {"name": "knowledge_base_id"},
            {"name": "content"},
            {"name": "embedding"},
        ]}

    def prepare_index_params(self):
        class _Idx:
            def add_index(self, **kwargs):
                return None
        return _Idx()

    def create_collection(self, collection_name, schema, index_params):
        self.creates.append(collection_name)
        self.v2_exists = True

    def drop_collection(self, collection_name):
        self.drops.append(collection_name)
        if collection_name == self.v2:
            self.v2_exists = False
            self.v2_records = []

    def load_collection(self, collection_name):
        return None

    def query(self, collection_name, filter, output_fields, limit=1000, offset=0):
        if collection_name == self.v2 and "tenant_id == 1" in filter:
            start = offset
            end = min(offset + limit, len(self.v2_records))
            return [dict(r) for r in self.v2_records[start:end]]
        start = offset
        end = min(offset + limit, len(self.legacy_records))
        return [dict(r) for r in self.legacy_records[start:end]]

    def insert(self, collection_name, data):
        self.inserts.append(list(data))
        self.v2_records.extend(dict(r) for r in data)
        self.v2_exists = True


def _record(i, kb=1):
    return {
        "chunk_id": f"chunk-{i}",
        "document_id": i % 3,
        "knowledge_base_id": kb,
        "content": f"content {i}",
        "block_type": "text",
        "outline_path": json.dumps(["doc"]),
        "metadata": json.dumps({"idx": i}),
        "embedding": [0.1] * 4,
    }


def _make_records(count):
    return [_record(i) for i in range(count)]


# ── Cluster: in-place ALTER + backfill ───────────────────────────────────────


@pytest.mark.parametrize("count", [1, 600, 1200])
def test_cluster_backfills_all_legacy_rows(count):
    """Every legacy row must be re-upserted with chunk_id AND tenant_id=1."""
    client = FakeMigrationClient(_make_records(count))
    store = MilvusClusterStore()
    store._client = client
    store._collection_name = "chunks"

    store._migrate_add_tenant_field(client)

    assert client.added[0]["field"] == "tenant_id"

    upserted = [row for page in client.upserts for row in page]
    assert len(upserted) == count
    assert all(row.get("tenant_id") == 1 for row in upserted)
    assert all(row.get("chunk_id") is not None for row in upserted)
    ids = [row["chunk_id"] for row in upserted]
    assert len(set(ids)) == count

    assert all(r.get("tenant_id") == 1 for r in client.records)


def test_cluster_migration_add_field_failure_raises():
    """Failure to add the field must raise so the caller can fail closed."""
    client = FakeMigrationClient(_make_records(1))

    def _boom(**kwargs):
        raise RuntimeError("cannot add field")

    client.add_collection_field = _boom
    store = MilvusClusterStore()
    store._client = client
    store._collection_name = "chunks"

    with pytest.raises(RuntimeError, match="add tenant_id"):
        store._migrate_add_tenant_field(client)


def test_cluster_migration_validation_failure_raises():
    """Rows still missing tenant_id after backfill must raise (fail closed)."""
    client = FakeMigrationClient(_make_records(1))

    def _validation(**kwargs):
        if "tenant_id == 0" in kwargs.get("filter", ""):
            return [{"chunk_id": "chunk-0"}]  # residual row found
        return []

    client.query = _validation
    store = MilvusClusterStore()
    store._client = client
    store._collection_name = "chunks"

    with pytest.raises(RuntimeError, match="still missing tenant_id"):
        store._migrate_add_tenant_field(client)


def test_cluster_ensure_collection_fail_closed_on_migration_error():
    """ensure_collection must return None and record _last_error on failure."""
    client = FakeMigrationClient(_make_records(1))

    def _boom(**kwargs):
        raise RuntimeError("cannot add field")

    client.add_collection_field = _boom
    store = MilvusClusterStore()
    store._client = client
    store._collection_name = "chunks"

    def _describe(name):
        return {"fields": [
            {"name": "chunk_id"}, {"name": "document_id"},
            {"name": "knowledge_base_id"}, {"name": "content"},
            {"name": "embedding", "params": {"dim": 4}},
        ]}

    client.has_collection = lambda name: True
    client.describe_collection = _describe

    result = store.ensure_collection()

    assert result is None
    assert "tenant_id migration failed" in store._last_error


# ── Lite: versioned offline copy to <name>_v2 ────────────────────────────────


@pytest.mark.parametrize("count", [1, 600, 1200])
def test_lite_migrates_legacy_rows_into_v2(count, tmp_path, monkeypatch):
    """Lite migration copies ALL rows into <name>_v2 stamped tenant_id=1 and
    switches the active collection; legacy collection is kept as backup."""
    from app.core.vectorstore import milvus_lite as ml
    monkeypatch.setattr(ml, "MILVUS_LITE_PATH", tmp_path / "milvus_test.db")

    client = FakeV2Client(_make_records(count), "chunks")
    store = MilvusLiteStore()
    store._client = client
    store._base_collection = "chunks"
    store._collection_name = "chunks"

    migrated = store._migrate_legacy_to_v2(client)

    assert migrated == "chunks_v2"
    assert client.v2_exists
    assert client.creates == ["chunks_v2"]
    # All rows copied with tenant_id=1.
    assert len(client.v2_records) == count
    assert all(r["tenant_id"] == 1 for r in client.v2_records)
    # Primary-key set preserved.
    assert {r["chunk_id"] for r in client.v2_records} == {r["chunk_id"] for r in client.legacy_records}
    # Active collection switched, marker persisted.
    assert store._collection_name == "chunks_v2"
    marker = ml._load_active_collection() if hasattr(ml, "_load_active_collection") else None
    assert json.loads((tmp_path / "milvus_test.db.active_collection.json").read_text(encoding="utf-8")) == {
        "active_collection": "chunks_v2"
    }


def test_lite_migration_failure_does_not_switch_read_path(tmp_path, monkeypatch):
    """If copying/validation fails, the read path must stay on the legacy
    collection (no v2 switch, service not-ready)."""
    from app.core.vectorstore import milvus_lite as ml
    monkeypatch.setattr(ml, "MILVUS_LITE_PATH", tmp_path / "milvus_test.db")

    client = FakeV2Client(_make_records(3), "chunks")

    def _boom(**kwargs):
        raise RuntimeError("simulated insert failure")

    client.insert = _boom
    store = MilvusLiteStore()
    store._client = client
    store._base_collection = "chunks"
    store._collection_name = "chunks"

    with pytest.raises(RuntimeError, match="simulated insert failure"):
        store._migrate_legacy_to_v2(client)

    # Read path NOT switched: still the legacy base collection.
    assert store._collection_name == "chunks"


def test_lite_migration_validation_failure_does_not_switch(tmp_path, monkeypatch):
    """A v2 whose data does not match the legacy set must fail validation and
    never be adopted as the active collection."""
    from app.core.vectorstore import milvus_lite as ml
    monkeypatch.setattr(ml, "MILVUS_LITE_PATH", tmp_path / "milvus_test.db")

    client = FakeV2Client(_make_records(2), "chunks")

    def _sabotaged_query(collection_name, filter, output_fields, limit=1000, offset=0):
        if collection_name == "chunks_v2" and "tenant_id == 1" in filter:
            return []  # v2 looks EMPTY to tenant 1 -> parity mismatch
        start = offset
        end = min(offset + limit, len(client.legacy_records))
        return [dict(r) for r in client.legacy_records[start:end]]

    client.query = _sabotaged_query
    store = MilvusLiteStore()
    store._client = client
    store._base_collection = "chunks"
    store._collection_name = "chunks"

    with pytest.raises(RuntimeError, match="validation failed"):
        store._migrate_legacy_to_v2(client)

    assert store._collection_name == "chunks"


def test_lite_migrates_legacy_set_larger_than_16384_rows(tmp_path, monkeypatch):
    """Validation must paginate the V2 primary keys so that a legacy set larger
    than the former single-query cap (16,384) is accepted as migrated.
    Regression for a false-negative parity check that would refuse service."""
    from app.core.vectorstore import milvus_lite as ml
    monkeypatch.setattr(ml, "MILVUS_LITE_PATH", tmp_path / "milvus_test.db")

    count = 16384 + 128  # exceeds the old fixed limit
    client = FakeV2Client(_make_records(count), "chunks")
    store = MilvusLiteStore()
    store._client = client
    store._base_collection = "chunks"
    store._collection_name = "chunks"

    migrated = store._migrate_legacy_to_v2(client)

    assert migrated == "chunks_v2"
    assert len(client.v2_records) == count
    assert {r["chunk_id"] for r in client.v2_records} == {r["chunk_id"] for r in client.legacy_records}
    assert store._collection_name == "chunks_v2"
