"""
Vectorization API Routes - FastAPI Version
Handles document parsing, chunking, and vectorization
"""

import asyncio
import os
import time
import logging
import json
import httpx
from collections import OrderedDict
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
    VectorChunk,
    VectorCountsRequest
)
from app.core.parser.base import BaseParser
from app.core.chunker.text_chunker import chunk_blocks
from app.core.chunker.quality import assess_chunk_quality
from app.core.parser.multimodal_evidence import MultimodalEvidenceExtractor
from app.core.embedding import get_embedding_service
from app.core.exceptions import (
    ParsingException,
    VectorizationException,
    EmbeddingException,
    MilvusException
)
from app.core.vectorstore.milvus_store import (
    create_collection,
    insert_chunks,
    search_similar,
    get_document_chunks,
    delete_document_chunks, delete_chunk_ids
)
from app.utils.config import config
from app.utils.validators import (
    validate_file_upload,
    validate_document_id
)
from app.core.tenant.context import set_tenant_id, clear_tenant_id, require_tenant_id

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory task status store for tracking background task progress
# Key: document_id, Value: {status, message, chunks_count, start_time, end_time, error}
# M13: 有界 LRU — 长驻进程下每个 document_id 一条、只增不删会无限增长；
# 上限 10000 条，写入时移到末尾，超出淘汰最旧条目（持久状态以 Java DB 为准）
_TASK_STATUS_STORE_MAX = 10000
_task_status_store: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()


def _task_status_put(document_id: str, entry: Dict[str, Any]) -> None:
    _task_status_store[document_id] = entry
    _task_status_store.move_to_end(document_id)
    while len(_task_status_store) > _TASK_STATUS_STORE_MAX:
        _task_status_store.popitem(last=False)


def _estimate_processing_seconds(file_path: str, file_type: str) -> int:
    """Return a conservative user-facing indexing estimate."""
    try:
        size_mb = os.path.getsize(file_path) / (1024 * 1024)
    except OSError:
        size_mb = 1
    base_seconds = {
        "pdf": 45,
        ".pdf": 45,
        "docx": 35,
        ".docx": 35,
        "txt": 15,
        ".txt": 15,
        "md": 15,
        ".md": 15,
        "csv": 20,
        ".csv": 20,
        "xlsx": 30,
        ".xlsx": 30,
    }.get((file_type or "").lower(), 30)
    estimate = base_seconds + int(size_mb * 25)
    return max(15, min(900, estimate))


def _dynamic_estimated_seconds(status: Dict[str, Any], now: Optional[float] = None) -> int:
    """Estimate total processing time from the observed progress.

    The initial estimate is intentionally conservative, but it cannot account
    for a slow embedding model or a busy local service.  Once a meaningful
    progress value is available, the elapsed time/progress ratio gives a
    better estimate and prevents the ETA from reaching zero while work is
    still in progress.
    """
    initial_estimate = status.get("estimated_seconds")
    if not initial_estimate:
        return 0

    start_time = status.get("start_time")
    if not start_time:
        return int(initial_estimate)

    current_time = time.time() if now is None else now
    elapsed = max(0.0, current_time - start_time)
    progress = status.get("progress")
    try:
        progress = float(progress)
    except (TypeError, ValueError):
        progress = 0.0

    # Early queue/parse states do not provide enough signal to infer a stable
    # total.  Keep the original estimate until progress is measurable.
    if progress <= 5 or elapsed < 1:
        return int(initial_estimate)

    observed_total = elapsed * 100.0 / min(progress, 99.0)
    # Do not let a short-lived fast sample cut the user's original estimate in
    # half, but allow slower real-world processing to extend it immediately.
    dynamic_total = max(initial_estimate * 0.75, observed_total)
    return int(round(min(900, max(15, dynamic_total))))


