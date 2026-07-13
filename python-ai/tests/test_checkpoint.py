"""CheckpointManager / Checkpoint 单元测试。

覆盖:
- SQLite 持久化 save/load/load_at_step/list_for_run
- 同一 run 多步快照（load 取最新步）
- INSERT OR REPLACE 幂等（同 run 同步覆盖）
- delete / prune / count
- build_checkpoint_from_agent 字段映射
- get_checkpoint_manager 单例
"""

import threading

import pytest

import app.core.agent.checkpoint as cp_mod
from app.core.agent.checkpoint import (
    Checkpoint,
    CheckpointManager,
    build_checkpoint_from_agent,
)


@pytest.fixture
def manager(tmp_path) -> CheckpointManager:
    return CheckpointManager(database_path=str(tmp_path / "checkpoints.db"))


def _make_checkpoint(run_id: str = "run-1", step_index: int = 0, **overrides) -> Checkpoint:
    payload = dict(
        conversation_history=[{"role": "user", "content": "你好"}],
        retrieved_context="上下文片段",
        pending_tool_calls=[{"name": "calculator", "arguments": {"expr": "1+1"}}],
        agent_state={"intent": "rag"},
        sources=[{"title": "文档A", "chunk_id": "c1"}],
        style="detailed",
        max_tool_steps=5,
    )
    payload.update(overrides)
    return Checkpoint(run_id=run_id, step_index=step_index, **payload)


class TestSaveAndLoad:
    """保存与加载。"""

    def test_save_returns_positive_row_id(self, manager: CheckpointManager):
        row_id = manager.save(_make_checkpoint())
        assert row_id > 0

    def test_load_round_trips_all_fields(self, manager: CheckpointManager):
        cp = _make_checkpoint()
        manager.save(cp)

        restored = manager.load("run-1")
        assert restored is not None
        assert restored.run_id == "run-1"
        assert restored.step_index == 0
        assert restored.conversation_history == cp.conversation_history
        assert restored.retrieved_context == cp.retrieved_context
        assert restored.pending_tool_calls == cp.pending_tool_calls
        assert restored.agent_state == cp.agent_state
        assert restored.sources == cp.sources
        assert restored.style == "detailed"
        assert restored.max_tool_steps == 5
        assert restored.created_at == cp.created_at

    def test_load_missing_run_returns_none(self, manager: CheckpointManager):
        assert manager.load("no-such-run") is None

    def test_load_returns_latest_step(self, manager: CheckpointManager):
        manager.save(_make_checkpoint(step_index=1))
        manager.save(_make_checkpoint(step_index=3))
        manager.save(_make_checkpoint(step_index=2))

        restored = manager.load("run-1")
        assert restored is not None
        assert restored.step_index == 3

    def test_save_same_run_step_replaces(self, manager: CheckpointManager):
        """同 (run_id, step_index) 重复保存应覆盖而非报错。"""
        manager.save(_make_checkpoint(step_index=1, retrieved_context="旧上下文"))
        manager.save(_make_checkpoint(step_index=1, retrieved_context="新上下文"))

        assert manager.count() == 1
        restored = manager.load("run-1")
        assert restored is not None
        assert restored.retrieved_context == "新上下文"

    def test_multiple_runs_isolated(self, manager: CheckpointManager):
        manager.save(_make_checkpoint(run_id="run-a", step_index=1))
        manager.save(_make_checkpoint(run_id="run-b", step_index=1))

        assert manager.load("run-a").agent_state == {"intent": "rag"}
        assert manager.count() == 2


class TestLoadAtStep:
    """按步加载。"""

    def test_load_exact_step(self, manager: CheckpointManager):
        manager.save(_make_checkpoint(step_index=0))
        manager.save(_make_checkpoint(step_index=1, retrieved_context="第二步上下文"))

        restored = manager.load_at_step("run-1", 1)
        assert restored is not None
        assert restored.retrieved_context == "第二步上下文"

    def test_load_missing_step_returns_none(self, manager: CheckpointManager):
        manager.save(_make_checkpoint(step_index=0))
        assert manager.load_at_step("run-1", 9) is None


class TestListDeletePrune:
    """列举 / 删除 / 清理。"""

    def test_list_for_run_ordered_by_step(self, manager: CheckpointManager):
        for step in (2, 0, 1):
            manager.save(_make_checkpoint(step_index=step))

        checkpoints = manager.list_for_run("run-1")
        assert [c.step_index for c in checkpoints] == [0, 1, 2]

    def test_delete_removes_only_target_run(self, manager: CheckpointManager):
        manager.save(_make_checkpoint(run_id="run-a"))
        manager.save(_make_checkpoint(run_id="run-a", step_index=1))
        manager.save(_make_checkpoint(run_id="run-b"))

        deleted = manager.delete("run-a")
        assert deleted == 2
        assert manager.load("run-a") is None
        assert manager.count() == 1

    def test_delete_missing_run_returns_zero(self, manager: CheckpointManager):
        assert manager.delete("no-such-run") == 0

    def test_prune_removes_only_stale_checkpoints(self, manager: CheckpointManager):
        manager.save(_make_checkpoint(run_id="old", created_at="2020-01-01T00:00:00+00:00"))
        manager.save(_make_checkpoint(run_id="fresh"))

        pruned = manager.prune(max_age_days=7)
        assert pruned == 1
        assert manager.load("old") is None
        assert manager.load("fresh") is not None


class TestConcurrency:
    """线程安全。"""

    def test_concurrent_saves(self, manager: CheckpointManager):
        def worker(worker_id: int) -> None:
            for step in range(5):
                manager.save(_make_checkpoint(run_id=f"run-{worker_id}", step_index=step))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert manager.count() == 20


class TestBuildCheckpointFromAgent:
    """从 ReactAgent 状态构建快照。"""

    def test_maps_agent_attributes(self):
        class _FakeAgent:
            _checkpoint_history = [{"role": "user", "content": "q"}]
            _checkpoint_context = "ctx"
            _checkpoint_pending_tools = [{"name": "t"}]
            _last_sources = [{"title": "s"}]
            style = "concise"
            max_steps = 7

        cp = build_checkpoint_from_agent(_FakeAgent(), run_id="run-9", step_index=2, extra_state={"k": "v"})

        assert cp.run_id == "run-9"
        assert cp.step_index == 2
        assert cp.conversation_history == [{"role": "user", "content": "q"}]
        assert cp.retrieved_context == "ctx"
        assert cp.pending_tool_calls == [{"name": "t"}]
        assert cp.sources == [{"title": "s"}]
        assert cp.style == "concise"
        assert cp.max_tool_steps == 7
        assert cp.agent_state == {"k": "v"}

    def test_missing_attributes_fall_back_to_defaults(self):
        class _BareAgent:
            pass

        cp = build_checkpoint_from_agent(_BareAgent(), run_id="run-9", step_index=0)

        assert cp.conversation_history == []
        assert cp.retrieved_context == ""
        assert cp.pending_tool_calls == []
        assert cp.sources == []
        assert cp.style == "detailed"
        assert cp.max_tool_steps == 5
        assert cp.agent_state == {}


class TestSingleton:
    """get_checkpoint_manager 全局单例。"""

    def test_returns_same_instance(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cp_mod, "_checkpoint_manager", None)
        monkeypatch.setattr(cp_mod.config, "CHECKPOINT_DB_PATH", str(tmp_path / "cp.db"), raising=False)

        first = cp_mod.get_checkpoint_manager()
        second = cp_mod.get_checkpoint_manager()
        assert first is second
