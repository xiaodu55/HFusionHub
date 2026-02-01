"""
Vectorization API Routes - FastAPI Version
Handles document parsing, chunking, and vectorization
"""

import os
import requests
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks

from app.models.document import (
    ParseRequest,
    ParseResponse,
    ChunkResponse,
    VectorChunkResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
    CallbackRequest,
    VectorChunk
)
from app.core.parser.base import BaseParser
from app.core.chunker.text_chunker import chunk_blocks
from app.core.embedding import get_embedding_service
from app.core.exceptions import (
    ParsingException,
    VectorizationException,
    EmbeddingException,
    CallbackException,
    MilvusException
)
from app.core.vectorstore.milvus_store import (
    create_collection,
    insert_chunks,
    search_similar,
    get_document_chunks,
    delete_document_chunks
)
from app.utils.config import config
from app.utils.validators import (
    validate_file_upload,
    validate_document_id
)

router = APIRouter()


@router.post("/api/test")
async def test_endpoint(data: dict):
    """Test endpoint"""
    return {"received": data}


@router.post("/api/parse-simple")
async def parse_simple(data: dict):
    """Simple parse endpoint for testing"""
    print(f"[Vectorization] Simple parse: {data}")
    return {"success": True, "message": "Simple parse works"}


@router.post("/api/parse-model")
async def parse_model(request: ParseRequest):
    """Parse endpoint with Pydantic model for testing"""
    print(f"[Vectorization] Model parse: {request.document_id}")
    return {"success": True, "document_id": request.document_id}


@router.post("/api/parse")
async def parse_document(request: ParseRequest, background_tasks: BackgroundTasks):
    """
    Parse a document and store chunks with vector embeddings
    """
    print(f"[Vectorization] Received parse request: {request.document_id}")
    try:
        # Step 0: Validate request
        validate_document_id(request.document_id)
        validate_file_upload(
            file_path=request.file_path,
            file_type=request.file_type,
            check_size=True
        )
        print(f"[Vectorization] Validation passed")

        # Step 1: Parse document
        print(f"[Vectorization] Parsing document: {request.document_id}")
        parser = BaseParser.get_parser(request.file_type)
        blocks = parser.parse(request.file_path)
        print(f"[Vectorization] Parsed {len(blocks)} blocks")

        # Step 2: Chunk blocks
        print(f"[Vectorization] Chunking blocks...")
        chunks = chunk_blocks(blocks, request.document_id)
        print(f"[Vectorization] Created {len(chunks)} chunks")

        # Step 3: Create/update Milvus collection
        print(f"[Vectorization] Creating Milvus collection...")
        create_collection()

        # Step 4: Generate embeddings and store
        print(f"[Vectorization] Generating embeddings...")
        chunks_with_embeddings = []
        for i, chunk in enumerate(chunks):
            embedding = await _generate_embedding(chunk.content)
            chunk_dict = chunk.to_dict()
            chunk_dict['embedding'] = embedding
            chunks_with_embeddings.append(chunk_dict)
            if (i + 1) % 10 == 0:
                print(f"[Vectorization] Processed {i + 1}/{len(chunks)} chunks")

        # Step 5: Insert into Milvus
        print(f"[Vectorization] Inserting chunks into Milvus...")
        embeddings = [c['embedding'] for c in chunks_with_embeddings]
        insert_chunks(chunks, embeddings, request.document_id)

        # Step 6: Notify Java backend
        if request.callback_url:
            background_tasks.add_task(
                _notify_callback,
                callback_url=request.callback_url,
                callback_secret=request.callback_secret,
                document_id=request.document_id,
                success=True,
                message=f"Successfully parsed document into {len(chunks)} chunks",
                chunks_count=len(chunks)
            )

        print(f"[Vectorization] Completed: {len(chunks)} chunks stored")
        return ParseResponse(
            success=True,
            document_id=request.document_id,
            blocks_count=len(blocks),
            chunks_count=len(chunks),
            message="Document parsed and vectorized successfully"
        )

    except Exception as e:
        print(f"[Vectorization] Error: {str(e)}")
        import traceback
        traceback.print_exc()

        # Notify failure
        if request.callback_url:
            background_tasks.add_task(
                _notify_callback,
                callback_url=request.callback_url,
                callback_secret=request.callback_secret,
                document_id=request.document_id,
                success=False,
                message=f"Parsing failed: {str(e)}",
                chunks_count=0
            )

        raise VectorizationException(str(e))


