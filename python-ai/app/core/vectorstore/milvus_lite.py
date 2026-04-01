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


class MilvusLiteStore(VectorStoreProtocol):
    """Embedded Milvus Lite backend (file-backed, single-process)."""

    def __init__(self) -> None:
        self._collection_name = config.MILVUS_COLLECTION
        self._client: Optional[MilvusClient] = None
        self._lock = threading.RLock()
        self._last_error: Optional[str] = None

    # ── Connection ───────────────────────────────────────────────────────────

    def _get_client(self) -> Optional[MilvusClient]:
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

    # ── Write ────────────────────────────────────────────────────────────────

    def insert_chunks(
        self,
        chunks: List[VectorChunk],
        embeddings: List[List[float]],
        document_id: str,
        knowledge_base_id: Optional[int] = None,
    ) -> bool:
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
                    "content": chunk.content,
                    "block_type": chunk.block_type,
                    "outline_path": outline_path_str,
                    "metadata": json.dumps(chunk.metadata) if chunk.metadata else "{}",
                    "embedding": embedding,
                })

            client.insert(collection_name=self._collection_name, data=data)
            logger.info("Inserted %d chunks into Milvus Lite", len(data))

            # Mirror to JSON co-store
            store_records = []
            for chunk in chunks:
                outline_path_str = json.dumps(chunk.outline_path) if chunk.outline_path else "[]"
                store_records.append({
                    "chunk_id": chunk.chunk_id,
                    "document_id": document_id,
                    "knowledge_base_id": knowledge_base_id or 0,
                    "content": chunk.content,
                    "block_type": chunk.block_type,
                    "outline_path": outline_path_str,
                    "metadata": json.dumps(chunk.metadata) if chunk.metadata else "{}",
                })
            self._save_to_co_store(document_id, store_records)
            return True
        except Exception as exc:
            logger.exception("Failed to insert chunks")
            return False

    def delete_document_chunks(self, document_id: str) -> bool:
        try:
            client = self._get_client()
            if client is not None and client.has_collection(self._collection_name):
                client.delete(
                    collection_name=self._collection_name,
                    filter=f'document_id == "{document_id}"',
                )
            store = self._load_co_store()
            store.pop(str(document_id), None)
            self._write_co_store(store)
            return True
        except Exception as exc:
            logger.exception("Failed to delete document chunks")
            return False

    def delete_chunk_ids(self, chunk_ids: List[str]) -> bool:
        if not chunk_ids:
            return True
        try:
            client = self._get_client()
            if client is not None and client.has_collection(self._collection_name):
                escaped = [str(cid).replace('"', '\\"') for cid in chunk_ids]
                values = ",".join(f'"{c}"' for c in escaped)
                client.delete(collection_name=self._collection_name, filter=f"chunk_id in [{values}]")
            return True
        except Exception as exc:
            logger.error("Failed to delete chunk IDs: %s", exc)
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

            client.load_collection(self._collection_name)

            filters = []
            if document_id:
                filters.append(f'document_id == "{document_id}"')
            if knowledge_base_id:
                filters.append(f"knowledge_base_id == {knowledge_base_id}")
            filter_expr = " and ".join(filters) if filters else None

            results = client.search(
                collection_name=self._collection_name,
                data=[query_embedding],
                limit=top_k,
                search_params={"metric_type": "COSINE", "params": {"nprobe": 16}},
                output_fields=["chunk_id", "document_id", "knowledge_base_id", "content", "block_type", "outline_path", "metadata"],
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
        except Exception as exc:
            logger.exception("Failed to search")
            return []

    def get_document_chunks(
        self, document_id: str, page: int = 1, size: int = 20, block_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            store = self._load_co_store()
            all_chunks = store.get(str(document_id), [])
            if block_type:
                all_chunks = [c for c in all_chunks if c.get("block_type") == block_type]
            total = len(all_chunks)
            start = (page - 1) * size
            records = all_chunks[start : start + size]
            return {"code": 200, "data": {"records": records, "total": total, "page": page, "size": size}}
        except Exception as exc:
            logger.exception("Failed to get document chunks")
            return {"code": 500, "message": str(exc)}

    def get_chunk_detail(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        try:
            client = self._get_client()
            if client is None:
                return None
            results = client.query(
                collection_name=self._collection_name,
                filter=f'chunk_id == "{chunk_id}"',
                output_fields=["chunk_id", "document_id", "knowledge_base_id", "content", "block_type", "outline_path", "metadata"],
            )
            return results[0] if results else None
        except Exception as exc:
            logger.exception("Failed to get chunk detail")
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
            filter_expr = f"knowledge_base_id == {knowledge_base_id}" if knowledge_base_id else None
            results = client.query(
                collection_name=self._collection_name,
                filter=filter_expr,
                output_fields=["chunk_id"],
                limit=16384,
            )
            return [r["chunk_id"] for r in results]
        except Exception as exc:
            logger.error("Failed to list chunk IDs: %s", exc)
            return []

    def count_chunks(self, knowledge_base_id: Optional[int] = None) -> int:
        try:
            client = self._get_client()
            if client is None:
                return 0
            if not client.has_collection(self._collection_name):
                return 0
            client.load_collection(self._collection_name)
            filter_expr = f"knowledge_base_id == {knowledge_base_id}" if knowledge_base_id else None
            results = client.query(
                collection_name=self._collection_name,
                filter=filter_expr,
                output_fields=["chunk_id"],
                limit=16384,
            )
            return len(results)
        except Exception as exc:
            logger.error("Failed to count chunks: %s", exc)
            return 0

    def all_chunks(self, knowledge_base_id: Optional[int] = None) -> Dict[str, List[Dict[str, Any]]]:
        """Return all chunks from the JSON co-store, grouped by document_id."""
        store = self._load_co_store()
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for document_id, chunks in store.items():
            for chunk in chunks:
                if knowledge_base_id is not None and chunk.get("knowledge_base_id") != knowledge_base_id:
                    continue
                grouped.setdefault(str(chunk.get("document_id", document_id)), []).append(chunk)
        return grouped

    # ── JSON co-store (private) ──────────────────────────────────────────────

    def _load_co_store(self) -> Dict[str, List[Dict]]:
        try:
            p = Path(CHUNKS_STORE_PATH)
            if p.exists():
                with p.open("r", encoding="utf-8") as f:
                    val = json.load(f)
                    return val if isinstance(val, dict) else {}
        except Exception as exc:
            logger.error("Co-store load error: %s", exc)
        return {}

    def _write_co_store(self, store: Dict[str, List[Dict]]) -> None:
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

    def _save_to_co_store(self, document_id: str, chunks: List[Dict]) -> None:
        store = self._load_co_store()
        store[document_id] = chunks
        self._write_co_store(store)
