"""
Pydantic models for document vectorization
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class BlockType(str, Enum):
    """Block types for parsed content"""
    HEADING = "HEADING"
    PARAGRAPH = "PARAGRAPH"
    CODE = "CODE"
    TABLE = "TABLE"
    LIST = "LIST"
    IMAGE = "IMAGE"


class ParseRequest(BaseModel):
    """Request for parsing a document"""
    document_id: str = Field(..., description="Document ID")
    file_path: str = Field(..., description="Path to the file")
    file_type: str = Field(..., description="File type: md, txt, pdf, docx")
    callback_url: str | None = Field(None, description="Callback URL for notifications")
    callback_secret: str | None = Field(None, description="Secret for callback authentication")
    knowledge_base_id: int | None = Field(None, description="Knowledge base ID")
    document_title: str | None = Field(None, description="Document title for citations")
    index_version: str = Field(..., description="Java-issued index version used to reject stale callbacks")
    embedding_model: str | None = Field(None, description="Embedding model to use: ollama or random")
    embedding_dimension: int | None = Field(None, description="Embedding vector dimension")
    embedding_version: str | None = Field(None, description="Embedding version identifier")


class ParsedBlock(BaseModel):
    """A parsed block of content"""
    content: str = Field(..., description="Block content")
    block_type: BlockType = Field(..., description="Block type")
    level: int | None = Field(None, description="Heading level (1-6)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class VectorChunk(BaseModel):
    """A chunk ready for vectorization"""
    chunk_id: str = Field(..., description="Unique chunk identifier")
    index: int = Field(..., description="Chunk index in document")
    content: str = Field(..., description="Chunk content")
    block_type: str = Field(..., description="Block type")
    outline_path: list[str] = Field(default_factory=list, description="Chapter hierarchy path")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ParseResponse(BaseModel):
    """Response from parsing"""
    success: bool = Field(..., description="Success status")
    document_id: str = Field(..., description="Document ID")
    blocks_count: int = Field(..., description="Number of parsed blocks")
    chunks_count: int = Field(..., description="Number of chunks created")
    message: str | None = Field(None, description="Status message")


class ChunkResponse(BaseModel):
    """Response with chunks for a document"""
    success: bool = Field(..., description="Success status")
    document_id: str = Field(..., description="Document ID")
    total_chunks: int = Field(..., description="Total number of chunks")
    chunks: list[VectorChunk] = Field(..., description="List of chunks")


class VectorChunkResponse(BaseModel):
    """Detailed chunk information"""
    chunk_id: str = Field(..., description="Chunk ID")
    document_id: str = Field(..., description="Document ID")
    content: str = Field(..., description="Chunk content")
    block_type: str = Field(..., description="Block type")
    outline_path: list[str] = Field(default_factory=list, description="Chapter path")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadata")
    embedding: list[float] | None = Field(None, description="Vector embedding")


class SearchRequest(BaseModel):
    """Request for searching similar content"""
    query: str = Field(..., description="Search query")
    top_k: int = Field(5, description="Number of results to return")
    collection_name: str | None = Field(None, description="Collection name")
    knowledge_base_id: int | None = Field(None, description="Filter by knowledge base ID")


class SearchResult(BaseModel):
    """A single search result"""
    chunk_id: str = Field(..., description="Chunk ID")
    document_id: str = Field(..., description="Document ID")
    content: str = Field(..., description="Chunk content")
    score: float = Field(..., description="Similarity score")
    block_type: str = Field(..., description="Block type")
    outline_path: list[str] = Field(default_factory=list, description="Chapter path")


class SearchResponse(BaseModel):
    """Response from search"""
    success: bool = Field(..., description="Success status")
    query: str = Field(..., description="Original query")
    results: list[SearchResult] = Field(..., description="Search results")


class CallbackRequest(BaseModel):
    """Callback request to Java backend"""
    document_id: str = Field(..., description="Document ID")
    success: bool = Field(..., description="Processing success status")
    message: str = Field(..., description="Status message")
    chunks_count: int = Field(0, description="Number of chunks processed")


class VectorCountsRequest(BaseModel):
    """Request for vector-store entity counts grouped by knowledge base.

    Used by the Java backend's reconciliation health check: the Java side
    compares these Milvus counts against its durable ``document_chunk`` table
    and raises an explicit alarm when they drift (e.g. after a vector-store
    volume is recreated while MySQL still holds chunk metadata).
    """
    knowledge_base_ids: list[int] = Field(..., description="Knowledge base IDs to count entities for")