def _remaining_seconds(status: Dict[str, Any], now: Optional[float] = None) -> int:
    if status.get("status") in ("COMPLETED", "FAILED"):
        return 0
    start_time = status.get("start_time")
    if not start_time:
        return 0

    current_time = time.time() if now is None else now
    elapsed = max(0.0, current_time - start_time)
    estimated_total = _dynamic_estimated_seconds(status, now=current_time)
    if not estimated_total:
        return 0

    # A non-terminal task should never tell the user that no time remains.
    return max(1, int(round(estimated_total - elapsed)))


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

    # Hard tenant boundary: the active tenant is resolved from the verified
    # request context and threaded into the background task explicitly.
    tenant_id = require_tenant_id()

    # Validate request synchronously (fast)
    validate_document_id(request.document_id)
    file_type, resolved_path = validate_file_upload(
        file_path=request.file_path,
        file_type=request.file_type,
        check_size=True
    )
    logger.info(f"[Vectorization] Validation passed, resolved path: {resolved_path}, file_type: {file_type}")

    estimated_seconds = _estimate_processing_seconds(resolved_path, file_type)

    # Initialize task status
    _task_status_put(request.document_id, {
        "status": "PROCESSING",
        "message": f"Task started. Estimated processing time: about {estimated_seconds} seconds",
        "chunks_count": 0,
        "start_time": time.time(),
        "end_time": None,
        "error": None,
        "index_version": request.index_version,
        "chunk_quality": None,
        "multimodal": None,
        "stage": "queued",
        "progress": 3,
        "estimated_seconds": estimated_seconds,
        "processed_chunks": 0,
        "total_chunks": None,
    })

    # Batch 8：按 TASK_QUEUE_MODE 分发（inline 进程内 / arq 独立 worker，
    # 入队失败自动降级 inline）
    from app.core.tasks.queue import dispatch_document_processing

    await dispatch_document_processing(
        background_tasks,
        document_id=request.document_id,
        file_path=resolved_path,
        file_type=file_type,
        knowledge_base_id=request.knowledge_base_id,
        tenant_id=tenant_id,
        document_title=request.document_title,
        index_version=request.index_version,
        callback_url=request.callback_url,
        callback_secret=request.callback_secret,
        embedding_model=request.embedding_model,
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
    dynamic_estimated_seconds = _dynamic_estimated_seconds(status)
    return {
        "status": status["status"],
        "message": status["message"],
        "chunks_count": status["chunks_count"],
        "elapsed_seconds": round(time.time() - status["start_time"], 1) if status["start_time"] else 0,
        "estimated_seconds": dynamic_estimated_seconds,
        "initial_estimated_seconds": status.get("estimated_seconds"),
        "remaining_seconds": _remaining_seconds(status),
        "stage": status.get("stage"),
        "progress": status.get("progress"),
        "processed_chunks": status.get("processed_chunks"),
        "total_chunks": status.get("total_chunks"),
        "error": status["error"],
        "index_version": status.get("index_version"),
        "chunk_quality": status.get("chunk_quality"),
        "multimodal": status.get("multimodal"),
    }


async def _process_document_background(
    document_id: str,
    file_path: str,
    file_type: str,
    knowledge_base_id: int,
    tenant_id: int,
    document_title: Optional[str] = None,
    index_version: str = "",
    callback_url: str = None,
    callback_secret: str = None,
    embedding_model: Optional[str] = None,
):
    """Background task to process document parsing, chunking, and vectorization"""
    def _update_status(
        status: str,
        message: str,
        chunks_count: int = 0,
        error: str = None,
        chunk_quality: Optional[Dict[str, Any]] = None,
        multimodal: Optional[Dict[str, Any]] = None,
        stage: Optional[str] = None,
        progress: Optional[int] = None,
        processed_chunks: Optional[int] = None,
        total_chunks: Optional[int] = None,
    ):
        """Update task status in the store"""
        previous = _task_status_store.get(document_id, {})
        previous_progress = previous.get("progress") or 0
        next_progress = progress if progress is not None else previous_progress
        if status not in ("COMPLETED", "FAILED"):
            next_progress = max(previous_progress, min(next_progress, 95))
        _task_status_put(document_id, {
            "status": status,
            "message": message,
            "chunks_count": chunks_count,
            "start_time": previous.get("start_time", time.time()),
            "end_time": time.time() if status in ("COMPLETED", "FAILED") else None,
            "error": error,
            "index_version": index_version,
            "chunk_quality": chunk_quality if chunk_quality is not None else previous.get("chunk_quality"),
            "multimodal": multimodal if multimodal is not None else previous.get("multimodal"),
            "stage": stage if stage is not None else previous.get("stage"),
            "progress": 100 if status in ("COMPLETED", "FAILED") else next_progress,
            "estimated_seconds": previous.get("estimated_seconds"),
            "processed_chunks": processed_chunks if processed_chunks is not None else previous.get("processed_chunks", 0),
            "total_chunks": total_chunks if total_chunks is not None else previous.get("total_chunks"),
        })

    try:
        # Background tasks run outside the HTTP request context, so restore the
        # tenant boundary explicitly before touching tenant-scoped storage.
        set_tenant_id(tenant_id)
        # Step 1: Parse document
        logger.info(f"[Vectorization] Parsing document: {document_id}, file: {file_path}")
        _update_status("PROCESSING", "Parsing document...", stage="parsing", progress=10)

        # Verify file exists before parsing
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        parser = BaseParser.get_parser(file_type)
        # 解析是 CPU 密集操作：放入线程池，避免阻塞事件循环
        blocks = await asyncio.to_thread(parser.parse, file_path)
        extractor = MultimodalEvidenceExtractor(
            enabled=config.RAG_MULTIMODAL_ENABLED,
            ocr_enabled=config.RAG_MULTIMODAL_OCR_ENABLED,
            ocr_command=config.RAG_MULTIMODAL_OCR_COMMAND,
            ocr_language=config.RAG_MULTIMODAL_OCR_LANGUAGE,
            max_images_per_document=config.RAG_MULTIMODAL_MAX_IMAGES_PER_DOCUMENT,
            max_image_bytes=config.RAG_MULTIMODAL_MAX_IMAGE_BYTES,
            max_ocr_characters=config.RAG_MULTIMODAL_MAX_OCR_CHARACTERS,
            ocr_timeout_seconds=config.RAG_MULTIMODAL_OCR_TIMEOUT_SECONDS,
            vlm_enabled=config.RAG_MULTIMODAL_VLM_ENABLED,
            vlm_model=config.RAG_MULTIMODAL_VLM_MODEL,
            vlm_base_url=config.RAG_MULTIMODAL_VLM_BASE_URL or config.OLLAMA_BASE_URL,
            vlm_timeout_seconds=config.RAG_MULTIMODAL_VLM_TIMEOUT_SECONDS,
        )
        blocks, multimodal_report = await asyncio.to_thread(extractor.enrich, file_path, file_type, blocks)
        multimodal = multimodal_report.to_dict()
        if not blocks:
            raise ParsingException("未提取到可索引文本，请确认文档包含可复制文字；扫描件或图片型 PDF 需要先 OCR。")
        logger.info(f"[Vectorization] Parsed {len(blocks)} blocks")
        _update_status(
            "PROCESSING",
            f"Parsed {len(blocks)} blocks, chunking...",
            multimodal=multimodal,
            stage="chunking",
            progress=25,
        )

        # Step 2: Chunk blocks（CPU 密集，放入线程池）
        chunks = await asyncio.to_thread(chunk_blocks, blocks, document_id)
        if not chunks:
            raise ParsingException("文档解析后没有生成可索引分块，请检查文档文本内容是否为空或格式异常。")
        quality = (await asyncio.to_thread(assess_chunk_quality, blocks, chunks)).to_dict()
        # Preserve a stable human-readable document title with every chunk so
        # chat citations do not depend on a separate Java HTTP request.
        for chunk in chunks:
            chunk.metadata["document_title"] = document_title or f"文档 #{document_id}"
        logger.info(f"[Vectorization] Created {len(chunks)} chunks")
        quality_suffix = f"；质量告警：{', '.join(quality['warnings'])}" if quality["warnings"] else ""
        _update_status(
            "PROCESSING",
            f"Created {len(chunks)} chunks, generating embeddings...{quality_suffix}",
            chunk_quality=quality,
            multimodal=multimodal,
            stage="embedding",
            progress=35,
            total_chunks=len(chunks),
        )

        # Step 3: Create/update Milvus collection.  Do not continue to a
        # destructive replacement when the vector store is unavailable; the
        # old index must remain intact and the callback must contain a useful
        # failure reason.
        if await asyncio.to_thread(create_collection) is None:
            raise MilvusException("Vector store is unavailable; cannot initialise the document index")

        # Step 4: Generate embeddings and store.
        # 默认路径按批调用 EmbeddingService.generate_batch（一次网络往返生成
        # 多条向量，Ollama /api/embed 原生支持），吞吐远高于逐条串行；
        # 仅当调用方显式指定了单模型时回退逐条生成以保持行为兼容。
        chunks_with_embeddings = []
        batch_size = 16
        service = get_embedding_service()
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start:start + batch_size]
            if embedding_model:
                embeddings = [
                    await service.generate(c.content, model=embedding_model)
                    for c in batch
                ]
            else:
                embeddings = await service.generate_batch([c.content for c in batch])
            if len(embeddings) != len(batch):
                raise MilvusException(
                    f"Embedding provider returned {len(embeddings)} vectors for "
                    f"{len(batch)} chunks"
                )
            for i, chunk in enumerate(batch):
                chunk_dict = chunk.to_dict()
                chunk_dict['embedding'] = embeddings[i]
                chunks_with_embeddings.append(chunk_dict)
            done = start + len(batch)
            if done % 5 == 0 or done == len(chunks):
                logger.info(f"[Vectorization] Processed {done}/{len(chunks)} chunks")
                embedding_progress = 40 + int((done / max(len(chunks), 1)) * 45)
                _update_status(
                    "PROCESSING",
                    f"Generated {done}/{len(chunks)} embeddings...",
                    stage="embedding",
                    progress=embedding_progress,
                    processed_chunks=done,
                    total_chunks=len(chunks),
                )

        # Step 5: Insert into Milvus
        _update_status(
            "PROCESSING",
            f"Inserting {len(chunks)} chunks into Milvus...",
            stage="storing",
            progress=90,
            processed_chunks=len(chunks),
            total_chunks=len(chunks),
        )
        embeddings = [c['embedding'] for c in chunks_with_embeddings]
        # Keep old data reachable while parsing and embedding.  Replacement is
        # performed immediately before insertion, rather than at task start.
        # Stage the new version first.  A failed embedding/insert must not
        # erase the last known-good index.
        old_result = await asyncio.to_thread(get_document_chunks, str(document_id), 1, 100000)
        old_records = old_result.get("data", {}).get("records", []) if old_result.get("code") == 200 else []
        old_ids = {str(record.get("chunk_id")) for record in old_records if record.get("chunk_id")}
        if not await asyncio.to_thread(insert_chunks, chunks, embeddings, document_id, knowledge_base_id):
            raise MilvusException(f"Failed to insert chunks for document {document_id}")
        new_ids = {str(chunk.chunk_id) for chunk in chunks if chunk.chunk_id}
        if not await asyncio.to_thread(delete_chunk_ids, sorted(old_ids - new_ids)):
            raise MilvusException(f"Failed to remove stale chunks for document {document_id}")

        # Step 6: Notify Java backend
        _update_status("PROCESSING", "Notifying Java backend...", stage="callback", progress=95)
        if callback_url:
            callback_ok = await _notify_callback_async(
                callback_url=callback_url,
                callback_secret=callback_secret,
                document_id=document_id,
                success=True,
                message=f"Successfully parsed document into {len(chunks)} chunks",
                chunks_count=len(chunks),
                index_version=index_version,
                chunks=_callback_chunk_metadata(chunks),
            )
            if not callback_ok:
                # S6 收敛：新索引已落库且旧版本已删（上方替换逻辑），索引是最新且
                # 无重复的 —— 此时把任务标 FAILED 会造成"索引有效但任务失败"的对账
                # 漂移并触发 Java 恢复调度重复重析。改为按完成收尾 + ERROR 告警；
                # 回调真丢失时 document 会停在 PROCESSING，由 Java stale 恢复调度
                # 幂等重析收敛。
                logger.error(
                    "[Vectorization] Java callback unacknowledged after retries: "
                    "document=%s version=%s — index stored, task marked COMPLETED; "
                    "document status will be reconciled by Java recovery scheduler",
                    document_id,
                    index_version,
                )

        _update_status(
            "COMPLETED",
            f"Successfully processed {len(chunks)} chunks",
            chunks_count=len(chunks),
            chunk_quality=quality,
            multimodal=multimodal,
            stage="completed",
            progress=100,
            processed_chunks=len(chunks),
            total_chunks=len(chunks),
        )
        logger.info(f"[Vectorization] Completed: {len(chunks)} chunks stored")

    except EmbeddingException as e:
        import traceback
        error_detail = f"{str(e)}\n{traceback.format_exc()}"
        logger.error(f"[Vectorization] Embedding failed: {error_detail}")
        _update_status("FAILED", f"向量嵌入失败: {str(e)}", error=str(e), stage="failed", progress=100)

        # Notify failure
        if callback_url:
            try:
                await _notify_callback_async(
                    callback_url=callback_url,
                    callback_secret=callback_secret,
                    document_id=document_id,
                    success=False,
                    message=f"向量嵌入失败: {str(e)}",
                    chunks_count=0,
                    index_version=index_version,
                )
            except Exception as callback_error:
                logger.error(f"[Vectorization] Callback also failed: {callback_error}")

    except Exception as e:
        import traceback
        error_detail = f"{str(e)}\n{traceback.format_exc()}"
        logger.error(f"[Vectorization] Background task failed: {error_detail}")
        _update_status("FAILED", f"Processing failed: {str(e)}", error=str(e), stage="failed", progress=100)

        # Notify failure
        if callback_url:
            try:
                await _notify_callback_async(
                    callback_url=callback_url,
                    callback_secret=callback_secret,
                    document_id=document_id,
                    success=False,
                    message=f"Processing failed: {str(e)}",
                    chunks_count=0,
                    index_version=index_version,
                )
            except Exception as callback_error:
                logger.error(f"[Vectorization] Callback also failed: {callback_error}")

    finally:
        clear_tenant_id()


