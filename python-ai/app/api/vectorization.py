"""
Vectorization API Routes - FastAPI Version
Handles document parsing, chunking, and vectorization
"""

import os
import time
import logging
import httpx
from typing import List, Optional, Dict, Any
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
logger = logging.getLogger(__name__)

# In-memory task status store for tracking background task progress
# Key: document_id, Value: {status, message, chunks_count, start_time, end_time, error}
_task_status_store: Dict[str, Dict[str, Any]] = {}


@router.get("/api/models")
async def get_models():
    """
    获取可用的嵌入模型列表

    Returns:
        可用模型列表，包括模型ID、名称、类型和维度
    """
    models = []

    # 获取嵌入服务
    service = get_embedding_service()

    # 检查 Ollama 模型
    if service._ollama.is_available:
        models.append({
            "id": "ollama",
            "name": f"Ollama - {service._ollama.model}",
            "type": "local",
            "dimension": service.dimension,
            "description": "本地 Ollama 嵌入模型，无需网络"
        })

    # 检查 DeepSeek 模型（如果有API Key）
    if service._deepseek.api_key:
        models.append({
            "id": "deepseek",
            "name": "DeepSeek Embedding",
            "type": "cloud",
            "dimension": service.dimension,
            "description": "DeepSeek 云端嵌入模型"
        })

    # 如果没有可用模型，返回默认选项
    if not models:
        models.append({
            "id": "random",
            "name": "Random Vectors",
            "type": "fallback",
            "dimension": service.dimension,
            "description": "随机向量（降级方案，不推荐）"
        })

    return {"models": models}


@router.post("/api/parse")
async def parse_document(request: ParseRequest, background_tasks: BackgroundTasks):
    """
    Parse a document and store chunks with vector embeddings.
    Returns immediately and processes in background.
    """
    logger.info(f"[Vectorization] Received parse request: {request.document_id}")

    # Validate request synchronously (fast)
    validate_document_id(request.document_id)
    file_type, resolved_path = validate_file_upload(
        file_path=request.file_path,
        file_type=request.file_type,
        check_size=True
    )
    logger.info(f"[Vectorization] Validation passed, resolved path: {resolved_path}, file_type: {file_type}")

    # Initialize task status
    _task_status_store[request.document_id] = {
        "status": "PROCESSING",
        "message": "Task started",
        "chunks_count": 0,
        "start_time": time.time(),
        "end_time": None,
        "error": None
    }

    # Move heavy processing to background task (use resolved path)
    background_tasks.add_task(
        _process_document_background,
        document_id=request.document_id,
        file_path=resolved_path,
        file_type=file_type,
        knowledge_base_id=request.knowledge_base_id,
        document_title=request.document_title,
        callback_url=request.callback_url,
        callback_secret=request.callback_secret,
    )

    return ParseResponse(
        success=True,
        document_id=request.document_id,
        blocks_count=0,
        chunks_count=0,
        message="Document parsing started in background"
    )


@router.get("/api/task-status/{document_id}")
async def get_task_status(document_id: str):
    """Check the status of a background processing task"""
    status = _task_status_store.get(document_id)
    if status is None:
        return {"status": "NOT_FOUND", "message": "No task found for this document"}
    return {
        "status": status["status"],
        "message": status["message"],
        "chunks_count": status["chunks_count"],
        "elapsed_seconds": round(time.time() - status["start_time"], 1) if status["start_time"] else 0,
        "error": status["error"]
    }


