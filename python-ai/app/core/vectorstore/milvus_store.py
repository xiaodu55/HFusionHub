"""
Milvus vector store — backward-compatible facade.

All production logic lives in :mod:`milvus_lite` or :mod:`milvus_cluster`
selected by the ``VECTOR_STORE_MODE`` env var.  This module re-exports the
same public API so that existing callers continue to work unchanged.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from typing import Any

from app.core.chunker.text_chunker import VectorChunk
from app.core.security.clearance import DEFAULT_VISIBILITY
from app.core.vectorstore.milvus_lite import CHUNKS_STORE_PATH as _CO_STORE_DEFAULT
from app.core.vectorstore.milvus_lite import MILVUS_LITE_PATH as _LITE_PATH_DEFAULT
from app.core.vectorstore.milvus_lite import _migrate_co_store_layout
from app.utils.config import config

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


def vector_store_status() -> dict[str, Any]:
    """Return a safe readiness summary for health checks and diagnostics.

    In lite mode this also triggers the lazy ensure/migration so that a failed
    tenant_id backfill surfaces here and is reported as NOT ready (fail-closed).
    """
    # If tests have patched get_milvus_client to return None, use the
    # module-level _last_connection_error for the error message.
    patched_client = get_milvus_client()
    if patched_client is None and _last_connection_error is not None:
        return {
            "ready": False,
            "collection": config.MILVUS_COLLECTION,
            "error": _last_connection_error,
        }
    # Trigger ensure/migration so a failed migration blocks readiness.
    # (Cheap in cluster mode? ensure_collection is guarded by has_collection;
    # we only force the migration path for the file-backed lite store.)
    store = _get_store()
    if config.VECTOR_STORE_MODE != "cluster":
        store.ensure_collection()
    status = store.status()
    # A migration failure recorded on the store must flip readiness off.
    last_error = getattr(store, "_last_error", None)
    if last_error:
        status.ready = False
        status.error = status.error or last_error
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
    chunks: list[VectorChunk],
    embeddings: list[list[float]],
    document_id: str,
    knowledge_base_id: int | None = None,
) -> bool:
    """Insert chunks with embeddings into the vector store."""
    return _get_store().insert_chunks(chunks, embeddings, document_id, knowledge_base_id)
def _matches_metadata_filter(metadata: Any, metadata_filter: Any) -> bool:
    """元数据过滤谓词（Batch 5）：filter 为 {field: value} 等值匹配。

    - metadata/filter 均容忍 JSON 字符串形态（Milvus 返回的 metadata 已反序列化，
      但扩展字段可能是 str 值），比较前做 str 归一化。
    - expected 为 list/tuple/set 时按集合成员匹配（主体级 ACL 的
      ``{"visibility": ["general", ...]}`` 过滤依赖此语义）。
    - ``visibility`` 键缺失按缺省等级 general 处理：V85 之前索引的存量分块
      metadata 无该字段，其语义等价于 DB 的 DEFAULT 'general'，不能因字段
      缺失而对低权限主体整体消失。
    - filter 为空/None 恒真。"""
    if not metadata_filter:
        return True
    if isinstance(metadata, str):
        # co-store 里的 metadata 落盘为 JSON 字符串（milvus_lite.insert_chunks
        # 的 json.dumps），谓词必须自行解析，否则对非 dict 恒 False 会把
        # ACL/block_type 过滤下的全部候选清空。
        import json as _json
        try:
            metadata = _json.loads(metadata)
        except (TypeError, ValueError):
            metadata = None
    if not isinstance(metadata, dict) or not isinstance(metadata_filter, dict):
        return False
    for key, expected in metadata_filter.items():
        actual = metadata.get(key)
        if actual is None and key == "visibility":
            actual = DEFAULT_VISIBILITY
        if actual is None:
            return False
        if isinstance(expected, (list, tuple, set, frozenset)):
            if str(actual) not in {str(item) for item in expected}:
                return False
        elif isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
            if actual != expected:
                return False
        elif str(actual) != str(expected):
            return False
    return True

def search_similar(
    query_text: str | None = None,
    query_embedding: list[float] | None = None,
    top_k: int = 5,
    document_id: str | None = None,
    knowledge_base_id: int | None = None,
    metadata_filter: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Search for similar chunks.

    ``metadata_filter``（Batch 5）：{field: value} 等值过滤，作用于 chunk
    metadata（如 {"block_type": "TABLE"}）。后过滤实现：存储层先超额召回
    再按谓词筛选并截断到 top_k，不依赖 Milvus schema 变更。
    """
    return _get_store().search(
        query_text, query_embedding, top_k, document_id, knowledge_base_id,
        metadata_filter=metadata_filter,
    )



