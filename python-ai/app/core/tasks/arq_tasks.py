"""arq worker 任务定义（Batch 8 任务队列外置）。

worker 启动方式：
- 本地：``cd python-ai && python -m arq app.core.tasks.arq_tasks.WorkerSettings``
- compose：``python-ai-worker`` 服务（command 覆盖为上述命令）

任务函数 ``process_document`` 只做一件事：把可 JSON 序列化的 payload
转交给 vectorization 的既有后台处理函数（状态推进/解析/分块/向量化/回调
全部复用同一条生产链路）。
"""

from __future__ import annotations

import logging
from typing import Any

from app.utils.config import config

logger = logging.getLogger(__name__)

# arq 可选依赖：worker 镜像内必装（Dockerfile 显式钉版）；API 进程与单元测试
# 环境无需安装——只有 WorkerSettings 的 redis_settings 需要它。
try:
    from arq.connections import RedisSettings

    redis_settings = RedisSettings.from_dsn(config.ARQ_REDIS_DSN)
    _ARQ_AVAILABLE = True
except ImportError:  # pragma: no cover - 测试环境
    redis_settings = None
    _ARQ_AVAILABLE = False


async def process_document(ctx: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """arq 任务：文档解析 + 分块 + 向量化 + Java 回调（payload 由 dispatch 构造）。"""
    from app.api.vectorization import _process_document_background

    document_id = payload.get("document_id")
    logger.info("[arq] process_document start: %s (job=%s)", document_id, ctx.get("job_id"))
    await _process_document_background(**payload)
    logger.info("[arq] process_document done: %s", document_id)
    return {"document_id": document_id, "status": "processed"}


async def startup(ctx: dict[str, Any]) -> None:
    logger.info("[arq] worker starting; vector store mode=%s", config.VECTOR_STORE_MODE)


async def shutdown(ctx: dict[str, Any]) -> None:
    logger.info("[arq] worker shutting down")


class WorkerSettings:
    """arq WorkerSettings（arq CLI 约定）。"""

    functions = [process_document]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = redis_settings
    # 解析+向量化是长任务：允许同文档重试前有充足时间
    job_timeout = 1800
    max_jobs = 4  # worker 并发上限（与嵌入/向量库吞吐匹配）