async def _process_document_background(
    document_id: str,
    file_path: str,
    file_type: str,
    knowledge_base_id: int,
    document_title: Optional[str] = None,
    callback_url: str = None,
    callback_secret: str = None,
):
    """Background task to process document parsing, chunking, and vectorization"""
    def _update_status(status: str, message: str, chunks_count: int = 0, error: str = None):
        """Update task status in the store"""
        _task_status_store[document_id] = {
            "status": status,
            "message": message,
            "chunks_count": chunks_count,
            "start_time": _task_status_store.get(document_id, {}).get("start_time", time.time()),
            "end_time": time.time() if status in ("COMPLETED", "FAILED") else None,
            "error": error
        }

    try:
        # Step 1: Parse document
        logger.info(f"[Vectorization] Parsing document: {document_id}, file: {file_path}")
        _update_status("PROCESSING", "Parsing document...")

        # Verify file exists before parsing
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        parser = BaseParser.get_parser(file_type)
        blocks = parser.parse(file_path)
        logger.info(f"[Vectorization] Parsed {len(blocks)} blocks")
        _update_status("PROCESSING", f"Parsed {len(blocks)} blocks, chunking...")

        # Step 2: Chunk blocks
        chunks = chunk_blocks(blocks, document_id)
        # Preserve a stable human-readable document title with every chunk so
        # chat citations do not depend on a separate Java HTTP request.
        for chunk in chunks:
            chunk.metadata["document_title"] = document_title or f"文档 #{document_id}"
        logger.info(f"[Vectorization] Created {len(chunks)} chunks")
        _update_status("PROCESSING", f"Created {len(chunks)} chunks, generating embeddings...")

        # Step 3: Create/update Milvus collection
        create_collection()

        # Step 4: Generate embeddings and store
        chunks_with_embeddings = []
        for i, chunk in enumerate(chunks):
            embedding = await _generate_embedding(chunk.content)
            chunk_dict = chunk.to_dict()
            chunk_dict['embedding'] = embedding
            chunks_with_embeddings.append(chunk_dict)
            if (i + 1) % 10 == 0:
                logger.info(f"[Vectorization] Processed {i + 1}/{len(chunks)} chunks")
                _update_status("PROCESSING", f"Generated {i + 1}/{len(chunks)} embeddings...")

        # Step 5: Insert into Milvus
        _update_status("PROCESSING", f"Inserting {len(chunks)} chunks into Milvus...")
        embeddings = [c['embedding'] for c in chunks_with_embeddings]
        insert_chunks(chunks, embeddings, document_id, knowledge_base_id)

        # Step 6: Notify Java backend
        _update_status("PROCESSING", "Notifying Java backend...")
        if callback_url:
            await _notify_callback_async(
                callback_url=callback_url,
                callback_secret=callback_secret,
                document_id=document_id,
                success=True,
                message=f"Successfully parsed document into {len(chunks)} chunks",
                chunks_count=len(chunks)
            )

        _update_status("COMPLETED", f"Successfully processed {len(chunks)} chunks", chunks_count=len(chunks))
        logger.info(f"[Vectorization] Completed: {len(chunks)} chunks stored")

    except Exception as e:
        import traceback
        error_detail = f"{str(e)}\n{traceback.format_exc()}"
        logger.error(f"[Vectorization] Background task failed: {error_detail}")
        _update_status("FAILED", f"Parsing failed: {str(e)}", error=str(e))

        # Notify failure
        if callback_url:
            try:
                await _notify_callback_async(
                    callback_url=callback_url,
                    callback_secret=callback_secret,
                    document_id=document_id,
                    success=False,
                    message=f"Parsing failed: {str(e)}",
                    chunks_count=0
                )
            except Exception as callback_error:
                logger.error(f"[Vectorization] Callback also failed: {callback_error}")


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
        # Search in Milvus
        try:
            results = search_similar(
                query_text=request.query,
                top_k=request.top_k,
                knowledge_base_id=request.knowledge_base_id
            )
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


async def _notify_callback_async(
    callback_url: str,
    document_id: str,
    success: bool,
    message: str,
    chunks_count: int,
    callback_secret: str = None
):
    """Notify Java backend about processing completion (async, non-blocking)"""
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

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(callback_url, json=payload, headers=headers)

        if response.status_code >= 400:
            logger.warning(f"[Callback] Warning: {callback_url} returned {response.status_code}")
        else:
            logger.info(f"[Callback] Notified {callback_url}: {response.status_code}")

    except httpx.TimeoutException:
        logger.warning(f"[Callback] Timeout: {callback_url}")
    except httpx.ConnectError:
        logger.warning(f"[Callback] Connection failed: {callback_url}")
    except Exception as e:
        logger.error(f"[Callback] Failed to notify: {str(e)}")
