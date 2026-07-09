"""arq worker CLI 入口（Batch 8 任务队列外置）。

用法（在 python-ai 目录）：
    python -m arq arq_worker.WorkerSettings

docker compose 场景由 ``python-ai-worker`` 服务以相同命令运行，共享
python-ai 镜像与配置（TASK_QUEUE_MODE / ARQ_REDIS_DSN）。
"""

from app.core.tasks.arq_tasks import WorkerSettings  # noqa: F401
