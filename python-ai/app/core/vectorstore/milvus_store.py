"""
Milvus vector store for storing and retrieving document chunks
Using Milvus Lite for local development
"""

import json
import os
from typing import List, Optional, Dict, Any
from pymilvus import (
    FieldSchema,
    CollectionSchema,
    DataType,
    MilvusClient
)
from app.utils.config import config
from app.core.chunker.text_chunker import VectorChunk


# Collection name
COLLECTION_NAME = "knowledge_chunks"

# Embedding dimension (BGE-M3 uses 1024)
EMBEDDING_DIM = 1024

# Milvus Lite database path
MILVUS_LITE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "milvus_data.db")

# Global client
_client: Optional[MilvusClient] = None


def get_milvus_client() -> Optional[MilvusClient]:
    """Get or create Milvus client (using Milvus Lite)"""
    global _client
    try:
        if _client is None:
            # Use Milvus Lite for local development
            _client = MilvusClient(uri=MILVUS_LITE_PATH)
            print(f"[Milvus] Connected to Milvus Lite at {MILVUS_LITE_PATH}")
        return _client
    except Exception as e:
        print(f"Failed to connect to Milvus: {e}")
        return None


def create_collection():
    """Create collection if not exists"""
    try:
        client = get_milvus_client()
        if client is None:
            return None

        # Check if collection exists
        if client.has_collection(COLLECTION_NAME):
            return client

        # Define fields
        fields = [
            FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, is_primary=True, max_length=128),
            FieldSchema(name="document_id", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="block_type", dtype=DataType.VARCHAR, max_length=20),
            FieldSchema(name="outline_path", dtype=DataType.VARCHAR, max_length=2000),
            FieldSchema(name="metadata", dtype=DataType.VARCHAR, max_length=4000),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM)
        ]

        # Create schema
        schema = CollectionSchema(fields=fields, description="Document chunks for RAG")

        # Create index params
        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            metric_type="COSINE",
            index_type="IVF_FLAT",
            params={"nlist": 128}
        )

        # Create collection
        client.create_collection(
            collection_name=COLLECTION_NAME,
            schema=schema,
            index_params=index_params
        )

        print(f"Created collection: {COLLECTION_NAME}")
        return client

    except Exception as e:
        print(f"Failed to create collection: {e}")
        return None


def insert_chunks(chunks: List[VectorChunk], embeddings: List[List[float]], document_id: str) -> bool:
    """Insert chunks with embeddings into Milvus"""
    try:
        client = create_collection()
        if client is None:
            return False

        # Prepare data
        data = []
        for chunk, embedding in zip(chunks, embeddings):
            # Convert outline_path list to JSON string
            outline_path_str = json.dumps(chunk.outline_path) if chunk.outline_path else "[]"

            data.append({
                "chunk_id": chunk.chunk_id,
                "document_id": document_id,
                "content": chunk.content,
                "block_type": chunk.block_type,
                "outline_path": outline_path_str,
                "metadata": json.dumps(chunk.metadata) if chunk.metadata else "{}",
                "embedding": embedding
            })

        # Insert data
        client.insert(
            collection_name=COLLECTION_NAME,
            data=data
        )

        print(f"Inserted {len(data)} chunks into Milvus")

        # Also save to local JSON store for reliable querying
        store_records = []
        for chunk, embedding in zip(chunks, embeddings):
            outline_path_str = json.dumps(chunk.outline_path) if chunk.outline_path else "[]"
            store_records.append({
                "chunk_id": chunk.chunk_id,
                "document_id": document_id,
                "content": chunk.content,
                "block_type": chunk.block_type,
                "outline_path": outline_path_str,
                "metadata": json.dumps(chunk.metadata) if chunk.metadata else "{}"
            })
        _save_chunks_to_store(document_id, store_records)

        return True

    except Exception as e:
        print(f"Failed to insert chunks: {e}")
        return False


