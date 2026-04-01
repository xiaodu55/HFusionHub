"""
Vector store abstraction layer.

The singleton instance is obtained via :func:`get_vector_store`.  Module-level
convenience functions are re-exported for backward compatibility with existing
callers that import from ``app.core.vectorstore.milvus_store``.
"""

from app.core.vectorstore.base import VectorStoreProtocol, VectorStoreStatus
from app.core.vectorstore.factory import get_vector_store, reset_vector_store
from app.core.vectorstore.milvus_lite import MilvusLiteStore
from app.core.vectorstore.milvus_cluster import MilvusClusterStore

__all__ = [
    "VectorStoreProtocol",
    "VectorStoreStatus",
    "get_vector_store",
    "reset_vector_store",
    "MilvusLiteStore",
    "MilvusClusterStore",
]
