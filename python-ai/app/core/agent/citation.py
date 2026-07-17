"""
Canonical source citation — Agent V1.

Every retrieval result, regardless of its origin (sync ``run()`` path,
streaming ``run_stream()`` path, or ReAct tool execution), is normalised
through the single function ``normalize_source()`` defined here.

Both the sync and SSE code paths MUST call this function — never
hand-roll a source dict.  The function is **idempotent**: calling it
twice on the same input produces the same output.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Canonical keys produced by normalize_source ──
CANONICAL_SOURCE_KEYS = frozenset({
    "document_id", "chunk_id", "title", "excerpt", "score",
    "knowledge_base_id",
})

# Sentinel returned when every extraction path fails.
_EMPTY_CITATION: dict[str, Any] = {
    "document_id": None,
    "chunk_id": None,
    "title": "",
    "excerpt": "",
    "score": 0.0,
    "knowledge_base_id": None,
}


def _is_canonical(source: dict[str, Any]) -> bool:
    """Return True when *source* is already in canonical Agent V1 format."""
    return CANONICAL_SOURCE_KEYS.issubset(source.keys())


def _extract_document_id(source: dict[str, Any]) -> int | None:
    raw = source.get("document_id")
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    return None


def _extract_chunk_id(source: dict[str, Any]) -> str | None:
    chunk_id = source.get("chunk_id")
    if chunk_id is not None:
        return str(chunk_id)
    # Some metadata dicts carry chunk_id inside them.
    meta = source.get("metadata")
    if isinstance(meta, dict):
        cid = meta.get("chunk_id")
        if cid is not None:
            return str(cid)
    return None


def _lookup_chunk_in_store(chunk_id: str | None) -> dict[str, Any] | None:
    """Look up a single chunk in the persistent JSON store.

    Used as a last-resort fallback when the in-memory metadata carried
    through the retrieval pipeline is missing ``document_title`` or
    ``content``.
    """
    if not chunk_id:
        return None
    try:
        # Lazy import — the chunk store lives inside the vectorstore package
        # and we don't want a hard dependency from the citation module.
        from app.core.vectorstore.milvus_store import _load_chunks_store

        store = _load_chunks_store()
        for doc_id, chunks in store.items():
            for chunk in chunks:
                if chunk.get("chunk_id") == chunk_id:
                    return chunk
    except Exception:
        pass
    return None


def _extract_title(source: dict[str, Any], doc_id: int | None) -> str:
    """Extract the best available title, logging when we must fall back."""
    # Prefer document_title from metadata (the raw retrieval path).
    meta = source.get("metadata")
    if isinstance(meta, dict):
        dt = meta.get("document_title")
        if dt:
            return str(dt)

    # Already-normalized source may carry "title" directly.
    title = source.get("title")
    if title:
        return str(title)

    # Some tool paths attach document_name at the top level.
    doc_name = source.get("document_name")
    if doc_name:
        return str(doc_name)

    # ── Persistent chunk-store fallback ───────────────────────────────
    chunk_id = _extract_chunk_id(source)
    chunk = _lookup_chunk_in_store(chunk_id)
    if chunk:
        meta = chunk.get("metadata")
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except (json.JSONDecodeError, TypeError):
                meta = {}
        if isinstance(meta, dict):
            dt = meta.get("document_title")
            if dt:
                logger.info("Title recovered from persistent chunk store for %s", chunk_id)
                return str(dt)
        # Also check top-level document_name on the chunk record.
        dn = chunk.get("document_name")
        if dn:
            logger.info("Title recovered from persistent chunk store for %s", chunk_id)
            return str(dn)

    # Last resort: log and fall back.
    logger.warning(
        "Citation has no document_title in metadata and no title field. "
        "source keys: %s",
        list(source.keys())[:10],
    )
    return f"文档 #{doc_id}" if doc_id else "未知文档"


def _extract_excerpt(source: dict[str, Any]) -> str:
    """Extract the best available excerpt (first 300 chars)."""
    # Already-normalized.
    excerpt = source.get("excerpt")
    if excerpt:
        return str(excerpt)[:300]

    # Raw retrieval dict — content is the full chunk text.
    content = source.get("content")
    if content:
        return str(content)[:300]

    # Some tool results nest content.
    result = source.get("result")
    if isinstance(result, dict):
        inner = result.get("content") or result.get("excerpt")
        if inner:
            return str(inner)[:300]

    # ── Persistent chunk-store fallback ───────────────────────────────
    chunk_id = _extract_chunk_id(source)
    chunk = _lookup_chunk_in_store(chunk_id)
    if chunk:
        content = chunk.get("content")
        if content:
            logger.info("Excerpt recovered from persistent chunk store for %s", chunk_id)
            return str(content)[:300]

    # Nothing usable.
    logger.warning(
        "Citation has no excerpt or content. source keys: %s",
        list(source.keys())[:10],
    )
    return ""


def _extract_score(source: dict[str, Any]) -> float:
    try:
        return float(source.get("score", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _extract_kb_id(source: dict[str, Any]) -> int | None:
    """Extract the knowledge-base id, preferring metadata then top level.

    Present on retrieval results produced inside a knowledge base scope.
    Returns ``None`` when the source carries no scoping information.
    """
    meta = source.get("metadata")
    if isinstance(meta, dict):
        raw = meta.get("knowledge_base_id")
        if raw is not None:
            try:
                return int(raw)
            except (TypeError, ValueError):
                pass
    raw = source.get("knowledge_base_id")
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    return None


def normalize_source(
    source: dict[str, Any] | Any,
) -> dict[str, Any]:
    """Normalise a single retrieval result into canonical Agent V1 format.

    This is the **single choke point** for source citations.  Every code
    path that produces a source MUST route through this function.

    Accepted inputs (the function sniffs and normalises):

    * **Dict, already canonical** — ``{document_id, chunk_id, title,
      excerpt, score}`` → returned as-is (idempotent).
    * **Dict, raw retrieval** — ``{content, metadata: {document_title,
      chunk_id, …}, document_id, score}`` → normalised.
    * **ProcessedResult / SearchResult object** — attributes ``content``,
      ``metadata``, ``document_id``, ``chunk_id``, ``score`` are read
      via ``getattr``.
    * **Any other object** with ``metadata`` attribute → attempted.

    Returns:
        Dict with keys ``document_id``, ``chunk_id``, ``title``,
        ``excerpt``, ``score``.  Missing values are logged and filled
        with safe defaults — the function **never** returns an empty
        ``title`` or ``excerpt`` without logging a warning first.
    """
    # ── Normalise to plain dict ──────────────────────────────────────
    if isinstance(source, dict):
        d = source
    else:
        # Object with attributes (ProcessedResult, SearchResult, etc.)
        metadata = getattr(source, "metadata", {}) or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                metadata = {}

        d = {
            "document_id": getattr(source, "document_id", None),
            "chunk_id": getattr(source, "chunk_id", None),
            "content": getattr(source, "content", ""),
            "score": getattr(source, "score", 0.0) or 0.0,
            "metadata": metadata,
            "knowledge_base_id": getattr(source, "knowledge_base_id", None),
        }

    # ── Already canonical → return as-is ─────────────────────────────
    if _is_canonical(d):
        return {
            "document_id": d["document_id"],
            "chunk_id": d["chunk_id"],
            "title": d["title"],
            "excerpt": d["excerpt"],
            "score": d["score"],
            "knowledge_base_id": d.get("knowledge_base_id"),
        }

    # ── Normalise from raw format ────────────────────────────────────
    doc_id = _extract_document_id(d)
    chunk_id = _extract_chunk_id(d)

    title = _extract_title(d, doc_id)
    excerpt = _extract_excerpt(d)
    score = _extract_score(d)
    knowledge_base_id = _extract_kb_id(d)

    return {
        "document_id": doc_id,
        "chunk_id": chunk_id,
        "title": title,
        "excerpt": excerpt,
        "score": score,
        "knowledge_base_id": knowledge_base_id,
    }