def search_similar(query_embedding: List[float], top_k: int = 5, document_id: Optional[str] = None) -> List[Dict]:
    """Search for similar chunks"""
    try:
        client = get_milvus_client()
        if client is None:
            return []

        # Load collection before search
        client.load_collection(COLLECTION_NAME)

        # Build search params
        search_params = {
            "metric_type": "COSINE",
            "params": {"nprobe": 16}
        }

        # Build filter
        filter_expr = None
        if document_id:
            filter_expr = f'document_id == "{document_id}"'

        # Search
        results = client.search(
            collection_name=COLLECTION_NAME,
            data=[query_embedding],
            limit=top_k,
            search_params=search_params,
            output_fields=["chunk_id", "document_id", "content", "block_type", "outline_path", "metadata"],
            filter=filter_expr
        )

        # Format results
        formatted_results = []
        for hits in results:
            for hit in hits:
                # Convert outline_path from JSON string back to list
                outline_path = hit.get("outline_path", "[]")
                if isinstance(outline_path, str):
                    try:
                        outline_path = json.loads(outline_path)
                    except:
                        outline_path = []

                formatted_results.append({
                    "chunk_id": hit.get("chunk_id"),
                    "document_id": hit.get("document_id"),
                    "content": hit.get("content"),
                    "block_type": hit.get("block_type"),
                    "outline_path": outline_path,
                    "metadata": json.loads(hit.get("metadata", "{}")),
                    "score": hit.get("distance")
                })

        return formatted_results

    except Exception as e:
        print(f"Failed to search: {e}")
        return []


# Local chunk metadata store (JSON file) - Milvus Lite's query() API is unreliable
CHUNKS_STORE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "chunks_store.json")


def _load_chunks_store() -> Dict[str, List[Dict]]:
    """Load chunks metadata from local JSON file"""
    try:
        if os.path.exists(CHUNKS_STORE_PATH):
            with open(CHUNKS_STORE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"[ChunksStore] Load error: {e}")
    return {}


def _save_chunks_store(store: Dict[str, List[Dict]]):
    """Save chunks metadata to local JSON file"""
    try:
        with open(CHUNKS_STORE_PATH, 'w', encoding='utf-8') as f:
            json.dump(store, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ChunksStore] Save error: {e}")


def _save_chunks_to_store(document_id: str, chunks: List[Dict]):
    """Save document chunks to local store"""
    store = _load_chunks_store()
    store[document_id] = chunks
    _save_chunks_store(store)


def get_document_chunks(document_id: str, page: int = 1, size: int = 20, block_type: Optional[str] = None) -> Dict:
    """Get chunks for a document from local store"""
    try:
        store = _load_chunks_store()
        all_chunks = store.get(str(document_id), [])

        # Filter by block_type if specified
        if block_type:
            all_chunks = [c for c in all_chunks if c.get("block_type") == block_type]

        total = len(all_chunks)

        # Paginate
        start = (page - 1) * size
        end = start + size
        records = all_chunks[start:end]

        return {
            "code": 200,
            "data": {
                "records": records,
                "total": total,
                "page": page,
                "size": size
            }
        }

    except Exception as e:
        print(f"Failed to get chunks: {e}")
        return {"code": 500, "message": str(e)}


def get_chunk_detail(chunk_id: str) -> Optional[Dict]:
    """Get single chunk detail"""
    try:
        client = get_milvus_client()
        if client is None:
            return None

        results = client.query(
            collection_name=COLLECTION_NAME,
            filter=f'chunk_id == "{chunk_id}"',
            output_fields=["chunk_id", "document_id", "content", "block_type", "outline_path", "metadata"]
        )

        if results:
            return results[0]
        return None

    except Exception as e:
        print(f"Failed to get chunk: {e}")
        return None


def delete_document_chunks(document_id: str) -> bool:
    """Delete all chunks for a document"""
    try:
        client = get_milvus_client()
        if client is None:
            return False

        # Delete by filter
        client.delete(
            collection_name=COLLECTION_NAME,
            filter=f'document_id == "{document_id}"'
        )

        print(f"Deleted chunks for document: {document_id}")
        return True

    except Exception as e:
        print(f"Failed to delete chunks: {e}")
        return False