@router.get("/api/chunks/{document_id}", response_model=ChunkResponse)
async def get_chunks(document_id: str, page: int = 1, size: int = 20, block_type: str = None):
    """Get all chunks for a document"""
    try:
        validate_document_id(document_id)

        result = await asyncio.to_thread(get_document_chunks, document_id, page, size, block_type)

        if result.get("code") != 200:
            raise MilvusException(result.get("message", "获取分块失败"))

        data = result.get("data", {})
        records = data.get("records", [])
        total = data.get("total", 0)

        chunks = []
        # index = 文档内全局顺序：分页 offset + 页内序号（此前硬编码 0，分页语义丢失）
        base_index = (max(page, 1) - 1) * size
        for offset, record in enumerate(records):
            # Parse outline_path from JSON string to list
            outline_path = record.get("outline_path", "[]")
            if isinstance(outline_path, str):
                import json
                try:
                    outline_path = json.loads(outline_path)
                except Exception:
                    outline_path = []

            chunks.append(VectorChunk(
                chunk_id=record.get("chunk_id", ""),
                index=base_index + offset,
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

        result = await asyncio.to_thread(get_document_chunks, document_id)
        records = result.get("data", {}).get("records", []) if isinstance(result, dict) else []

        for chunk in records:
            if chunk.get('chunk_id') == chunk_id:
                return VectorChunkResponse(**chunk)

        from app.core.exceptions import ValidationException
        raise ValidationException(f"分块不存在: {chunk_id}", code=404)

    except ValidationException:
        raise
    except Exception as e:
        raise MilvusException(f"获取分块详情失败: {e}")


@router.post("/api/search", response_model=SearchResponse)
async def search_chunks(request: SearchRequest):
    """Search for similar chunks"""
    try:
        # Search in Milvus（pymilvus 为同步客户端，放入线程池避免阻塞事件循环）
        try:
            results = await asyncio.to_thread(
                search_similar,
                query_text=request.query,
                top_k=request.top_k,
                knowledge_base_id=request.knowledge_base_id,
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


@router.post("/api/stats/vector-counts")
async def vector_counts(request: VectorCountsRequest):
    """Return Milvus entity counts per knowledge base for reconciliation.

    Called by the Java backend's vector-store health check.  Each count is
    scoped to the active tenant (fail-closed), matching the Java side's
    per-tenant comparison.  A per-KB ``-1`` marks an individual count failure
    (e.g. transient Milvus outage) so the Java side does not raise a false
    drift alarm from an unreadable store.
    """
    from app.core.vectorstore.milvus_store import count_chunks
    counts: Dict[str, int] = {}
    for kb_id in request.knowledge_base_ids:
        try:
            counts[str(kb_id)] = await asyncio.to_thread(count_chunks, knowledge_base_id=kb_id)
        except Exception as exc:
            logger.warning("[Vectorization] Vector count failed for kb=%s: %s", kb_id, exc)
            counts[str(kb_id)] = -1
    return {"counts": counts}


@router.delete("/api/documents/{document_id}/chunks")
async def remove_document_chunks(document_id: str):
    """Remove a document's vector entries and local metadata before deletion."""
    validate_document_id(document_id)
    if not await asyncio.to_thread(delete_document_chunks, document_id):
        raise MilvusException(f"删除文档 {document_id} 的分块失败")
    _task_status_store.pop(document_id, None)
    return {"success": True, "document_id": document_id}


async def _generate_embedding(text: str, model: Optional[str] = None) -> List[float]:
    """
    Generate embedding using multi-strategy service
    Strategy: Ollama BGE-M3 -> DeepSeek API

    Args:
        text: Input text
        model: Embedding model name (e.g. "ollama")
    """
    service = get_embedding_service()
    return await service.generate(text, model=model)


async def _notify_callback_async(
    callback_url: str,
    document_id: str,
    success: bool,
    message: str,
    chunks_count: int,
    index_version: str,
    chunks: Optional[List[Dict[str, Any]]] = None,
    callback_secret: str = None
) -> bool:
    """Notify Java backend about processing completion (async, non-blocking)"""
    import hmac
    import hashlib
    import base64

    try:
        # Convert to Java backend expected format
        status = "COMPLETED" if success else "FAILED"
        payload = {
            "document_id": document_id,
            "status": status,
            "chunkCount": chunks_count,
            "message": message,
            "indexVersion": index_version,
            "chunks": chunks or [],
        }

        # Serialize payload to JSON for HMAC signing
        payload_json = json.dumps(payload, ensure_ascii=False)

        headers = {"Content-Type": "application/json"}
        # 透传请求级 trace_id：Java TraceFilter 会把入站 X-Trace-ID 记入
        # MDC，回调若不带此头，Java 侧的日志/审计无法与原请求关联。
        try:
            from app.utils.trace import get_trace_id
            trace_id = get_trace_id()
            if trace_id:
                headers["X-Trace-ID"] = trace_id
        except Exception:
            pass
        if callback_secret:
            headers["X-Callback-Secret"] = callback_secret
            # Compute HMAC-SHA256 signature over the raw JSON body
            signature = base64.b64encode(
                hmac.new(
                    callback_secret.encode("utf-8"),
                    payload_json.encode("utf-8"),
                    hashlib.sha256,
                ).digest()
            ).decode("ascii")
            headers["X-Callback-Signature"] = signature

        # 复用共享 httpx 池（此前每次调用新建 AsyncClient 泄漏连接）+ 指数退避重试
        from app.core.llm.http_client import get_shared_client

        client = get_shared_client("callback", timeout=10.0)
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                response = await client.post(callback_url, content=payload_json, headers=headers)
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                logger.warning(f"[Callback] attempt {attempt}/{max_attempts} network error: {callback_url}: {type(e).__name__}")
            except Exception as e:
                logger.error(f"[Callback] attempt {attempt}/{max_attempts} failed: {type(e).__name__}: {str(e)[:200]}")
            else:
                if response.status_code < 400:
                    logger.info(f"[Callback] Notified {callback_url}: {response.status_code}")
                    return True
                logger.warning(
                    f"[Callback] attempt {attempt}/{max_attempts}: {callback_url} returned {response.status_code}"
                )
                # 4xx 属确定性失败（鉴权/参数错误），重试无意义
                if 400 <= response.status_code < 500:
                    return False
            if attempt < max_attempts:
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
        return False

    except Exception as e:
        logger.error(f"[Callback] Failed to notify: {type(e).__name__}: {str(e)[:200]}")
        return False


def _callback_chunk_metadata(chunks: List[VectorChunk]) -> List[Dict[str, Any]]:
    """Build a bounded callback payload; full text stays in the vector store."""
    from app.utils.config import config
    return [
        {
            "chunkId": chunk.chunk_id,
            "index": chunk.index,
            "blockType": chunk.block_type,
            "outlinePath": chunk.outline_path,
            "contentExcerpt": chunk.content[:1000],
            "charCount": len(chunk.content),
            "metadata": _json_safe_metadata(chunk.metadata),
            "embeddingModel": config.EMBEDDING_MODEL or config.OLLAMA_EMBEDDING_MODEL,
            "embeddingDimension": config.EMBEDDING_DIMENSION,
            "embeddingVersion": "v1",
        }
        for chunk in chunks
    ]


def _json_safe_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Avoid losing the whole callback because one parser value is not JSON serializable."""
    return json.loads(json.dumps(metadata or {}, ensure_ascii=False, default=str))
