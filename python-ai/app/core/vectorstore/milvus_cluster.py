"""
Milvus standalone / cluster vector store — remote HTTP-connected backend.

This module connects to a Milvus standalone or distributed cluster via the
standard pymilvus HTTP client.  It conforms to :class:`VectorStoreProtocol`
and is selected when ``VECTOR_STORE_MODE=cluster``.

Production / staging deployments MUST use this backend; the embedded Lite
process cannot share a data directory across multiple worker processes.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Dict, List, Optional

from pymilvus import (
    FieldSchema,
    CollectionSchema,
    DataType,
    MilvusClient,
)

from app.utils.config import config
from app.core.vectorstore.base import VectorStoreProtocol, VectorStoreStatus
from app.core.chunker.text_chunker import VectorChunk
from app.core.tenant.context import require_tenant_id

logger = logging.getLogger(__name__)


class MilvusClusterStore(VectorStoreProtocol):
    """Remote Milvus standalone / cluster backend (HTTP-connected)."""

    def __init__(self) -> None:
        self._collection_name = config.MILVUS_COLLECTION
        self._uri = f"http://{config.MILVUS_HOST}:{config.MILVUS_PORT}"
        self._client: Optional[MilvusClient] = None
        self._lock = threading.RLock()
        self._last_error: Optional[str] = None

    # ── Connection ───────────────────────────────────────────────────────────

    def _get_client(self) -> Optional[MilvusClient]:
        with self._lock:
            if self._client is not None:
                return self._client
            try:
                # Milvus 认证：MILVUS_PASSWORD 非空时携带 user/password（默认 root）
                if config.MILVUS_PASSWORD:
                    client = MilvusClient(
                        uri=self._uri,
                        user=config.MILVUS_USER or "root",
                        password=config.MILVUS_PASSWORD,
                    )
                else:
                    client = MilvusClient(uri=self._uri)
                self._client = client
                self._last_error = None
                logger.info("Connected to Milvus cluster at %s", self._uri)
                return client
            except Exception as exc:
                self._client = None
                self._last_error = str(exc)
                logger.exception("Failed to connect to Milvus cluster at %s", self._uri)
                return None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def status(self) -> VectorStoreStatus:
        client = self._get_client()
        if client is None:
            return VectorStoreStatus(
                ready=False,
                collection=self._collection_name,
                mode="cluster",
                error=self._last_error or "Milvus cluster connection failed",
            )
        try:
            return VectorStoreStatus(
                ready=True,
                collection=self._collection_name,
                collection_exists=client.has_collection(self._collection_name),
                mode="cluster",
                extra={"uri": self._uri},
            )
        except Exception as exc:
            logger.exception("Milvus cluster readiness check failed")
            return VectorStoreStatus(ready=False, collection=self._collection_name, mode="cluster", error=str(exc))

    def ensure_collection(self) -> Optional[MilvusClient]:
        client = self._get_client()
        if client is None:
            return None
        try:
            if client.has_collection(self._collection_name):
                try:
                    schema = client.describe_collection(self._collection_name)
                    field_map = {f.get("name"): f for f in schema.get("fields", [])}
                    required = {"chunk_id", "document_id", "knowledge_base_id", "content", "embedding"}
                    missing = required - set(field_map.keys())
                    if missing:
                        logger.error("Milvus schema missing fields: %s; refusing drop", sorted(missing))
                        return None
                    if "tenant_id" not in field_map:
                        try:
                            self._migrate_add_tenant_field(client)
                        except Exception as exc:
                            self._last_error = f"tenant_id migration failed: {exc}"
                            logger.error("FATAL: %s", self._last_error)
                            return None
                    emb = field_map.get("embedding", {})
                    dim = (emb.get("params") or {}).get("dim") or emb.get("dim")
                    if dim is not None and dim != config.EMBEDDING_DIMENSION:
                        logger.error(
                            "Milvus embedding dimension mismatch: got %s, expected %s; refusing drop",
                            dim, config.EMBEDDING_DIMENSION,
                        )
                        return None
                except Exception as exc:
                    logger.warning("Schema check failed (keeping collection): %s", exc)
                return client

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
            schema = CollectionSchema(fields=fields, description="Document chunks for RAG")
            index_params = client.prepare_index_params()
            index_params.add_index(
                field_name="embedding",
                metric_type="COSINE",
                index_type="IVF_FLAT",
                params={"nlist": 128},
            )
            client.create_collection(
                collection_name=self._collection_name,
                schema=schema,
                index_params=index_params,
            )
            logger.info("Created collection: %s", self._collection_name)
            return client
        except Exception as exc:
            logger.exception("Failed to create collection")
            return None

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
        except Exception as exc:
            logger.exception("Failed to drop collection")
            return False

    # ── Tenant isolation ─────────────────────────────────────────────────────

    _BACKFILL_PAGE_SIZE = 512

    def _migrate_add_tenant_field(self, client: MilvusClient) -> None:
        """Add the tenant_id field to a legacy collection and backfill ALL rows.

        A HARD safety gate: any failure to add the field or backfill, or any
        residual row still missing tenant_id after validation, is raised so the
        service refuses to serve un-isolatable historical vectors.
        """
        logger.info("Migrating Milvus cluster collection to add tenant_id")
        try:
            client.add_collection_field(
                collection_name=self._collection_name,
                field_name="tenant_id",
                data_type=DataType.INT64,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to add tenant_id field to %s: {exc}" % self._collection_name
            ) from exc

        client.load_collection(self._collection_name)

        all_fields = [
            "chunk_id", "document_id", "knowledge_base_id", "tenant_id",
            "content", "block_type", "outline_path", "metadata", "embedding",
        ]
        offset = 0
        total_updated = 0
        while True:
            page = client.query(
                collection_name=self._collection_name,
                filter="",
                output_fields=[f for f in all_fields if f != "tenant_id"],
                limit=self._BACKFILL_PAGE_SIZE,
                offset=offset,
            )
            if not page:
                break
            rows = []
            for row in page:
                rows.append({
                    "chunk_id": row.get("chunk_id"),
                    "document_id": row.get("document_id"),
                    "knowledge_base_id": row.get("knowledge_base_id"),
                    "tenant_id": 1,
                    "content": row.get("content"),
                    "block_type": row.get("block_type"),
                    "outline_path": row.get("outline_path", "[]"),
                    "metadata": row.get("metadata", "{}"),
                    "embedding": row.get("embedding"),
                })
            if rows:
                client.upsert(collection_name=self._collection_name, data=rows)
                total_updated += len(rows)
            offset += len(page)
            if len(page) < self._BACKFILL_PAGE_SIZE:
                break

        missing = client.query(
            collection_name=self._collection_name,
            filter="tenant_id == 0 or tenant_id == null",
            output_fields=["chunk_id"],
            limit=1,
        )
        logger.info("Backfilled %d rows to tenant 1", total_updated)
        if missing:
            raise RuntimeError(
                f"Milvus backfill validation failed: {len(missing)} rows still "
                f"missing tenant_id in {self._collection_name}"
            )

    def _tenant_filter(self, knowledge_base_id: Optional[int] = None,
                       document_id: Optional[str] = None) -> Optional[str]:
        """Build a filter expression that ALWAYS scopes to the active tenant."""
        tenant_id = require_tenant_id()  # fail-closed: no default tenant
        parts = [f"tenant_id == {tenant_id}"]
        if knowledge_base_id:
            parts.append(f"knowledge_base_id == {knowledge_base_id}")
        if document_id:
            escaped = str(document_id).replace('"', '\\"')
            parts.append(f'document_id == "{escaped}"')
        return " and ".join(parts)

    # ── Write ────────────────────────────────────────────────────────────────

    def insert_chunks(
        self,
        chunks: List[VectorChunk],
        embeddings: List[List[float]],
        document_id: str,
        knowledge_base_id: Optional[int] = None,
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

            client.insert(collection_name=self._collection_name, data=data)
            logger.info("Inserted %d chunks into Milvus cluster (tenant %d)", len(data), tenant_id)
            return True
        except Exception as exc:
            logger.exception("Failed to insert chunks into Milvus cluster")
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
            return True
        except Exception as exc:
            logger.exception("Failed to delete document chunks from cluster")
            return False

    def delete_chunk_ids(self, chunk_ids: List[str]) -> bool:
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
            logger.error("Failed to delete chunk IDs from cluster: %s", exc)
            return False

    # ── Read ─────────────────────────────────────────────────────────────────

    def search(
        self,
        query_text: Optional[str] = None,
        query_embedding: Optional[List[float]] = None,
        top_k: int = 5,
        document_id: Optional[str] = None,
        knowledge_base_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        try:
            client = self._get_client()
            if client is None:
                return []

            if query_text and query_embedding is None:
                from app.core.embedding import get_embedding_service
                embedding_service = get_embedding_service()
                query_embedding = embedding_service.get_embedding(query_text)
                if query_embedding is None:
                    logger.warning("Failed to generate embedding for query: %s", query_text[:50])
                    return []

            if query_embedding is None:
                return []

            # Tenant isolation: always scope retrieval to the active tenant.
            filter_expr = self._tenant_filter(
                knowledge_base_id=knowledge_base_id, document_id=document_id
            )

            # R15-15：不再每次查询 load_collection（冗余 RPC）。集合在
            # ensure/启动阶段已 load；若被驱逐，load 后重试一次。
            def _do_search():
                return client.search(
                    collection_name=self._collection_name,
                    data=[query_embedding],
                    limit=top_k,
                    search_params={"metric_type": "COSINE", "params": {"nprobe": 16}},
                    output_fields=["chunk_id", "document_id", "knowledge_base_id", "tenant_id", "content", "block_type", "outline_path", "metadata"],
                    filter=filter_expr,
                )

            try:
                results = _do_search()
            except Exception as exc:
                if "not loaded" not in str(exc).lower():
                    raise
                client.load_collection(self._collection_name)
                results = _do_search()

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
        except Exception as exc:
            logger.exception("Failed to search cluster")
            return []

    def get_document_chunks(
        self, document_id: str, page: int = 1, size: int = 20, block_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """In cluster mode, chunk browsing is served via Milvus query (no JSON co-store)."""
        try:
            client = self._get_client()
            if client is None:
                return {"code": 503, "message": "Milvus cluster unavailable"}
            if not client.has_collection(self._collection_name):
                return {"code": 200, "data": {"records": [], "total": 0, "page": page, "size": size}}

            filters = [f'document_id == "{document_id}"']
            if block_type:
                filters.append(f'block_type == "{block_type}"')
            filter_expr = self._tenant_filter(document_id=document_id) if block_type is None \
                else " and ".join([self._tenant_filter(document_id=document_id), f'block_type == "{block_type}"'])

            # Milvus doesn't natively paginate; query all then slice.
            results = client.query(
                collection_name=self._collection_name,
                filter=filter_expr,
                output_fields=["chunk_id", "document_id", "knowledge_base_id", "tenant_id", "content", "block_type", "outline_path", "metadata"],
                limit=16384,
            )

            total = len(results)
            start = (page - 1) * size
            records = results[start : start + size]
            return {"code": 200, "data": {"records": records, "total": total, "page": page, "size": size}}
        except Exception as exc:
            logger.exception("Failed to get document chunks from cluster")
            return {"code": 500, "message": str(exc)}

    def get_chunk_detail(self, chunk_id: str) -> Optional[Dict[str, Any]]:
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
        except Exception as exc:
            logger.exception("Failed to get chunk detail from cluster")
            return None

    # ── Reconciliation helpers ───────────────────────────────────────────────

    def list_all_chunk_ids(self, knowledge_base_id: Optional[int] = None) -> List[str]:
        try:
            client = self._get_client()
            if client is None:
                return []
            if not client.has_collection(self._collection_name):
                return []
            client.load_collection(self._collection_name)
            filter_expr = self._tenant_filter(knowledge_base_id=knowledge_base_id)
            # 单次 query 硬上限 16384 — 大库对账会静默截断虚低。
            # 优先 query_iterator（游标迭代无窗口限制），不可用时回退单次 query
            try:
                iterator = client.query_iterator(
                    collection_name=self._collection_name,
                    filter=filter_expr,
                    output_fields=["chunk_id"],
                    batch_size=1000,
                )
                ids: List[str] = []
                while True:
                    batch = iterator.next()
                    if not batch:
                        break
                    ids.extend(r["chunk_id"] for r in batch)
                iterator.close()
                return ids
            except (AttributeError, TypeError) as exc:
                logger.warning(
                    "query_iterator unavailable (%s); falling back to single query (16384 cap)", exc
                )
            results = client.query(
                collection_name=self._collection_name,
                filter=filter_expr,
                output_fields=["chunk_id"],
                limit=16384,
            )
            return [r["chunk_id"] for r in results]
        except Exception as exc:
            logger.error("Failed to list chunk IDs from cluster: %s", exc)
            return []

    def count_chunks(self, knowledge_base_id: Optional[int] = None) -> int:
        try:
            client = self._get_client()
            if client is None:
                return 0
            if not client.has_collection(self._collection_name):
                return 0
            client.load_collection(self._collection_name)
            filter_expr = self._tenant_filter(knowledge_base_id=knowledge_base_id)
            results = client.query(
                collection_name=self._collection_name,
                filter=filter_expr,
                output_fields=["chunk_id"],
                limit=16384,
            )
            return len(results)
        except Exception as exc:
            logger.error("Failed to count chunks from cluster: %s", exc)
            return 0

    def all_chunks(self, knowledge_base_id: Optional[int] = None) -> Dict[str, List[Dict[str, Any]]]:
        """Return all chunks from Milvus, grouped by document_id.

        This provides BM25 / citation with the same scoped corpus the vector
        and keyword channels operate on, without depending on a per-pod JSON
        co-store.  The ``metadata`` field is parsed back into a dict.
        """
        try:
            client = self._get_client()
            if client is None:
                return {}
            if not client.has_collection(self._collection_name):
                return {}
            client.load_collection(self._collection_name)

            # Tenant isolation: scope the chunk corpus to the active tenant.
            filter_expr = self._tenant_filter(knowledge_base_id=knowledge_base_id)

            output = ["chunk_id", "document_id", "knowledge_base_id", "tenant_id", "content",
                      "block_type", "outline_path", "metadata"]
            grouped: Dict[str, List[Dict[str, Any]]] = {}
            offset = 0
            page_size = 1000
            while True:
                results = client.query(
                    collection_name=self._collection_name,
                    filter=filter_expr,
                    output_fields=output,
                    limit=page_size,
                    offset=offset,
                )
                if not results:
                    break
                for r in results:
                    outline = r.get("outline_path", "[]")
                    if isinstance(outline, str):
                        try:
                            outline = json.loads(outline)
                        except Exception:
                            outline = []
                    metadata = r.get("metadata", "{}")
                    if isinstance(metadata, str):
                        try:
                            metadata = json.loads(metadata)
                        except Exception:
                            metadata = {}
                    doc_key = str(r.get("document_id", ""))
                    grouped.setdefault(doc_key, []).append({
                        "chunk_id": r.get("chunk_id"),
                        "document_id": r.get("document_id"),
                        "knowledge_base_id": r.get("knowledge_base_id"),
                        "content": r.get("content", ""),
                        "block_type": r.get("block_type"),
                        "outline_path": outline,
                        "metadata": metadata,
                    })
                if len(results) < page_size:
                    break
                offset += page_size
            return grouped
        except Exception as exc:
            logger.error("Failed to load all chunks from cluster: %s", exc)
            return {}
