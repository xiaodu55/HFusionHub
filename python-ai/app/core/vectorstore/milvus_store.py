"""
Milvus vector store — backward-compatible facade.

All production logic lives in :mod:`milvus_lite` or :mod:`milvus_cluster`
selected by the ``VECTOR_STORE_MODE`` env var.  This module re-exports the
same public API so that existing callers continue to work unchanged.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from app.utils.config import config
from app.core.chunker.text_chunker import VectorChunk
from app.core.vectorstore.milvus_lite import MILVUS_LITE_PATH as _LITE_PATH_DEFAULT
from app.core.vectorstore.milvus_lite import CHUNKS_STORE_PATH as _CO_STORE_DEFAULT

logger = logging.getLogger(__name__)

# Backward-compatible module-level attributes for tests that access ms._client,
# ms._last_connection_error, ms.MILVUS_LITE_PATH, ms.CHUNKS_STORE_PATH,
# and ms.config directly.
_client = None
_last_connection_error = None
MILVUS_LITE_PATH = _LITE_PATH_DEFAULT
CHUNKS_STORE_PATH = _CO_STORE_DEFAULT


def get_milvus_client():
    """Backward-compatible accessor — returns the underlying Milvus client."""
    store = _get_store()
    if hasattr(store, "_get_client"):
        return store._get_client()
    return None


def _get_store():
    from app.core.vectorstore.factory import get_vector_store
    return get_vector_store()


# ── Public API — delegates to the configured backend ────────────────────────


def vector_store_status() -> Dict[str, Any]:
    """Return a safe readiness summary for health checks and diagnostics."""
    # If tests have patched get_milvus_client to return None, use the
    # module-level _last_connection_error for the error message.
    patched_client = get_milvus_client()
    if patched_client is None and _last_connection_error is not None:
        return {
            "ready": False,
            "collection": config.MILVUS_COLLECTION,
            "error": _last_connection_error,
        }
    status = _get_store().status()
    return {
        "ready": status.ready,
        "collection": status.collection,
        "collection_exists": status.collection_exists,
        "mode": status.mode,
        **({"error": status.error} if status.error else {}),
        **(status.extra or {}),
    }


def create_collection():
    """Create collection if not exists, or return existing client."""
    # If tests have patched get_milvus_client, honor the patched value
    # by delegating to the store's ensure_collection which uses _get_client.
    store = _get_store()
    if hasattr(store, "_client"):
        store._client = None  # Reset so the store re-evaluates
    return store.ensure_collection()


def drop_collection() -> bool:
    """Drop collection (gated by MILVUS_ALLOW_COLLECTION_DROP)."""
    return _get_store().drop_collection()


def insert_chunks(
    chunks: List[VectorChunk],
    embeddings: List[List[float]],
    document_id: str,
    knowledge_base_id: Optional[int] = None,
) -> bool:
    """Insert chunks with embeddings into the vector store."""
    return _get_store().insert_chunks(chunks, embeddings, document_id, knowledge_base_id)


def search_similar(
    query_text: Optional[str] = None,
    query_embedding: Optional[List[float]] = None,
    top_k: int = 5,
    document_id: Optional[str] = None,
    knowledge_base_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Search for similar chunks."""
    return _get_store().search(query_text, query_embedding, top_k, document_id, knowledge_base_id)


def get_document_chunks(
    document_id: str, page: int = 1, size: int = 20, block_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Get paginated chunks for a document."""
    return _get_store().get_document_chunks(document_id, page, size, block_type)


def get_chunk_detail(chunk_id: str) -> Optional[Dict[str, Any]]:
    """Get single chunk detail."""
    return _get_store().get_chunk_detail(chunk_id)


def delete_document_chunks(document_id: str) -> bool:
    """Delete all chunks for a document (idempotent)."""
    return _get_store().delete_document_chunks(document_id)


def delete_chunk_ids(chunk_ids: List[str]) -> bool:
    """Delete specific chunks by ID (idempotent, no-op if empty)."""
    return _get_store().delete_chunk_ids(chunk_ids)


# ── Chunk corpus accessors — used by query_router / citation ────────────────

def _load_chunks_store() -> Dict[str, List[Dict]]:
    """Return every chunk grouped by ``document_id`` for BM25 / citation.

    In cluster mode the corpus is read from Milvus (no per-pod JSON co-store).
    In lite mode it is read from the local JSON co-store.  The module-level
    ``CHUNKS_STORE_PATH`` is honoured in lite mode so that tests may patch it.
    """
    store = _get_store()
    if config.VECTOR_STORE_MODE == "cluster":
        return store.all_chunks() or {}
    import json as _json
    from pathlib import Path
    try:
        p = Path(CHUNKS_STORE_PATH)
        if p.exists():
            with p.open("r", encoding="utf-8") as f:
                val = _json.load(f)
                return val if isinstance(val, dict) else {}
    except Exception as exc:
        logger.error("Co-store load error: %s", exc)
    return {}
