"""Batch 8 单元测试：任务队列分发（inline / arq + 失败降级）。

arq 为延迟导入——本测试通过 sys.modules 注入假 arq 模块，
无需真实安装 arq 包即可覆盖入队/降级路径。
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

import app.core.tasks.queue as queue_mod
from app.core.tasks.queue import ARQ_JOB_NAME, dispatch_document_processing


@pytest.fixture(autouse=True)
def _reset_mode(monkeypatch):
    from app.utils.config import config

    monkeypatch.setattr(config, "TASK_QUEUE_MODE", "inline")
    yield
    monkeypatch.setattr(config, "TASK_QUEUE_MODE", "inline")


def _payload(**overrides) -> dict[str, Any]:
    base = {"document_id": "doc-1", "file_path": "/tmp/x.pdf", "file_type": "pdf"}
    base.update(overrides)
    return base


class _FakeBackgroundTasks:
    def __init__(self):
        self.added: dict[str, Any] = {}

    def add_task(self, fn, *args, **kwargs):
        self.added.update({"fn": fn, "args": args, "kwargs": kwargs})


class TestInlineMode:
    @pytest.mark.asyncio
    async def test_inline_uses_background_tasks(self):
        background = _FakeBackgroundTasks()

        mode = await dispatch_document_processing(
            background, **_payload(tenant_id=3))
        assert mode == "inline"
        # dispatch 构造完整 payload（未传字段为 None）
        (passed_payload,) = background.added["args"]
        assert passed_payload["tenant_id"] == 3
        assert passed_payload["document_id"] == "doc-1"
        expected_fields = {
            "document_id", "file_path", "file_type", "knowledge_base_id",
            "tenant_id", "document_title", "visibility", "index_version",
            "callback_url", "callback_secret", "embedding_model",
        }
        assert set(passed_payload) == expected_fields
        # 执行体是 async 函数（Starlette 会 await）
        import inspect

        assert inspect.iscoroutinefunction(background.added["fn"])

    @pytest.mark.asyncio
    async def test_inline_executes_pipeline(self, monkeypatch):
        """_run_inline 正确转交 vectorization 后台处理函数（kwargs 全量传递）。"""
        received: dict[str, Any] = {}

        async def fake_process(**kwargs):
            received.update(kwargs)
            return None

        monkeypatch.setattr(
            "app.api.vectorization._process_document_background", fake_process)
        await queue_mod._run_inline(_payload(embedding_model="bge-m3"))
        assert received == _payload(embedding_model="bge-m3")


class _FakePool:
    def __init__(self, sink: dict[str, Any]):
        self._sink = sink

    async def enqueue_job(self, name, payload):
        self._sink["name"] = name
        self._sink["payload"] = payload

    async def aclose(self):
        self._sink["closed"] = True


class TestArqMode:
    @pytest.fixture
    def fake_arq(self, monkeypatch):
        """向 sys.modules 注入假 arq / arq.connections 模块。"""
        state: dict[str, Any] = {}

        class _FakeRedisSettings:
            def __init__(self, dsn: str):
                self.dsn = dsn

            @classmethod
            def from_dsn(cls, dsn: str):
                return cls(dsn)

        async def fake_create_pool(settings):
            state["dsn"] = settings.dsn
            pool = _FakePool(state)
            state["pool_created"] = True
            return pool

        fake_arq_mod = types.SimpleNamespace(create_pool=fake_create_pool)
        fake_connections = types.SimpleNamespace(RedisSettings=_FakeRedisSettings)
        monkeypatch.setitem(sys.modules, "arq", fake_arq_mod)
        monkeypatch.setitem(sys.modules, "arq.connections", fake_connections)
        yield state

    @pytest.mark.asyncio
    async def test_arq_enqueues_job_payload(self, monkeypatch, fake_arq):
        from app.utils.config import config

        monkeypatch.setattr(config, "TASK_QUEUE_MODE", "arq")
        monkeypatch.setattr(config, "ARQ_REDIS_DSN", "redis://:pw@redis7:6379/2")

        background = _FakeBackgroundTasks()
        mode = await dispatch_document_processing(background, **_payload())

        assert mode == "arq"
        assert fake_arq["name"] == ARQ_JOB_NAME
        assert fake_arq["payload"]["document_id"] == "doc-1"
        assert fake_arq["closed"] is True
        assert fake_arq["dsn"] == "redis://:pw@redis7:6379/2"
        assert "fn" not in background.added  # 未回退 inline

    @pytest.mark.asyncio
    async def test_arq_failure_falls_back_to_inline(self, monkeypatch, fake_arq):
        from app.utils.config import config

        monkeypatch.setattr(config, "TASK_QUEUE_MODE", "arq")

        async def broken_create_pool(settings):
            raise RuntimeError("redis down")

        fake_arq_mod = types.SimpleNamespace(create_pool=broken_create_pool)
        monkeypatch.setitem(sys.modules, "arq", fake_arq_mod)

        background = _FakeBackgroundTasks()
        mode = await dispatch_document_processing(background, **_payload())

        assert mode == "inline"  # 降级
        assert background.added["fn"] is queue_mod._run_inline


class TestArqTaskFunction:
    @pytest.mark.asyncio
    async def test_process_document_delegates_with_payload(self, monkeypatch):
        received: dict[str, Any] = {}

        async def fake_process(**kwargs):
            received.update(kwargs)

        monkeypatch.setattr(
            "app.api.vectorization._process_document_background", fake_process)
        from app.core.tasks.arq_tasks import process_document

        result = await process_document({"job_id": "job-9"}, _payload(document_id="doc-9"))
        assert received == _payload(document_id="doc-9")
        assert result == {"document_id": "doc-9", "status": "processed"}
