"""
Pydantic models for document vectorization
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


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
    callback_url: Optional[str] = Field(None, description="Callback URL for notifications")
    callback_secret: Optional[str] = Field(None, description="Secret for callback authentication")
    knowledge_base_id: Optional[int] = Field(None, description="Knowledge base ID")
    document_title: Optional[str] = Field(None, description="Document title for citations")
    index_version: str = Field(..., description="Java-issued index version used to reject stale callbacks")
    embedding_model: Optional[str] = Field(None, description="Embedding model to use: ollama, deepseek, or random")


class ParsedBlock(BaseModel):
    """A parsed block of content"""
    content: str = Field(..., description="Block content")
    block_type: BlockType = Field(..., description="Block type")
    level: Optional[int] = Field(None, description="Heading level (1-6)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class VectorChunk(BaseModel):
    """A chunk ready for vectorization"""
    chunk_id: str = Field(..., description="Unique chunk identifier")
    index: int = Field(..., description="Chunk index in document")
    content: str = Field(..., description="Chunk content")
    block_type: str = Field(..., description="Block type")
    outline_path: List[str] = Field(default_factory=list, description="Chapter hierarchy path")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ParseResponse(BaseModel):
    """Response from parsing"""
    success: bool = Field(..., description="Success status")
    document_id: str = Field(..., description="Document ID")
    blocks_count: int = Field(..., description="Number of parsed blocks")
    chunks_count: int = Field(..., description="Number of chunks created")
    message: Optional[str] = Field(None, description="Status message")


class ChunkResponse(BaseModel):
    """Response with chunks for a document"""
    success: bool = Field(..., description="Success status")
    document_id: str = Field(..., description="Document ID")
    total_chunks: int = Field(..., description="Total number of chunks")
    chunks: List[VectorChunk] = Field(..., description="List of chunks")


class VectorChunkResponse(BaseModel):
    """Detailed chunk information"""
    chunk_id: str = Field(..., description="Chunk ID")
    document_id: str = Field(..., description="Document ID")
    content: str = Field(..., description="Chunk content")
    block_type: str = Field(..., description="Block type")
    outline_path: List[str] = Field(default_factory=list, description="Chapter path")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata")
    embedding: Optional[List[float]] = Field(None, description="Vector embedding")


class SearchRequest(BaseModel):
    """Request for searching similar content"""
    query: str = Field(..., description="Search query")
    top_k: int = Field(5, description="Number of results to return")
    collection_name: Optional[str] = Field(None, description="Collection name")
    knowledge_base_id: Optional[int] = Field(None, description="Filter by knowledge base ID")


class SearchResult(BaseModel):
    """A single search result"""
    chunk_id: str = Field(..., description="Chunk ID")
    document_id: str = Field(..., description="Document ID")
    content: str = Field(..., description="Chunk content")
    score: float = Field(..., description="Similarity score")
    block_type: str = Field(..., description="Block type")
    outline_path: List[str] = Field(default_factory=list, description="Chapter path")


class SearchResponse(BaseModel):
    """Response from search"""
    success: bool = Field(..., description="Success status")
    query: str = Field(..., description="Original query")
    results: List[SearchResult] = Field(..., description="Search results")


class CallbackRequest(BaseModel):
    """Callback request to Java backend"""
    document_id: str = Field(..., description="Document ID")
    success: bool = Field(..., description="Processing success status")
    message: str = Field(..., description="Status message")
    chunks_count: int = Field(0, description="Number of chunks processed")
