"""第九十九批判据：插件子进程的 fd 上限必须是「继承数 + 预算」，且不得钉死 hard。

缺陷形状（第九十七批在容器里量到、本批修）：`sandbox_runner.py:99` 把 RLIMIT_NOFILE 设成
`(config.max_open_files, config.max_open_files)`，而这发生在 fork **之后** —— 子进程已经继承了
父进程当时打开的全部 fd，它们同样计入那个数字。于是：
  - 裸父进程（子进程继承 9 个 fd）时，实际新增可用额度是 56，不是声明的 64；
  - 父进程 fd ≥ 64 时（CI 上 pytest 的形态）子进程**一个 fd 都开不了**，栽在自己的
    `import httpx` 上，报 `[Errno 24] Too many open files`；
  - hard 也被一起钉成 64，子进程再也抬不回去。

修法（用户选定方案 A）：只动 soft，且 soft = 设限时已打开的 fd 数 + `max_open_files`；
hard 保持继承值，让子进程需要时能抬回去。

平台诚实说明：Windows 没有 `resource` 模块，`_apply_subprocess_limits` 的三项限制全走
ImportError 分支（这正是"本机恒绿、CI 恒红"的成因）。所以本文件的 rlimit 断言只在 POSIX 上
真执行，判据主体由 CI 的 ubuntu `python` job 提供；本地 Windows 上它们是 skip，
**不能拿本地的绿当作这条链被验证过**。不依赖真 rlimit 的那几条（缺 `resource` 模块时必须
告警，而不是静默"设限成功"）在所有平台都跑。
"""

from __future__ import annotations

import os
import sys
from multiprocessing import Pipe, Process

import pytest

from app.core.plugin.sandbox_runner import (
    SubprocessConfig,
    _apply_subprocess_limits,
    _count_open_fds,
    execute_in_sandbox,
)

try:
    import resource
except ImportError:  # Windows
    resource = None  # type: ignore[assignment]

POSIX = resource is not None
requires_posix = pytest.mark.skipif(
    not POSIX, reason="RLIMIT_NOFILE 只在有 `resource` 模块的平台上存在"
)

BUDGET = 16
LOADED_PARENT_FDS = 200  # 明显大于默认预算 64，构造出 CI 那轮红的形态
_SCAN_CAP = 4096
_PROBE_CAP = 10000  # 额度探针的兜底上界，避免"限制没生效"时把 CI 拖成死循环
# 观测用的子进程是 fork 出来的 pytest，VSZ 远超 256MB；若沿用缺省 memory_mb，
# RLIMIT_AS 会在 conn.send 分配内存时把子进程打死（EOFError），fd 分支就测不到了。
_OBSERVE_CONFIG_KWARGS = {"memory_mb": 8192, "cpu_seconds": 120}


def _fd_count() -> int:
    """当前进程打开的 fd 数：优先 /proc，否则按 fstat 扫（macOS 走后者）。"""
    if os.path.isdir("/proc/self/fd"):
        return len(os.listdir("/proc/self/fd"))
    count = 0
    for fd in range(_SCAN_CAP):
        try:
            os.fstat(fd)
        except OSError:
            continue
        count += 1
    return count


def _hold_fds(target: int) -> list[int]:
    held: list[int] = []
    while _fd_count() < target:
        held.append(os.open(os.devnull, os.O_RDONLY))
    return held


