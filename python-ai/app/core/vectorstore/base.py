"""
Abstract vector store protocol.

Every vector store backend must implement this interface so that the indexing
pipeline, retrieval pipeline, and reconciliation services can operate against
any backend without knowing the concrete implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class VectorStoreStatus:
    """Standardised health / readiness payload."""
    ready: bool
    collection: str
    collection_exists: bool = False
    mode: str = "unknown"
    error: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


class VectorStoreProtocol(ABC):
    """Abstract interface for a vector store backend.

    Implementations must be thread-safe and support lazy initialisation so that
    the application can start even if the vector store is temporarily
    unreachable.
    """

    # ── Lifecycle ────────────────────────────────────────────────────────────

    @abstractmethod
    def status(self) -> VectorStoreStatus:
        """Return a safe readiness summary (never raises)."""

    @abstractmethod
    def ensure_collection(self) -> Optional[Any]:
        """Create the collection if it does not exist.

        Returns the connected client on success, or ``None`` if the store is
        unavailable.  Must NOT drop an existing collection with incompatible
        schema — return ``None`` and log an error instead.
        """

    @abstractmethod
    def drop_collection(self) -> bool:
        """Drop the collection (gated by an env var in production)."""

    # ── Write ────────────────────────────────────────────────────────────────

    @abstractmethod
    def insert_chunks(
        self,
        chunk_ids: List[str],
        document_id: str,
        knowledge_base_id: int,
        contents: List[str],
        block_types: List[str],
        outline_paths: List[str],
        metadatas: List[str],
        embeddings: List[List[float]],
    ) -> bool:
        """Insert pre-embedded chunks into the vector store.

        All lists must have the same length.  Implementations should mirror
        chunk metadata to the JSON co-store for BM25 / chunk browsing.
        """

    @abstractmethod
    def delete_document_chunks(self, document_id: str) -> bool:
        """Delete all chunks belonging to *document_id* (idempotent)."""

    @abstractmethod
    def delete_chunk_ids(self, chunk_ids: List[str]) -> bool:
        """Delete specific chunks by ID (idempotent, no-op if empty)."""

    # ── Read ─────────────────────────────────────────────────────────────────

    @abstractmethod
    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        document_id: Optional[str] = None,
        knowledge_base_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Vector similarity search.

        Returns a list of dicts with at least:
        ``chunk_id, document_id, knowledge_base_id, content, score``.
        """

    @abstractmethod
    def get_document_chunks(
        self,
        document_id: str,
        page: int = 1,
        size: int = 20,
        block_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Paginated chunk listing from the JSON co-store."""

    @abstractmethod
    def get_chunk_detail(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """Single chunk detail (from Milvus query or JSON co-store)."""

    # ── Reconciliation helpers ───────────────────────────────────────────────

    @abstractmethod
    def list_all_chunk_ids(self, knowledge_base_id: Optional[int] = None) -> List[str]:
        """Return every chunk_id in the vector store, optionally filtered by KB.

        Used by the reconciliation job to detect orphan vectors.
        """

    @abstractmethod
    def count_chunks(self, knowledge_base_id: Optional[int] = None) -> int:
        """Return total chunk count, optionally filtered by KB."""

    @abstractmethod
    def all_chunks(self, knowledge_base_id: Optional[int] = None) -> Dict[str, List[Dict[str, Any]]]:
        """Return every chunk grouped by ``document_id`` (for BM25 / citation).

        Keys are document_ids; each value is a list of chunk metadata dicts with
        ``chunk_id``, ``document_id``, ``knowledge_base_id``, ``content``,
        ``block_type``, ``outline_path`` and ``metadata``.
        """
