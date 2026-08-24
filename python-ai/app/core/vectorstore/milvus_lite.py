"""
Milvus Lite vector store — single-process, file-backed, for development.

This module wraps the embedded Milvus Lite client in a class that conforms to
:class:`VectorStoreProtocol`.  It is the default backend when
``VECTOR_STORE_MODE=lite`` (or unset).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from pymilvus import (
    CollectionSchema,
    DataType,
    FieldSchema,
    MilvusClient,
)

from app.core.chunker.text_chunker import VectorChunk
from app.core.tenant.context import require_tenant_id
from app.core.vectorstore.base import VectorStoreProtocol, VectorStoreStatus
from app.utils.config import config

logger = logging.getLogger(__name__)

# Resolve relative storage paths from the Python service root, not cwd.
PYTHON_AI_ROOT = Path(__file__).resolve().parents[3]
MILVUS_LITE_PATH = Path(config.MILVUS_LITE_PATH)
if not MILVUS_LITE_PATH.is_absolute():
    MILVUS_LITE_PATH = (PYTHON_AI_ROOT / MILVUS_LITE_PATH).resolve()

# JSON co-store path
_chunks_store_env = os.getenv("CHUNKS_STORE_PATH")
CHUNKS_STORE_PATH = (
    Path(_chunks_store_env).expanduser()
    if _chunks_store_env
    else (PYTHON_AI_ROOT / "data" / "chunks_store.json")
)


def _migrate_co_store_layout(store: dict[str, Any]) -> dict[str, Any]:
    """Normalize the JSON co-store to the tenant-keyed physical layout.

    Legacy stores were keyed by ``document_id`` (value = list of chunks).  The
    hardened layout is ``tenant_id -> document_id -> chunks`` so that every
    read/write/delete anchors at the ACTIVE tenant root — a cross-tenant
    operation can never touch another tenant's rows.  Legacy rows are folded
    into tenant 1 (the historical default), which matches the Milvus backfill.
    """
    if not isinstance(store, dict):
        return {}
    is_legacy = any(isinstance(v, list) for v in store.values())
    if not is_legacy:
        return store
    migrated: dict[str, Any] = {}
    for doc_id, chunks in store.items():
        if not isinstance(chunks, list):
            continue
        for c in chunks:
            tenant = str(int(c.get("tenant_id", 1)))
            doc = str(c.get("document_id", doc_id))
            migrated.setdefault(tenant, {}).setdefault(doc, []).append(c)
    return migrated


def _co_store_tenant_root(store: dict[str, Any], tenant_key: str) -> dict[str, list[dict]]:
    """Return the tenant-keyed root of the co-store for a concrete tenant id.

    Lazily creates the bucket so writes can anchor to an empty tenant without
    touching any sibling tenant's data.
    """
    root = store.get(tenant_key)
    if not isinstance(root, dict):
        root = {}
        store[tenant_key] = root
    return root


class MilvusLiteStore(VectorStoreProtocol):
    """Embedded Milvus Lite backend (file-backed, single-process)."""

    _V2_SUFFIX = "_v2"
    _ACTIVE_COLLECTION_MARKER = ".active_collection.json"

    def __init__(self) -> None:
        self._base_collection = config.MILVUS_COLLECTION
        self._collection_name = self._load_active_collection() or self._base_collection
        self._client: MilvusClient | None = None
        self._lock = threading.RLock()
        self._last_error: str | None = None

    # ── Connection ───────────────────────────────────────────────────────────

    def _get_client(self) -> MilvusClient | None:
        with self._lock:
            if self._client is not None:
                return self._client
            try:
                MILVUS_LITE_PATH.parent.mkdir(parents=True, exist_ok=True)
                client = MilvusClient(uri=str(MILVUS_LITE_PATH))
                self._client = client
                self._last_error = None
                logger.info("Connected to Milvus Lite at %s", MILVUS_LITE_PATH)
                return client
            except Exception as exc:
                self._client = None
                self._last_error = str(exc)
                logger.exception("Failed to connect to Milvus Lite at %s", MILVUS_LITE_PATH)
                return None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def status(self) -> VectorStoreStatus:
        client = self._get_client()
        if client is None:
            return VectorStoreStatus(
                ready=False,
                collection=self._collection_name,
                mode="lite",
                error=self._last_error or "Milvus Lite connection failed",
            )
        # A recorded migration failure means the store is serving (or about to
        # serve) un-isolatable legacy data — it must report NOT ready.
        if self._last_error:
            return VectorStoreStatus(
                ready=False,
                collection=self._collection_name,
                collection_exists=client.has_collection(self._collection_name),
                mode="lite",
                error=self._last_error,
            )
        try:
            return VectorStoreStatus(
                ready=True,
                collection=self._collection_name,
                collection_exists=client.has_collection(self._collection_name),
                mode="lite",
            )
        except Exception as exc:
            logger.exception("Milvus Lite readiness check failed")
            return VectorStoreStatus(ready=False, collection=self._collection_name, mode="lite", error=str(exc))

    def ensure_collection(self) -> MilvusClient | None:
        client = self._get_client()
        if client is None:
            return None
        try:
            # Fresh deployment: no active marker and no base collection → create
            # the initial tenant-keyed collection (WITH tenant_id) directly.
            if self._collection_name == self._base_collection:
                if client.has_collection(self._base_collection):
                    # Legacy collection lacks tenant_id.  Milvus Lite cannot
                    # ALTER a schema in place, so we copy all rows into a
                    # <name>_v2 collection stamped tenant_id=1, validate, and
                    # only then switch the active collection — the legacy
                    # collection is retained as a rollback backup.
                    base_fields = {
                        f.get("name"): f
                        for f in client.describe_collection(self._base_collection).get("fields", [])
                    }
                    if "tenant_id" not in base_fields:
                        self._migrate_legacy_to_v2(client)
                else:
                    self._create_tenant_collection(client, self._base_collection)
                    self._persist_active_collection(self._base_collection)

            # Active collection is now the (possibly migrated) V2 collection.
            if not client.has_collection(self._collection_name):
                logger.error("Active collection %s missing", self._collection_name)
                return None
            schema = client.describe_collection(self._collection_name)
            field_map = {f.get("name"): f for f in schema.get("fields", [])}
            required = {"chunk_id", "document_id", "knowledge_base_id", "content", "embedding"}
            missing = required - set(field_map.keys())
            if missing:
                logger.error("Milvus schema missing fields: %s; refusing drop", sorted(missing))
                return None
            emb = field_map.get("embedding", {})
            dim = (emb.get("params") or {}).get("dim") or emb.get("dim")
            if dim is not None and dim != config.EMBEDDING_DIMENSION:
                logger.error(
                    "Milvus embedding dimension mismatch: got %s, expected %s; refusing drop",
                    dim, config.EMBEDDING_DIMENSION,
                )
                return None
            return client

        except Exception as exc:
            # Migration failure must NOT switch the read path.
            self._last_error = f"tenant_id migration failed: {exc}"
            logger.error("FATAL: %s", self._last_error)
            return None

    def _migrate_legacy_to_v2(self, client: MilvusClient) -> str:
        """Copy legacy rows into <name>_v2 stamped tenant_id=1.

        Read all records, write them (plus ``tenant_id``) into a new ``_v2``
        collection, build the index, validate row/pk parity and tenant-1
        retrieval, then atomically switch the active collection.  The legacy
        collection is kept as a rollback backup.  Any failure raises WITHOUT
        switching the read path (idempotent: a validated ``_v2`` is reused).
        """
        v2 = self._base_collection + self._V2_SUFFIX

        # 1. Read every legacy row (paginated) from the old collection.
        legacy_rows = self._read_all_rows(client, self._base_collection)
        legacy_ids = {str(r["chunk_id"]) for r in legacy_rows}

        # 2. Build the tenant-keyed V2 collection unless an already-valid one exists.
        if client.has_collection(v2) and self._validate_v2(client, v2, legacy_ids):
            logger.info("Reusing already-migrated collection %s", v2)
        else:
            self._drop_collection_if_exists(client, v2)
            self._create_tenant_collection(client, v2)

            if legacy_rows:
                client.load_collection(v2)
                for offset_db in range(0, len(legacy_rows), self._BACKFILL_PAGE_SIZE):
                    batch = [
                        {**row, "tenant_id": 1}
                        for row in legacy_rows[offset_db:offset_db + self._BACKFILL_PAGE_SIZE]
                    ]
                    client.insert(collection_name=v2, data=batch)
                client.load_collection(v2)

            # 3. Validate parity + tenant-1 retrieval before switching.
            if not self._validate_v2(client, v2, legacy_ids):
                raise RuntimeError(
                    f"V2 migration validation failed for {v2} (rows={len(legacy_rows)})"
                )

        # 4. Atomic switch: persist marker first, then flip the in-memory active.
        self._persist_active_collection(v2)
        self._collection_name = v2
        logger.info("Switched active collection %s -> %s (%d rows)",
                    self._base_collection, v2, len(legacy_rows))
        return v2

    def _create_tenant_collection(self, client: MilvusClient, name: str) -> None:
        """Create a collection whose schema includes the ``tenant_id`` column."""
        fields = [
            FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, is_primary=True, max_length=128),
            FieldSchema(name="document_id", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="knowledge_base_id", dtype=DataType.INT64),
            FieldSchema(name="tenant_id", dtype=DataType.INT64),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="block_type", dtype=DataType.VARCHAR, max_length=20),
            FieldSchema(name="outline_path", dtype=DataType.VARCHAR, max_length=2000),
            FieldSchema(name="metadata", dtype=DataType.VARCHAR, max_length=4000),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=config.EMBEDDING_DIMENSION),
        ]
        schema = CollectionSchema(fields=fields, description="Document chunks for RAG (tenant-keyed)")
        index_params = client.prepare_index_params()
        index_params.add_index(field_name="embedding", metric_type="COSINE",
                               index_type="IVF_FLAT", params={"nlist": 128})
        client.create_collection(collection_name=name, schema=schema, index_params=index_params)
        logger.info("Created collection %s", name)

    def _read_all_rows(self, client: MilvusClient, collection: str) -> list[dict[str, Any]]:
        fields = [
            "chunk_id", "document_id", "knowledge_base_id",
            "content", "block_type", "outline_path", "metadata", "embedding",
        ]
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = client.query(
                collection_name=collection, filter="",
                output_fields=fields, limit=self._BACKFILL_PAGE_SIZE, offset=offset,
            )
            if not page:
                break
            rows.extend(page)
            offset += len(page)
            if len(page) < self._BACKFILL_PAGE_SIZE:
                break
        return rows

    def _read_all_ids(self, client: MilvusClient, collection: str,
                      filter_expr: str = "", output_field: str = "chunk_id") -> set:
        """Paginate the primary keys (or any single field) for an expression.

        Unlike a single ``limit=16384`` query, this is unbounded — large legacy
        sets (>16,384 rows) validate correctly instead of alarming the parity
        check into a false failure.
        """
        ids: set = set()
        offset = 0
        while True:
            page = client.query(
                collection_name=collection, filter=filter_expr,
                output_fields=[output_field], limit=self._BACKFILL_PAGE_SIZE, offset=offset,
            )
            if not page:
                break
            ids.update(str(r[output_field]) for r in page)
            offset += len(page)
            if len(page) < self._BACKFILL_PAGE_SIZE:
                break
        return ids

    def _validate_v2(self, client: MilvusClient, v2: str, legacy_ids: set) -> bool:
        """Row count + primary-key parity, plus tenant-1 retrievability."""
        try:
            schema = client.describe_collection(v2)
            if "tenant_id" not in {f.get("name") for f in schema.get("fields", [])}:
                return False
            client.load_collection(v2)
            migrated_ids = self._read_all_ids(client, v2, filter_expr="tenant_id == 1")
            if migrated_ids != legacy_ids:
                logger.error("V2 primary-key/tenant-1 parity mismatch for %s", v2)
                return False
            return True
        except Exception as exc:
            logger.error("V2 validation error for %s: %s", v2, exc)
            return False

    def _drop_collection_if_exists(self, client: MilvusClient, name: str) -> None:
        try:
            if client.has_collection(name):
                client.drop_collection(name)
                logger.info("Dropped stale migration target %s", name)
        except Exception as exc:
            logger.warning("Could not drop stale migration target %s: %s", name, exc)

    # ── Active-collection persistence (atomic switch marker) ─────────────────

    def _marker_path(self) -> Path:
        return Path(str(MILVUS_LITE_PATH) + self._ACTIVE_COLLECTION_MARKER)

    def _load_active_collection(self) -> str | None:
        try:
            p = self._marker_path()
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                name = data.get("active_collection")
                if name:
                    return str(name)
        except Exception as exc:
            logger.warning("Failed to read active-collection marker: %s", exc)
        return None

    def _persist_active_collection(self, name: str) -> None:
        p = self._marker_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps({"active_collection": name}), encoding="utf-8")
        os.replace(tmp, p)

    def drop_collection(self) -> bool:
        if os.getenv("MILVUS_ALLOW_COLLECTION_DROP", "false").lower() != "true":
            logger.error("Refusing to drop collection without MILVUS_ALLOW_COLLECTION_DROP=true")
            return False
        try:
            client = self._get_client()
            if client is None:
                return False
            if client.has_collection(self._collection_name):
                client.drop_collection(self._collection_name)
                logger.info("Dropped collection: %s", self._collection_name)
            return True
        except Exception:
            logger.exception("Failed to drop collection")
            return False

    # ── Tenant isolation ─────────────────────────────────────────────────────

    _BACKFILL_PAGE_SIZE = 512

    def _tenant_filter(self, knowledge_base_id: int | None = None,
                       document_id: str | None = None) -> str | None:
        """Build a filter expression that ALWAYS scopes to the active tenant."""
        tenant_id = require_tenant_id()  # fail-closed: no default tenant
        parts = [f"tenant_id == {tenant_id}"]
        if knowledge_base_id:
            parts.append(f"knowledge_base_id == {knowledge_base_id}")
        if document_id:
            escaped = str(document_id).replace('"', '\\"')
            parts.append(f'document_id == "{escaped}"')
        return " and ".join(parts)

    def _tenant_co_store_key(self) -> str:
        """Return the per-tenant document-grouped co-store view keyed by tenant."""
        return str(require_tenant_id())

    # ── Write ────────────────────────────────────────────────────────────────

    def insert_chunks(
        self,
        chunks: list[VectorChunk],
        embeddings: list[list[float]],
        document_id: str,
        knowledge_base_id: int | None = None,
    ) -> bool:
        tenant_id = require_tenant_id()  # fail-closed
        try:
            client = self.ensure_collection()
            if client is None:
                return False

            data = []
            for chunk, embedding in zip(chunks, embeddings):
                outline_path_str = json.dumps(chunk.outline_path) if chunk.outline_path else "[]"
                data.append({
                    "chunk_id": chunk.chunk_id,
                    "document_id": document_id,
                    "knowledge_base_id": knowledge_base_id or 0,
                    "tenant_id": tenant_id,
                    "content": chunk.content,
                    "block_type": chunk.block_type,
                    "outline_path": outline_path_str,
                    "metadata": json.dumps(chunk.metadata) if chunk.metadata else "{}",
                    "embedding": embedding,
                })

            # chunk_id 为确定性主键（{document_id}_chunk_{n}）：文档重析/embedding
            # 变更重索引时新旧 ID 大量相同，insert 不去重会造成同主键双份存储、
            # 旧文本继续可被检索——必须 upsert 按主键替换。
            client.upsert(collection_name=self._collection_name, data=data)
            logger.info("Upserted %d chunks into Milvus Lite (tenant %d)", len(data), tenant_id)

            # Mirror to JSON co-store
            store_records = []
            for chunk in chunks:
                outline_path_str = json.dumps(chunk.outline_path) if chunk.outline_path else "[]"
                store_records.append({
                    "chunk_id": chunk.chunk_id,
                    "document_id": document_id,
                    "knowledge_base_id": knowledge_base_id or 0,
                    "tenant_id": tenant_id,
                    "content": chunk.content,
                    "block_type": chunk.block_type,
                    "outline_path": outline_path_str,
                    "metadata": json.dumps(chunk.metadata) if chunk.metadata else "{}",
                })
            self._save_to_co_store(document_id, store_records)
            return True
        except Exception:
            logger.exception("Failed to insert chunks")
            return False

    def delete_document_chunks(self, document_id: str) -> bool:
        try:
            tenant_id = require_tenant_id()
            client = self._get_client()
            if client is not None and client.has_collection(self._collection_name):
                client.delete(
                    collection_name=self._collection_name,
                    filter=self._tenant_filter(document_id=document_id),
                )
            with self._lock:
                # R15-13：与 _save_to_co_store 同锁，防并发删/插互相覆盖
                store = self._load_co_store()
                store.setdefault(str(tenant_id), {}).pop(str(document_id), None)
                self._write_co_store(store)
            return True
        except Exception:
            logger.exception("Failed to delete document chunks")
            return False

    def delete_chunk_ids(self, chunk_ids: list[str]) -> bool:
        if not chunk_ids:
            return True
        try:
            tenant_id = require_tenant_id()
            client = self._get_client()
            if client is not None and client.has_collection(self._collection_name):
                escaped = [str(cid).replace('"', '\\"') for cid in chunk_ids]
                values = ",".join(f'"{c}"' for c in escaped)
                client.delete(
                    collection_name=self._collection_name,
                    filter=f"tenant_id == {tenant_id} and chunk_id in [{values}]",
                )
            return True
        except Exception as exc:
            logger.error("Failed to delete chunk IDs: %s", exc)
            return False

    # ── Read ─────────────────────────────────────────────────────────────────

    def search(
        self,
        query_text: str | None = None,
        query_embedding: list[float] | None = None,
        top_k: int = 5,
        document_id: str | None = None,
        knowledge_base_id: int | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            client = self._get_client()
            if client is None:
                return []

            if query_text and query_embedding is None:
                from app.core.embedding import get_embedding_service
                embedding_service = get_embedding_service()
                # R16-5：查询向量走缓存路径（同请求内重复检索/跨请求同问法
                # 直接命中，省一次 CPU 推理 ~2.5s）。
                query_embedding = embedding_service.get_query_embedding(query_text)
                if query_embedding is None:
                    logger.warning("Failed to generate embedding for query: %s", query_text[:50])
                    return []

            if query_embedding is None:
                return []

            # R15-15：不再每次查询 load_collection（冗余 RPC）。集合通常在
            # ensure/迁移阶段已 load；若被驱逐（not loaded 错误），在 except
            # 中 load 后重试一次。
            try:
                return self._filtered_search(
                    client, query_embedding, top_k, knowledge_base_id, document_id,
                    metadata_filter,
                )
            except Exception as exc:
                if "not loaded" in str(exc).lower() or "not exist" in str(exc).lower():
                    client.load_collection(self._collection_name)
                    return self._filtered_search(
                        client, query_embedding, top_k, knowledge_base_id, document_id,
                        metadata_filter,
                    )
                raise
        except Exception:
            logger.exception("Failed to search")
            return []

    def _filtered_search(
        self,
        client,
        query_embedding: list[float],
        top_k: int,
        knowledge_base_id: int | None,
        document_id: str | None,
        metadata_filter: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """带元数据过滤的搜索：先超额召回再按谓词后过滤（Batch 5）。

        无 filter 时与原路径完全一致（top_k 直取）。
        """
        if not metadata_filter:
            return self._search_client(
                client, query_embedding, top_k, knowledge_base_id, document_id
            )
        from app.core.vectorstore.milvus_store import _matches_metadata_filter

        fetch_k = min(max(top_k * 4, 20), 200)
        candidates = self._search_client(
            client, query_embedding, fetch_k, knowledge_base_id, document_id
        )
        matched = [
            r for r in candidates
            if _matches_metadata_filter(r.get("metadata"), metadata_filter)
        ]
        return matched[:top_k]

    def _search_client(
        self,
        client,
        query_embedding: list[float],
        top_k: int,
        knowledge_base_id: int | None,
        document_id: str | None,
    ) -> list[dict[str, Any]]:
        # Tenant isolation: always scope retrieval to the active tenant.
        filter_expr = self._tenant_filter(
            knowledge_base_id=knowledge_base_id, document_id=document_id
        )

        results = client.search(
            collection_name=self._collection_name,
            data=[query_embedding],
            limit=top_k,
            search_params={"metric_type": "COSINE", "params": {"nprobe": 16}},
            output_fields=["chunk_id", "document_id", "knowledge_base_id", "tenant_id", "content", "block_type", "outline_path", "metadata"],
            filter=filter_expr,
        )

        formatted = []
        for hits in results:
            for hit in hits:
                outline_path = hit.get("outline_path", "[]")
                if isinstance(outline_path, str):
                    try:
                        outline_path = json.loads(outline_path)
                    except Exception:
                        outline_path = []
                formatted.append({
                    "chunk_id": hit.get("chunk_id"),
                    "document_id": hit.get("document_id"),
                    "knowledge_base_id": hit.get("knowledge_base_id"),
                    "content": hit.get("content"),
                    "block_type": hit.get("block_type"),
                    "outline_path": outline_path,
                    "metadata": json.loads(hit.get("metadata", "{}")),
                    "score": hit.get("distance"),
                })
        return formatted

    def get_document_chunks(
        self, document_id: str, page: int = 1, size: int = 20, block_type: str | None = None,
    ) -> dict[str, Any]:
        try:
            tenant_id = require_tenant_id()
            store = self._load_co_store()
            tenant_key = str(tenant_id)
            all_chunks = store.get(tenant_key, {}).get(str(document_id), [])
            if block_type:
                all_chunks = [c for c in all_chunks if c.get("block_type") == block_type]
            total = len(all_chunks)
            start = (page - 1) * size
            records = all_chunks[start : start + size]
            return {"code": 200, "data": {"records": records, "total": total, "page": page, "size": size}}
        except Exception as exc:
            logger.exception("Failed to get document chunks")
            return {"code": 500, "message": str(exc)}

    def get_chunk_detail(self, chunk_id: str) -> dict[str, Any] | None:
        try:
            tenant_id = require_tenant_id()
            client = self._get_client()
            if client is None:
                return None
            escaped = str(chunk_id).replace('"', '\\"')
            results = client.query(
                collection_name=self._collection_name,
                filter=f'tenant_id == {tenant_id} and chunk_id == "{escaped}"',
                output_fields=["chunk_id", "document_id", "knowledge_base_id", "tenant_id", "content", "block_type", "outline_path", "metadata"],
            )
            return results[0] if results else None
        except Exception:
            logger.exception("Failed to get chunk detail")
            return None

    # ── Reconciliation helpers ───────────────────────────────────────────────

    def list_all_chunk_ids(self, knowledge_base_id: int | None = None) -> list[str]:
        try:
            client = self._get_client()
            if client is None:
                return []
            if not client.has_collection(self._collection_name):
                return []
            client.load_collection(self._collection_name)
            filter_expr = self._tenant_filter(knowledge_base_id=knowledge_base_id)
            return sorted(self._read_all_ids(client, self._collection_name, filter_expr))
        except Exception as exc:
            logger.error("Failed to list chunk IDs: %s", exc)
            return []

    def count_chunks(self, knowledge_base_id: int | None = None) -> int:
        try:
            client = self._get_client()
            if client is None:
                return 0
            if not client.has_collection(self._collection_name):
                return 0
            client.load_collection(self._collection_name)
            filter_expr = self._tenant_filter(knowledge_base_id=knowledge_base_id)
            return len(self._read_all_ids(client, self._collection_name, filter_expr))
        except Exception as exc:
            logger.error("Failed to count chunks: %s", exc)
            return 0

    def all_chunks(self, knowledge_base_id: int | None = None) -> dict[str, list[dict[str, Any]]]:
        """Return all chunks of the active tenant from the JSON co-store."""
        tenant_id = require_tenant_id()
        store = self._load_co_store()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for document_id, chunks in store.get(str(tenant_id), {}).items():
            for chunk in chunks:
                if knowledge_base_id is not None and chunk.get("knowledge_base_id") != knowledge_base_id:
                    continue
                grouped.setdefault(str(chunk.get("document_id", document_id)), []).append(chunk)
        return grouped

    # ── JSON co-store (private) ──────────────────────────────────────────────

    def _load_co_store(self) -> dict[str, Any]:
        try:
            p = Path(CHUNKS_STORE_PATH)
            if p.exists():
                with p.open("r", encoding="utf-8") as f:
                    val = json.load(f)
                    return _migrate_co_store_layout(val)
        except Exception as exc:
            logger.error("Co-store load error: %s", exc)
        return {}

    def _write_co_store(self, store: dict[str, Any]) -> None:
        try:
            p = Path(CHUNKS_STORE_PATH)
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(p.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(store, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, p)
        except Exception as exc:
            logger.error("Co-store save error: %s", exc)

    def _save_to_co_store(self, document_id: str, chunks: list[dict]) -> None:
        # R15-13：读-改-写必须持锁——两个并发索引（或索引与删除）各自
        # load→modify→replace 会互相覆盖丢文档。锁只包 co-store 事务，
        # 不包 Milvus 客户端写入（已在锁外完成）。
        with self._lock:
            store = self._load_co_store()
            tenant_key = self._tenant_co_store_key()
            tenant_root = _co_store_tenant_root(store, tenant_key)
            tenant_root[str(document_id)] = chunks
            self._write_co_store(store)
