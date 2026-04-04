"""Tenant-isolation regression tests for the JSON co-store.

Ensures the co-store physical layout is ``tenant_id -> document_id -> chunks``
and that read/write/delete all anchor at the ACTIVE tenant root — so a
cross-tenant operation (e.g. tenant B deleting a document id owned by A) can
never touch another tenant's fallback rows.
"""

import json

from app.core.tenant.context import set_tenant_id, clear_tenant_id
from app.core.vectorstore import milvus_lite
from app.core.vectorstore.milvus_lite import MilvusLiteStore


def _store(tmp_path, monkeypatch):
    path = tmp_path / "chunks_store.json"
    monkeypatch.setattr(milvus_lite, "CHUNKS_STORE_PATH", path)
    return MilvusLiteStore()


def test_co_store_write_is_tenant_rooted(tmp_path, monkeypatch):
    """_save_to_co_store writes under the ACTIVE tenant's root, not globally."""
    set_tenant_id(7)
    try:
        s = _store(tmp_path, monkeypatch)
        recs = [{"chunk_id": "7_0", "document_id": "d1", "tenant_id": 7,
                 "content": "t7", "metadata": "{}"}]
        s._save_to_co_store("d1", recs)

        with open(milvus_lite.CHUNKS_STORE_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        assert "7" in raw
        assert raw["7"]["d1"] == recs
    finally:
        clear_tenant_id()


def test_cross_tenant_delete_does_not_touch_other_tenant(tmp_path, monkeypatch):
    """Tenant B deleting a document id must NOT delete tenant A's co-store rows."""
    path = tmp_path / "chunks_store.json"

    # Seed tenant A's data under its root.
    set_tenant_id(1)
    try:
        monkeypatch.setattr(milvus_lite, "CHUNKS_STORE_PATH", path)
        a = MilvusLiteStore()
        a._save_to_co_store("shared-doc", [
            {"chunk_id": "a_0", "document_id": "shared-doc", "tenant_id": 1,
             "content": "tenant A", "metadata": "{}"},
        ])
    finally:
        clear_tenant_id()

    # Tenant B deletes the SAME document id — its own root.
    set_tenant_id(2)
    try:
        b = MilvusLiteStore()
        # Exercise only the JSON co-store delete path (no live Milvus needed).
        b._get_client = lambda: None
        assert b.delete_document_chunks("shared-doc") is True
    finally:
        clear_tenant_id()

    # Tenant A's row must survive.
    set_tenant_id(1)
    try:
        a2 = MilvusLiteStore()
        assert a2._load_co_store()["1"]["shared-doc"][0]["content"] == "tenant A"
    finally:
        clear_tenant_id()


def test_read_anchors_to_tenant_root(tmp_path, monkeypatch):
    """get_document_chunks / all_chunks return only the active tenant's rows."""
    set_tenant_id(1)
    try:
        s = _store(tmp_path, monkeypatch)
        s._save_to_co_store("doc-a", [
            {"chunk_id": "a_0", "document_id": "doc-a", "tenant_id": 1,
             "knowledge_base_id": 11, "content": "A", "block_type": "P", "metadata": "{}"},
        ])
    finally:
        clear_tenant_id()

    set_tenant_id(2)
    try:
        s = _store(tmp_path, monkeypatch)
        res = s.get_document_chunks("doc-a")
        assert res["code"] == 200
        assert res["data"]["records"] == []
        assert s.all_chunks() == {}
    finally:
        clear_tenant_id()


def test_legacy_flat_layout_migrates_to_tenant_1(tmp_path, monkeypatch):
    """A legacy document_id-keyed file is normalized into tenant 1 on load."""
    set_tenant_id(1)
    try:
        path = tmp_path / "chunks_store.json"
        original = {
            "legacy-doc": [{
                "chunk_id": "l_0", "document_id": "legacy-doc", "tenant_id": 1,
                "content": "old", "metadata": "{}",
            }],
        }
        path.write_text(json.dumps(original), encoding="utf-8")
        monkeypatch.setattr(milvus_lite, "CHUNKS_STORE_PATH", path)

        s = MilvusLiteStore()
        store = s._load_co_store()
        assert store["1"]["legacy-doc"][0]["chunk_id"] == "l_0"
    finally:
        clear_tenant_id()