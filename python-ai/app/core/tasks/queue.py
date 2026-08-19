"""任务队列抽象（Batch 8）—— 解析/向量化任务从进程内 BackgroundTasks 外置到 arq worker。

两种模式（``TASK_QUEUE_MODE``）：

- ``inline``（默认）：沿用 FastAPI BackgroundTasks，进程内执行（单实例部署零依赖）；
- ``arq``：任务入 Redis 队列（``ARQ_REDIS_DSN``），由独立 worker 进程
  （``python-ai/arq_worker.py``，docker compose 的 ``python-ai-worker`` 服务）
  消费——解析/向量化吞吐与 API 进程解耦，为水平扩展铺路。

arq 是延迟导入：inline 模式（以及所有单元测试）无需安装 arq。

入队失败自动降级 inline（告警日志），保证队列基础设施故障不阻断文档入库。
"""

from __future__ import annotations

import logging
from typing import Any

from app.utils.config import config

logger = logging.getLogger(__name__)

ARQ_JOB_NAME = "process_document"


async def dispatch_document_processing(
    background_tasks: Any,
    *,
    document_id: str,
    file_path: str,
    file_type: str,
    knowledge_base_id: Any = None,
    tenant_id: Any = None,
    document_title: Any = None,
    visibility: Any = None,
    index_version: Any = None,
    callback_url: Any = None,
    callback_secret: Any = None,
    embedding_model: Any = None,
) -> str:
    """按 TASK_QUEUE_MODE 分发文档处理任务，返回实际使用的模式。

    - ``inline``：任务挂到 FastAPI BackgroundTasks（响应后进程内执行）；
    - ``arq``：入队 arq（payload 为可 JSON 序列化 dict），失败降级 inline。
    """
    payload: dict[str, Any] = {
        "document_id": document_id,
        "file_path": file_path,
        "file_type": file_type,
        "knowledge_base_id": knowledge_base_id,
        "tenant_id": tenant_id,
        "document_title": document_title,
        "visibility": visibility,
        "index_version": index_version,
        "callback_url": callback_url,
        "callback_secret": callback_secret,
        "embedding_model": embedding_model,
    }

    if config.TASK_QUEUE_MODE == "arq":
        try:
            await _enqueue_arq(payload)
            logger.info("[task-queue] Document %s dispatched via arq", document_id)
            return "arq"
        except Exception as exc:
            logger.warning(
                "[task-queue] arq enqueue failed (%s); falling back to inline for document %s",
                exc, document_id,
            )

    background_tasks.add_task(_run_inline, payload)
    return "inline"


async def _enqueue_arq(payload: dict[str, Any]) -> None:
    from arq import create_pool
    from arq.connections import RedisSettings

    pool = await create_pool(RedisSettings.from_dsn(config.ARQ_REDIS_DSN))
    try:
        await pool.enqueue_job(ARQ_JOB_NAME, payload)
    finally:
        await pool.aclose()


async def _run_inline(payload: dict[str, Any]) -> None:
    """inline 模式执行体：直接复用 vectorization 的后台处理函数（async）。"""
    from app.api.vectorization import _process_document_background

    await _process_document_background(**payload)