@router.get("/api/chunks/{document_id}", response_model=ChunkResponse)
async def get_chunks(document_id: str, page: int = 1, size: int = 20, block_type: str = None):
    """Get all chunks for a document"""
    try:
        validate_document_id(document_id)

        result = get_document_chunks(document_id, page, size, block_type)

        if result.get("code") != 200:
            raise MilvusException(result.get("message", "获取分块失败"))

        data = result.get("data", {})
        records = data.get("records", [])
        total = data.get("total", 0)

        chunks = []
        for record in records:
            # Parse outline_path from JSON string to list
            outline_path = record.get("outline_path", "[]")
            if isinstance(outline_path, str):
                import json
                try:
                    outline_path = json.loads(outline_path)
                except:
                    outline_path = []

            chunks.append(VectorChunk(
                chunk_id=record.get("chunk_id", ""),
                index=0,
                content=record.get("content", ""),
                block_type=record.get("block_type", "PARAGRAPH"),
                outline_path=outline_path,
                metadata={}
            ))

        return ChunkResponse(
            success=True,
            document_id=document_id,
            total_chunks=total,
            chunks=chunks
        )

    except Exception as e:
        raise MilvusException(f"获取分块列表失败: {e}")


@router.get("/api/chunks/detail/{chunk_id}", response_model=VectorChunkResponse)
async def get_chunk_detail(chunk_id: str, document_id: str):
    """Get detailed chunk information including embedding"""
    try:
        validate_document_id(document_id)

        chunks = get_document_chunks(config.MILVUS_COLLECTION, document_id)

        for chunk in chunks:
            if chunk.get('chunk_id') == chunk_id:
                return VectorChunkResponse(**chunk)

        from app.core.exceptions import ValidationException
        raise ValidationException(f"分块不存在: {chunk_id}", code=404)

    except Exception as e:
        raise MilvusException(f"获取分块详情失败: {e}")


@router.post("/api/search", response_model=SearchResponse)
async def search_chunks(request: SearchRequest):
    """Search for similar chunks"""
    try:
        # Generate query embedding
        try:
            query_embedding = await _generate_embedding(request.query)
        except Exception as e:
            raise EmbeddingException(f"生成查询向量失败: {e}")

        # Search in Milvus
        try:
            results = search_similar(query_embedding, request.top_k)
        except Exception as e:
            raise MilvusException(f"搜索失败: {e}")

        return SearchResponse(
            success=True,
            query=request.query,
            results=[SearchResult(**result) for result in results]
        )

    except Exception as e:
        raise VectorizationException(str(e))


async def _generate_embedding(text: str) -> List[float]:
    """
    Generate embedding using multi-strategy service
    Strategy: Ollama BGE-M3 -> DeepSeek API -> Random vectors
    """
    service = get_embedding_service()
    return await service.generate(text)


def _notify_callback(
    callback_url: str,
    document_id: str,
    success: bool,
    message: str,
    chunks_count: int,
    callback_secret: str = None
):
    """Notify Java backend about processing completion"""
    try:
        # Convert to Java backend expected format
        status = "COMPLETED" if success else "FAILED"
        payload = {
            "document_id": document_id,
            "status": status,
            "chunkCount": chunks_count,
            "message": message
        }

        headers = {"Content-Type": "application/json"}
        if callback_secret:
            headers["X-Callback-Secret"] = callback_secret

        response = requests.post(
            callback_url,
            json=payload,
            headers=headers,
            timeout=10
        )

        if response.status_code >= 400:
            print(f"[Callback] Warning: {callback_url} returned {response.status_code}")
        else:
            print(f"[Callback] Notified {callback_url}: {response.status_code}")

    except requests.exceptions.Timeout:
        print(f"[Callback] Timeout: {callback_url}")
    except requests.exceptions.ConnectionError:
        print(f"[Callback] Connection failed: {callback_url}")
    except Exception as e:
        print(f"[Callback] Failed to notify: {str(e)}")
