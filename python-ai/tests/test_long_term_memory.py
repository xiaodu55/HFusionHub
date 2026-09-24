"""长期记忆接线（Batch 1）单元测试。

覆盖 app/core/rag/long_term_memory.py 的 LongTermMemoryService：
- feature flag 门控（关闭时零 HTTP 调用、零抽取）
- persist_entries 的 category→Java type 映射、超长截断、重要性钳制
- fetch_relevant 的 Java 返回归一化
- build_memory_context 的注入块组装（含"非指令"标注）
- schedule_turn_consolidation 的每 N 轮触发
- consolidate_conversation 的抽取→落库串联

Java 交互全部通过 monkeypatch httpx.AsyncClient 模拟，不发真实网络请求。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import app.core.rag.long_term_memory as ltm_module
from app.core.rag.long_term_memory import (
    FLAG_KEY,
    LongTermMemoryService,
    get_long_term_memory,
    reset_long_term_memory,
)

# ── httpx 假客户端 ─────────────────────────────────────────────────────────


class FakeResponse:
    """Java ``R`` 信封替身：调用方只写 data，信封 ``code`` 默认 200。

    刻意把信封构造收进替身本身：本仓出站点打到的 Java 内部面一律回
    ``{"code":…,"message":…,"data":…}``，若替身允许按"裸 data"构造，消费侧对
    信封码失明就永远测不出来（第七十七批同类教训）。
    """

    def __init__(
        self,
        data: Any = None,
        *,
        code: int = 200,
        message: str = "success",
        status_code: int = 200,
    ):
        self._payload = {"code": code, "message": message, "data": data}
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("error", request=None, response=None)

    def json(self) -> dict[str, Any]:
        return self._payload


class UnparseableResponse(FakeResponse):
    """HTTP 200 但 body 不是 JSON（反代/网关改写的形状）。"""

    def json(self) -> dict[str, Any]:
        raise ValueError("Expecting value: line 1 column 1 (char 0)")


class FakeAsyncClient:
    """记录请求并返回预置响应的 httpx.AsyncClient 替身。"""

    requests: list[dict[str, Any]] = []
    response: FakeResponse | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def get(self, url: str, **kwargs: Any) -> FakeResponse:
        FakeAsyncClient.requests.append({"method": "GET", "url": url, **kwargs})
        return FakeAsyncClient.response or FakeResponse([])

    async def post(self, url: str, **kwargs: Any) -> FakeResponse:
        FakeAsyncClient.requests.append({"method": "POST", "url": url, **kwargs})
        return FakeAsyncClient.response or FakeResponse({"saved": 0})


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_long_term_memory()
    FakeAsyncClient.requests = []
    FakeAsyncClient.response = None
    yield
    reset_long_term_memory()


def _set_flag(monkeypatch: pytest.MonkeyPatch, enabled: bool) -> None:
    monkeypatch.setattr(
        ltm_module.feature_flags,
        "is_enabled",
        lambda key, **kwargs: (key == FLAG_KEY and enabled),
    )


def _use_fake_http(monkeypatch: pytest.MonkeyPatch, response: FakeResponse | None = None):
    FakeAsyncClient.response = response
    monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)


# ── 开关门控 ───────────────────────────────────────────────────────────────


class TestFlagGating:
    def test_disabled_flag_build_memory_context_returns_empty_without_http(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        _set_flag(monkeypatch, enabled=False)
        _use_fake_http(monkeypatch)

        service = LongTermMemoryService()

        result = asyncio.run(service.build_memory_context(user_id=1, query="偏好什么"))
        assert result == ""
        assert FakeAsyncClient.requests == []  # 关闭时零网络调用

    def test_disabled_flag_consolidate_returns_none_without_llm(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        _set_flag(monkeypatch, enabled=False)

        called = {"extract": False}

        class FakeConsolidator:
            async def extract_memories(self, **kwargs: Any):
                called["extract"] = True
                raise AssertionError("flag 关闭时不应调用抽取")

        monkeypatch.setattr(
            "app.core.rag.memory_consolidator.get_memory_consolidator",
            lambda: FakeConsolidator(),
        )

        service = LongTermMemoryService()
        result = asyncio.run(
            service.consolidate_conversation(
                conversation_id=1, user_id=1, messages=[{"role": "user", "content": "hi"}]
            )
        )
        assert result is None
        assert called["extract"] is False

    def test_enabled_flag_without_user_id_skips(self, monkeypatch: pytest.MonkeyPatch):
        _set_flag(monkeypatch, enabled=True)
        _use_fake_http(monkeypatch)

        service = LongTermMemoryService()
        assert asyncio.run(service.build_memory_context(user_id=0, query="q")) == ""
        assert asyncio.run(service.build_memory_context(user_id=None, query="q")) == ""
        assert FakeAsyncClient.requests == []


# ── 持久化映射 ─────────────────────────────────────────────────────────────


class TestPersistEntries:
    def test_category_mapping_truncation_and_clamp(self, monkeypatch: pytest.MonkeyPatch):
        _set_flag(monkeypatch, enabled=True)
        _use_fake_http(monkeypatch, FakeResponse({"saved": 3}))

        service = LongTermMemoryService()
        entries = [
            {"fact": "用户偏好简洁回答", "category": "preference", "importance": 0.9},
            {"fact": "长" * 5000, "category": "fact", "importance": 2.0},
            {"fact": "目标是完成投标", "category": "goal", "importance": "bad"},  # 非法重要性→0.5
            {"fact": "   ", "category": "fact"},  # 空 fact → 丢弃
        ]
        saved = asyncio.run(
            service.persist_entries(user_id=7, entries=entries, conversation_id=11)
        )
        assert saved == 3

        post = next(r for r in FakeAsyncClient.requests if r["method"] == "POST")
        assert post["url"].endswith("/api/internal/memory/entries")
        body = post["json"]
        assert body["user_id"] == 7
        assert body["conversation_id"] == 11
        payload = body["entries"]
        assert payload[0]["type"] == "user_preference"
        assert payload[1]["type"] == "entity_fact"
        assert len(payload[1]["content"]) == 4000  # 截断到 Java 上限
        assert payload[1]["importance"] == 1.0  # 钳制到 [0, 1]
        assert payload[2]["type"] == "conversation_summary"  # goal → conversation_summary
        assert payload[2]["importance"] == 0.5
        assert len(payload) == 3  # 空 fact 被丢弃

    def test_over_batch_is_capped(self, monkeypatch: pytest.MonkeyPatch):
        _set_flag(monkeypatch, enabled=True)
        _use_fake_http(monkeypatch, FakeResponse({"saved": 0}))

        service = LongTermMemoryService()
        entries = [
            {"fact": f"事实 {i}", "category": "fact", "importance": 0.5} for i in range(30)
        ]
        asyncio.run(service.persist_entries(user_id=1, entries=entries))
        post = FakeAsyncClient.requests[-1]
        assert len(post["json"]["entries"]) == 20  # _MAX_BATCH_ENTRIES

    def test_missing_user_id_returns_zero_without_http(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        _set_flag(monkeypatch, enabled=True)
        _use_fake_http(monkeypatch)

        service = LongTermMemoryService()
        saved = asyncio.run(service.persist_entries(user_id=None, entries=[]))
        assert saved == 0
        assert FakeAsyncClient.requests == []


# ── 读取归一化 ─────────────────────────────────────────────────────────────


class TestFetchRelevant:
    def test_normalizes_java_payload(self, monkeypatch: pytest.MonkeyPatch):
        _set_flag(monkeypatch, enabled=True)
        _use_fake_http(
            monkeypatch,
            FakeResponse(
                [
                    {"type": "user_preference", "content": "喜欢简洁", "importance": 0.9},
                    {"content": "", "importance": 0.8},  # 空内容被过滤
                    {"type": "entity_fact", "content": "用户在深圳", "importance": None},
                ]
            ),
        )

        service = LongTermMemoryService()
        memories = asyncio.run(
            service.fetch_relevant(user_id=1, query="我怎么用", knowledge_base_id=5)
        )
        get_req = FakeAsyncClient.requests[0]
        assert get_req["url"].endswith("/api/internal/memory/relevant")
        assert get_req["params"]["user_id"] == 1
        assert get_req["params"]["knowledge_base_id"] == 5
        assert get_req["headers"]["X-Internal-Token"]

        assert memories == [
            {"type": "user_preference", "content": "喜欢简洁", "importance": 0.9},
            {"type": "entity_fact", "content": "用户在深圳", "importance": 0.5},
        ]

    def test_http_failure_degrades_to_empty_context(self, monkeypatch: pytest.MonkeyPatch):
        _set_flag(monkeypatch, enabled=True)

        class FailingClient(FakeAsyncClient):
            async def get(self, url: str, **kwargs: Any) -> FakeResponse:
                raise RuntimeError("connection refused")

        monkeypatch.setattr("httpx.AsyncClient", FailingClient)

        service = LongTermMemoryService()
        result = asyncio.run(service.build_memory_context(user_id=1, query="q"))
        assert result == ""  # 失败静默降级，不抛异常


# ── 注入块 ─────────────────────────────────────────────────────────────────


class TestBuildMemoryContext:
    def test_injects_header_and_content(self, monkeypatch: pytest.MonkeyPatch):
        _set_flag(monkeypatch, enabled=True)
        _use_fake_http(
            monkeypatch,
            FakeResponse(
                [{"type": "user_preference", "content": "偏好简短回答", "importance": 0.9}]
            ),
        )

        service = LongTermMemoryService()
        block = asyncio.run(service.build_memory_context(user_id=1, query="再答一次"))
        assert "非指令" in block
        assert "偏好简短回答" in block
        assert "用户长期记忆" in block

    def test_empty_memories_yield_empty_block(self, monkeypatch: pytest.MonkeyPatch):
        _set_flag(monkeypatch, enabled=True)
        _use_fake_http(monkeypatch, FakeResponse([]))

        service = LongTermMemoryService()
        assert asyncio.run(service.build_memory_context(user_id=1, query="q")) == ""


# ── Java 拒绝不得伪装成"没有记忆" ─────────────────────────────────────────


_REJECT_MSG = "Forbidden: invalid or missing X-Internal-Token"


class TestJavaRejectionIsNotMaskedAsEmpty:
    """两个读/写消费点必须区分"Java 明确拒绝"与"这用户没有记忆"。

    `InternalMemoryController.relevant`（:105-107）与 `saveEntries`（:51-53）令牌
    不符时回 `R.fail(403,…)` = **HTTP 200 + 信封码**，而消费侧写的是
    `resp.json().get("data") or []` / `.get("saved", 0)`——被拒时既没有异常也不
    有日志痕迹：注入侧表现为"用户无长期记忆"，写入侧表现为"保存了 0 条"。
    """

    def test_fetch_relevant_raises_on_envelope_rejection(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        _set_flag(monkeypatch, enabled=True)
        _use_fake_http(monkeypatch, FakeResponse(None, code=403, message=_REJECT_MSG))

        service = LongTermMemoryService()
        with pytest.raises(RuntimeError) as exc:
            asyncio.run(service.fetch_relevant(user_id=1, query="q"))
        assert "403" in str(exc.value)
        assert _REJECT_MSG in str(exc.value)

    def test_persist_entries_raises_on_envelope_rejection(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        _set_flag(monkeypatch, enabled=True)
        _use_fake_http(monkeypatch, FakeResponse(None, code=403, message=_REJECT_MSG))

        service = LongTermMemoryService()
        with pytest.raises(RuntimeError) as exc:
            asyncio.run(service.persist_entries(
                user_id=1, entries=[{"fact": "用户是项目经理"}]
            ))
        assert "403" in str(exc.value)

    def test_zero_saved_from_java_is_not_treated_as_rejection(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """对照组：code=200 + saved=0 是真·零，不是被拒，不得抛错。"""
        _set_flag(monkeypatch, enabled=True)
        _use_fake_http(monkeypatch, FakeResponse({"saved": 0}))

        service = LongTermMemoryService()
        saved = asyncio.run(service.persist_entries(
            user_id=1, entries=[{"fact": "团队用飞书"}]
        ))
        assert saved == 0

    def test_empty_data_list_is_not_treated_as_rejection(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """对照组：code=200 + data=[] 是真·无记忆，不得抛错。"""
        _set_flag(monkeypatch, enabled=True)
        _use_fake_http(monkeypatch, FakeResponse([]))

        service = LongTermMemoryService()
        assert asyncio.run(service.fetch_relevant(user_id=1, query="q")) == []

    def test_build_memory_context_warns_on_rejection(
        self, monkeypatch: pytest.MonkeyPatch, caplog
    ):
        """降级为空串是设计，但必须在 WARNING 里留下可归因的痕迹。"""
        import logging

        _set_flag(monkeypatch, enabled=True)
        _use_fake_http(monkeypatch, FakeResponse(None, code=403, message=_REJECT_MSG))

        service = LongTermMemoryService()
        with caplog.at_level(logging.DEBUG, logger="app.core.rag.long_term_memory"):
            assert asyncio.run(service.build_memory_context(user_id=1, query="q")) == ""
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert warnings, "Java 明确拒绝却只记 debug，运维无从区分配置错误与无记忆"
        assert "403" in " ".join(r.getMessage() for r in warnings)

    def test_unparseable_success_body_is_not_silently_empty(
        self, monkeypatch: pytest.MonkeyPatch, caplog
    ):
        import logging

        _set_flag(monkeypatch, enabled=True)
        _use_fake_http(monkeypatch, UnparseableResponse())

        service = LongTermMemoryService()
        with caplog.at_level(logging.DEBUG, logger="app.core.rag.long_term_memory"):
            assert asyncio.run(service.build_memory_context(user_id=1, query="q")) == ""
        assert [r for r in caplog.records if r.levelno >= logging.WARNING]

    def test_transport_failure_does_not_become_a_warning(
        self, monkeypatch: pytest.MonkeyPatch, caplog
    ):
        """反向守护：网络抖动仍是 debug 降噪，本批不把降级路径变成告警风暴。"""
        import logging

        _set_flag(monkeypatch, enabled=True)

        class FailingClient(FakeAsyncClient):
            async def get(self, url: str, **kwargs: Any) -> FakeResponse:
                raise RuntimeError("connection refused")

        monkeypatch.setattr("httpx.AsyncClient", FailingClient)

        service = LongTermMemoryService()
        with caplog.at_level(logging.DEBUG, logger="app.core.rag.long_term_memory"):
            assert asyncio.run(service.build_memory_context(user_id=1, query="q")) == ""
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

    def test_consolidate_propagates_rejection_instead_of_reporting_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """写入侧被拒不能上报"抽取到 N 条、保存 0 条"——那是把鉴权故障记成数据事实。"""
        _set_flag(monkeypatch, enabled=True)
        _use_fake_http(monkeypatch, FakeResponse(None, code=403, message=_REJECT_MSG))

        class _FakeResult:
            entries = [{"fact": "用户是项目经理", "category": "context", "importance": 0.8}]
            summary = "1 memories"

        class FakeConsolidator:
            async def extract_memories(self, **kwargs: Any):
                return _FakeResult()

        monkeypatch.setattr(
            "app.core.rag.memory_consolidator.get_memory_consolidator",
            lambda: FakeConsolidator(),
        )

        service = LongTermMemoryService()
        with pytest.raises(RuntimeError):
            asyncio.run(service.consolidate_conversation(
                conversation_id=42, user_id=7, messages=[{"role": "user", "content": "x"}]
            ))


# ── 每轮触发 ───────────────────────────────────────────────────────────────


class TestScheduleTurnConsolidation:
    def test_triggers_only_every_n_turns(self, monkeypatch: pytest.MonkeyPatch):
        _set_flag(monkeypatch, enabled=True)
        monkeypatch.setattr(ltm_module.config, "MEMORY_CONSOLIDATE_EVERY_TURNS", 2)

        calls: list[dict[str, Any]] = []

        async def fake_consolidate(**kwargs: Any) -> None:
            calls.append(kwargs)

        service = LongTermMemoryService()
        monkeypatch.setattr(service, "consolidate_conversation", fake_consolidate)

        async def drive():
            messages = [{"role": "user", "content": "hi"}]
            service.schedule_turn_consolidation(
                conversation_id=99, user_id=1, messages=messages
            )
            service.schedule_turn_consolidation(
                conversation_id=99, user_id=1, messages=messages
            )
            # 等待后台任务完成
            tasks = list(ltm_module._background_tasks)
            if tasks:
                await asyncio.gather(*tasks)

        asyncio.run(drive())
        assert len(calls) == 1
        assert calls[0]["conversation_id"] == 99
        assert calls[0]["user_id"] == 1

    def test_missing_ids_never_schedule(self, monkeypatch: pytest.MonkeyPatch):
        _set_flag(monkeypatch, enabled=True)
        monkeypatch.setattr(ltm_module.config, "MEMORY_CONSOLIDATE_EVERY_TURNS", 1)

        service = LongTermMemoryService()
        service.schedule_turn_consolidation(
            conversation_id=None, user_id=1, messages=[{"role": "user", "content": "x"}]
        )
        service.schedule_turn_consolidation(
            conversation_id=1, user_id=None, messages=[{"role": "user", "content": "x"}]
        )
        assert ltm_module._background_tasks == set()

    def test_counter_isolated_per_conversation(self):
        service = LongTermMemoryService()
        with service._counter_lock:
            service._turn_counters[1] = 1
            service._turn_counters[2] = 1
        with service._counter_lock:
            assert service._turn_counters[1] == 1
            assert service._turn_counters[2] == 1


# ── 抽取→落库串联 ──────────────────────────────────────────────────────────


class TestConsolidateConversation:
    def test_extracts_then_persists(self, monkeypatch: pytest.MonkeyPatch):
        _set_flag(monkeypatch, enabled=True)
        _use_fake_http(monkeypatch, FakeResponse({"saved": 2}))

        class _FakeResult:
            entries = [
                {"fact": "用户是项目经理", "category": "context", "importance": 0.8},
                {"fact": "团队用飞书", "category": "fact", "importance": 0.6},
            ]
            summary = "2 memories"

        class FakeConsolidator:
            async def extract_memories(self, conversation_id, messages, user_id=None, llm=None):
                assert conversation_id == 42
                assert user_id == 7
                return _FakeResult()

        monkeypatch.setattr(
            "app.core.rag.memory_consolidator.get_memory_consolidator",
            lambda: FakeConsolidator(),
        )

        service = LongTermMemoryService()
        result = asyncio.run(
            service.consolidate_conversation(
                conversation_id=42,
                user_id=7,
                messages=[{"role": "user", "content": "我是项目经理"}],
                knowledge_base_id=3,
            )
        )
        assert result == {"saved": 2, "summary": "2 memories"}
        post = FakeAsyncClient.requests[0]
        assert post["json"]["knowledge_base_id"] == 3
        assert post["json"]["entries"][0]["type"] == "entity_fact"  # context → entity_fact

    def test_no_entries_yields_none(self, monkeypatch: pytest.MonkeyPatch):
        _set_flag(monkeypatch, enabled=True)
        _use_fake_http(monkeypatch)

        class FakeConsolidator:
            async def extract_memories(self, **kwargs: Any):
                return None

        monkeypatch.setattr(
            "app.core.rag.memory_consolidator.get_memory_consolidator",
            lambda: FakeConsolidator(),
        )

        service = LongTermMemoryService()
        result = asyncio.run(
            service.consolidate_conversation(
                conversation_id=1, user_id=1, messages=[{"role": "user", "content": "x"}]
            )
        )
        assert result is None
        assert FakeAsyncClient.requests == []  # 无产出不落库


# ── 单例 ───────────────────────────────────────────────────────────────────


def test_singleton_returns_same_instance():
    assert get_long_term_memory() is get_long_term_memory()
    reset_long_term_memory()
    assert get_long_term_memory() is not None