def _child_observation(budget: int, hard_floor: int | None = None) -> dict:
    """fork 子进程，在里面调用生产的设限函数，回报设限前后的观测值。

    `hard_floor` 非空时，子进程在设限前先把 hard 降到该值（降 hard 无需特权），用来验证
    预算不会越过继承来的 hard。只在子进程里降，不影响 pytest 自己。
    """
    parent_conn, child_conn = Pipe()

    def run(conn) -> None:
        soft_before, hard_before = resource.getrlimit(resource.RLIMIT_NOFILE)
        if hard_floor is not None:
            resource.setrlimit(resource.RLIMIT_NOFILE, (min(soft_before, hard_floor), hard_floor))
            soft_before, hard_before = resource.getrlimit(resource.RLIMIT_NOFILE)
        inherited = _fd_count()
        _apply_subprocess_limits(SubprocessConfig(max_open_files=budget, **_OBSERVE_CONFIG_KWARGS))
        soft_after, hard_after = resource.getrlimit(resource.RLIMIT_NOFILE)
        # 边开边关永远不会撞上限（那是个死循环）：额度要靠**持有**来测，测完再关
        handles: list[int] = []
        while len(handles) < _PROBE_CAP:
            try:
                handles.append(os.open(os.devnull, os.O_RDONLY))
            except OSError:
                break
        opened = len(handles)
        for fd in handles:
            os.close(fd)
        # 能否抬回**继承来的** hard：这才是"hard 没被钉死"的可判含义
        # （第九十七批的探针当时拿 after_hard 自比，hard 被钉死时也报 True，是假指标）
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (hard_before, hard_before))
            raisable = True
        except (ValueError, OSError):
            raisable = False
        conn.send(
            {
                "soft_before": soft_before,
                "hard_before": hard_before,
                "inherited": inherited,
                "soft_after": soft_after,
                "hard_after": hard_after,
                "opened": opened,
                "raisable_to_inherited_hard": raisable,
            }
        )
        conn.close()

    proc = Process(target=run, args=(child_conn,), daemon=True)
    proc.start()
    child_conn.close()
    if not parent_conn.poll(30):
        proc.terminate()
        proc.join(5)
        pytest.fail("子进程未在 30s 内回报 fd 观测值")
    payload = parent_conn.recv()
    proc.join(10)
    parent_conn.close()
    return payload


@pytest.fixture
def loaded_parent():
    """把 pytest 自己的 fd 灌满 —— CI 那轮 5 条红就是从这个形态来的。"""
    if not POSIX:
        yield None
        return
    held = _hold_fds(LOADED_PARENT_FDS)
    try:
        yield _fd_count()
    finally:
        for fd in held:
            try:
                os.close(fd)
            except OSError:
                pass


NOOP_PLUGIN = "def noop(**kwargs):\n    return {'ok': True}\n"


@requires_posix
class TestHardLimitStaysInherited:
    def test_hard_is_not_pinned_to_the_budget(self):
        obs = _child_observation(BUDGET)
        assert obs["hard_after"] == obs["hard_before"], (
            f"hard 从 {obs['hard_before']} 被钉成 {obs['hard_after']}，子进程再也抬不回去"
        )

    def test_child_can_raise_soft_back_to_inherited_hard(self):
        obs = _child_observation(BUDGET)
        assert obs["raisable_to_inherited_hard"] is True


@requires_posix
class TestSoftIsInheritedPlusBudget:
    def test_soft_accounts_for_inherited_fds(self):
        obs = _child_observation(BUDGET)
        assert obs["soft_after"] == obs["inherited"] + BUDGET

    def test_budget_is_a_real_ceiling_not_an_absolute_count(self, loaded_parent):
        obs = _child_observation(BUDGET)
        assert loaded_parent and loaded_parent > BUDGET
        # 改前这里是 0：父进程持有 200 个 fd 时子进程一个 fd 都开不了
        assert obs["opened"] >= 1, (
            f"父进程持有 {loaded_parent} 个 fd 时新增可用 fd = "
            f"{obs['opened']}（soft={obs['soft_after']}）"
        )
        # 上界取 BUDGET+1：/proc 的自计那 1 个 fd（见 TestCountOpenFds 钉住的差值）
        assert BUDGET <= obs["opened"] <= BUDGET + 1, (
            f"预算 {BUDGET} 实际给了 {obs['opened']} 个新增 fd —— 限制被放宽成了绝对数或空转"
        )

    def test_absurd_inherited_soft_is_still_lowered(self):
        """继承来的 soft 很大时仍要压回「继承数 + 预算」，否则限制空转。"""
        parent_soft, parent_hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        huge = min(60000, parent_hard)
        resource.setrlimit(resource.RLIMIT_NOFILE, (huge, parent_hard))
        try:
            obs = _child_observation(BUDGET)
        finally:
            resource.setrlimit(resource.RLIMIT_NOFILE, (parent_soft, parent_hard))
        assert obs["soft_before"] == huge
        assert obs["soft_after"] == obs["inherited"] + BUDGET