def get_document_chunks(
    document_id: str, page: int = 1, size: int = 20, block_type: str | None = None,
) -> dict[str, Any]:
    """Get paginated chunks for a document."""
    return _get_store().get_document_chunks(document_id, page, size, block_type)


def get_chunk_detail(chunk_id: str) -> dict[str, Any] | None:
    """Get single chunk detail."""
    return _get_store().get_chunk_detail(chunk_id)


def delete_document_chunks(document_id: str) -> bool:
    """Delete all chunks for a document (idempotent)."""
    return _get_store().delete_document_chunks(document_id)


def delete_chunk_ids(chunk_ids: list[str]) -> bool:
    """Delete specific chunks by ID (idempotent, no-op if empty)."""
    return _get_store().delete_chunk_ids(chunk_ids)


def count_chunks(knowledge_base_id: int | None = None) -> int:
    """Count vector entities, optionally scoped to a knowledge base.

    Used by the reconciliation endpoint that compares Milvus entity counts
    against the Java side's durable ``document_chunk`` table.
    """
    return _get_store().count_chunks(knowledge_base_id)


# ── Chunk corpus accessors — used by query_router / citation ────────────────

# Chunk-corpus cache for the lite co-store.  Without it every retrieval
# (BM25, graph, observability) re-reads + re-parses the whole corpus JSON on
# each request.  Keyed by (tenant_id → (mtime_ns, size)); writes go through
# the store's atomic ``os.replace`` so a changed mtime/size naturally
# invalidates the entry.  Cluster mode reads straight from Milvus and is
# never cached.
#
# 租户隔离（第十五轮 P0-2）：缓存值是「单个租户」的作用域语料，因此必须
# 按租户分键——单键缓存在双租户交替读取（期间无写入）时会把 A 租户语料
# 返回给 B 租户。按租户各持一份 (file_sig, scoped) 条目，LRU 上限封顶。
_co_store_cache: OrderedDict[str, tuple[tuple[int, int], dict[str, list[dict]]]] = OrderedDict()
_CO_STORE_CACHE_MAX = 8
_co_store_lock = threading.Lock()


def _load_chunks_store() -> dict[str, list[dict]]:
    """Return the active tenant's chunks grouped by ``document_id``.

    In cluster mode the corpus is read from Milvus (no per-pod JSON co-store).
    In lite mode it is read from the local JSON co-store, filtered to the
    current tenant.  The module-level ``CHUNKS_STORE_PATH`` is honoured in lite
    mode so that tests may patch it.  Lite reads are cached per-tenant by file
    mtime+size so hot retrieval paths do not re-read + re-parse the whole
    corpus per request; the cache is invalidated automatically when the file
    changes.
    """
    store = _get_store()
    if config.VECTOR_STORE_MODE == "cluster":
        return store.all_chunks() or {}
    import json as _json
    from pathlib import Path
    try:
        try:
            from app.core.tenant.context import require_tenant_id
            tid = str(require_tenant_id())
        except Exception:
            # 无租户上下文：不读文件也不动缓存（无法定位应失效的条目）
            return {}
        p = Path(CHUNKS_STORE_PATH)
        if not p.exists():
            with _co_store_lock:
                _co_store_cache.pop(tid, None)
            return {}
        st = p.stat()
        key = (st.st_mtime_ns, st.st_size)
        with _co_store_lock:
            entry = _co_store_cache.get(tid)
            if entry is not None and entry[0] == key:
                return entry[1]
            with p.open("r", encoding="utf-8") as f:
                val = _json.load(f)
            if not isinstance(val, dict):
                _co_store_cache.pop(tid, None)
                return {}
            # Tenant isolation: normalize to the tenant-keyed physical
            # layout, then return ONLY the active tenant's document root.
            val = _migrate_co_store_layout(val)
            tenant_root = val.get(tid, {})
            if not isinstance(tenant_root, dict):
                _co_store_cache.pop(tid, None)
                return {}
            scoped: dict[str, list[dict]] = {}
            for doc_id, chunks in tenant_root.items():
                for c in chunks:
                    scoped.setdefault(str(c.get("document_id", doc_id)), []).append(c)
            _co_store_cache[tid] = (key, scoped)
            _co_store_cache.move_to_end(tid)
            while len(_co_store_cache) > _CO_STORE_CACHE_MAX:
                _co_store_cache.popitem(last=False)
            return scoped
    except Exception as exc:
        logger.error("Co-store load error: %s", exc)
    return {}
