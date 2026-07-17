"""
Vector store factory — returns the correct backend based on VECTOR_STORE_MODE.

Usage::

    from app.core.vectorstore.factory import get_vector_store
    store = get_vector_store()
    store.insert_chunks(...)
"""

from __future__ import annotations

import logging

from app.core.vectorstore.base import VectorStoreProtocol
from app.utils.config import config

logger = logging.getLogger(__name__)

_store: VectorStoreProtocol | None = None


def get_vector_store() -> VectorStoreProtocol:
    """Return the singleton vector store instance.

    The concrete backend is chosen once at import time based on
    ``VECTOR_STORE_MODE``.  Switching at runtime is not supported.
    """
    global _store
    if _store is not None:
        return _store

    mode = config.VECTOR_STORE_MODE

    if mode == "lite":
        if config.SERVER_ENV in ("production", "staging"):
            logger.critical(
                "VECTOR_STORE_MODE=lite is not allowed in %s; "
                "set VECTOR_STORE_MODE=cluster and configure MILVUS_HOST/MILVUS_PORT",
                config.SERVER_ENV,
            )
            raise SystemExit(1)
        from app.core.vectorstore.milvus_lite import MilvusLiteStore
        _store = MilvusLiteStore()
        logger.info("Vector store initialised: MilvusLiteStore (mode=%s)", mode)
    elif mode == "cluster":
        from app.core.vectorstore.milvus_cluster import MilvusClusterStore
        _store = MilvusClusterStore()
        logger.info("Vector store initialised: MilvusClusterStore (mode=%s)", mode)
    else:
        logger.critical(
            "VECTOR_STORE_MODE must be either 'lite' or 'cluster', got %s",
            mode,
        )
        raise SystemExit(1)

    return _store


def reset_vector_store() -> None:
    """Reset the singleton (for tests only)."""
    global _store
    _store = None