@requires_posix
class TestEndToEndWithLoadedParent:
    def test_execute_in_sandbox_survives_fd_loaded_parent(self, tmp_path, loaded_parent):
        plugin_dir = tmp_path / "plugin_fd_loaded"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text(NOOP_PLUGIN, encoding="utf-8")
        result = execute_in_sandbox(
            plugin_dir=str(plugin_dir),
            plugin_name="plugin_fd_loaded",
            tool_name="noop",
            tool_input={},
            config=SubprocessConfig(runner_mode="subprocess", timeout_seconds=20),
        )
        assert result.success is True, (
            f"父进程持有 {loaded_parent} 个 fd 时调用失败："
            f"error_code={result.error_code} error={result.error}"
        )
        assert result.data == {"ok": True}


@requires_posix
class TestBudgetNeverCrossesInheritedHard:
    def test_target_is_clamped_by_hard(self):
        """hard 降到「比预算小」时，soft 只能停在 hard，不能越过它。"""
        parent_now = _fd_count()
        hard_floor = parent_now + 8  # 仍高于已开的 fd 数，否则子进程连 listdir 都做不了
        obs = _child_observation(BUDGET, hard_floor=hard_floor)
        assert obs["hard_after"] == hard_floor, "hard 被改动，子进程失去原有上限"
        assert obs["inherited"] + BUDGET > hard_floor, "这轮没构成夹紧，断言无意义"
        assert obs["soft_after"] == hard_floor


@requires_posix
class TestCountOpenFds:
    def test_proc_channel_matches_a_direct_listing(self):
        if not os.path.isdir("/proc/self/fd"):
            pytest.skip("本平台没有 /proc/self/fd，走 fstat 扫描分支")
        assert _count_open_fds() == len(os.listdir("/proc/self/fd"))

    def test_scan_fallback_is_exactly_one_below_proc(self, monkeypatch):
        """没有 /proc 的平台（macOS）走 fstat 扫描：在 Linux 上把 /proc 藏起来验扫描分支。

        没有这条，`_count_open_fds` 的 fallback 只有 macOS 会跑到，而这个仓库的 CI 是 ubuntu ——
        也就是那条分支永远不会被执行。
        差值钉成 1 而不是相等，是因为 `os.listdir("/proc/self/fd")` 用来读该目录的那个 fd
        自己也出现在目录里（第九十九批容器实测两次都是 listdir = fstat 扫描 + 1）；
        生产码走 /proc，所以 `max_open_files` 的语义是"预算 + 1 个富余"，不是恰好预算。
        """
        if not os.path.isdir("/proc/self/fd"):
            pytest.skip("本平台没有 /proc/self/fd，无参照可比")
        listed = len(os.listdir("/proc/self/fd"))
        real_listdir = os.listdir

        def fake_listdir(path, *args, **kwargs):
            if str(path) == "/proc/self/fd":
                raise OSError(2, "No such file or directory", str(path))
            return real_listdir(path, *args, **kwargs)

        monkeypatch.setattr(os, "listdir", fake_listdir)
        scanned = _count_open_fds()
        assert listed - scanned == 1, (f"listdir={listed} fstat 扫描={scanned}，" "差值不再是 1：/proc 自计那条口径变了")



class TestNoResourceModuleFailsLoudly:
    """没有 `resource` 模块时必须告警，不能静默"设限成功"。

    这两条不依赖真 rlimit，所以在 Windows 上也真执行：它们把"本机这三项限制其实没生效"
    变成可判定的事实，而不是只写在文档里的一句话。
    """

    def test_missing_resource_module_warns(self, monkeypatch, caplog):
        monkeypatch.setitem(sys.modules, "resource", None)
        with caplog.at_level("WARNING"):
            _apply_subprocess_limits(SubprocessConfig())
        assert "not enforced" in caplog.text.lower() or "unavailable" in caplog.text.lower(), (
            caplog.text
        )

    def test_no_exception_when_resource_is_absent(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "resource", None)
        _apply_subprocess_limits(SubprocessConfig())
