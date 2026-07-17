"""Tests for sandbox_runner hardening (第十五轮 P0-1 / P0-6).

Verifies:
  1. Container mode works when called from a plain sync thread (asyncio.run
     in a loop-free worker — the normal asyncio.to_thread dispatch path)
  2. Container mode SURVIVES being called from a thread with a running event
     loop (the historical bug: bare run_until_complete raised RuntimeError
     that was swallowed by fail-closed handling → silent
     container_runner_unavailable)
  3. Network guard default-DENY: empty allowed_domains blocks everything
  4. Filesystem default-deny baseline: no allowed_paths → only plugin dir +
     system temp are readable
"""

from __future__ import annotations

import asyncio
import os

import pytest

from app.core.plugin.container_runner import ContainerResult
from app.core.plugin.sandbox_runner import (
    SubprocessConfig,
    _make_domain_check,
    execute_in_sandbox,
)

# ── P0-1: container execution chain ──────────────────────────────────

def _patch_canary(monkeypatch, result: ContainerResult) -> None:
    async def fake_canary(**kwargs):
        return result

    monkeypatch.setattr(
        "app.core.plugin.container_runner.execute_with_canary", fake_canary
    )


def _container_config() -> SubprocessConfig:
    return SubprocessConfig(
        runner_mode="container",
        plugin_id="bid_docx@1.0.0",
        user_id=1,
        container_image="hfusionhub-plugin-bid-docx:1.0.0",
        timeout_seconds=10,
    )


def test_container_mode_from_loop_free_thread(monkeypatch):
    """Normal dispatch: asyncio.to_thread worker has no running loop."""
    _patch_canary(
        monkeypatch,
        ContainerResult(success=True, data={"ok": True}, duration_ms=5.0),
    )
    result = execute_in_sandbox(
        plugin_dir="/opt/plugin",
        plugin_name="bid_docx",
        tool_name="bid_export_docx",
        tool_input={},
        config=_container_config(),
    )
    assert result.success is True
    assert result.data == {"ok": True}
    assert result.error_code is None


def test_container_mode_survives_running_loop_thread(monkeypatch):
    """Regression: sync call from a thread WITH a running loop must not
    surface as container_runner_unavailable (historical RuntimeError)."""
    _patch_canary(
        monkeypatch,
        ContainerResult(success=True, data={"ok": True}, duration_ms=5.0),
    )
    config = _container_config()

    async def caller():
        # 模拟旧 bug 场景：async 上下文里直接同步调用（无 to_thread）
        return execute_in_sandbox(
            plugin_dir="/opt/plugin",
            plugin_name="bid_docx",
            tool_name="bid_export_docx",
            tool_input={},
            config=config,
        )

    result = asyncio.run(caller())
    assert result.success is True, f"container chain broken again: {result.error}"
    assert result.data == {"ok": True}


def test_container_mode_fail_closed_on_runner_error(monkeypatch):
    async def boom(**kwargs):
        raise ConnectionError("runner down")

    monkeypatch.setattr(
        "app.core.plugin.container_runner.execute_with_canary", boom
    )
    result = execute_in_sandbox(
        plugin_dir="/opt/plugin",
        plugin_name="p",
        tool_name="t",
        tool_input={},
        config=_container_config(),
    )
    assert result.success is False
    assert result.error_code == "container_runner_unavailable"


# ── P0-6: network default-deny semantics ─────────────────────────────

class TestNetworkDefaultDeny:
    def test_empty_allowlist_denies_everything(self):
        check = _make_domain_check(allowed_domains := [], blocked_domains := [])
        with pytest.raises(OSError, match="default-deny|no allowed_domains|denied"):
            check("http://93.184.216.34:80/")
        # 显式变量消除未使用告警语义
        assert allowed_domains == [] and blocked_domains == []

    def test_empty_allowlist_denies_hostless_target(self):
        check = _make_domain_check([], [])
        with pytest.raises(OSError, match="denied"):
            check("socket://")

    def test_allowlist_mode_still_permits_matches(self):
        check = _make_domain_check(["api.example.com"], [])
        check("https://api.example.com/v1/data")  # should not raise

    def test_allowlist_mode_blocks_non_matching(self):
        check = _make_domain_check(["api.example.com"], [])
        with pytest.raises(OSError, match="whitelist"):
            check("https://evil.example.com/data")

    def test_blocked_list_beats_allowlist(self):
        check = _make_domain_check(["*.example.com"], ["secret.example.com"])
        with pytest.raises(OSError, match="blocked"):
            check("https://secret.example.com/data")


# ── P0-6: filesystem / network baseline via real subprocess ──────────

def _write_plugin(tmp_path, tool_name: str, fn_source: str) -> str:
    """worker 以 __init__.py 为插件模块根；fn_source 为完整函数定义源码。"""
    plugin_dir = tmp_path / f"plugin_{tool_name}"
    plugin_dir.mkdir()
    (plugin_dir / "__init__.py").write_text(fn_source, encoding="utf-8")
    return str(plugin_dir)


def test_fs_default_baseline_reads_own_plugin_dir(tmp_path):
    plugin_dir = tmp_path / "plugin_own"
    plugin_dir.mkdir()
    (plugin_dir / "data.txt").write_text("hello", encoding="utf-8")
    (plugin_dir / "__init__.py").write_text(
        "import os\n"
        "def read_own(**kwargs):\n"
        "    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data.txt')\n"
        "    with open(p, 'r', encoding='utf-8') as f:\n"
        "        return {'size': len(f.read())}\n",
        encoding="utf-8",
    )
    result = execute_in_sandbox(
        plugin_dir=str(plugin_dir),
        plugin_name="plugin_own",
        tool_name="read_own",
        tool_input={},
        config=SubprocessConfig(runner_mode="subprocess", timeout_seconds=20),
    )
    assert result.success is True, result.error
    assert result.data == {"size": 5}


def test_fs_default_baseline_denies_paths_outside_baseline(tmp_path):
    # home 目录不在「插件目录 + 系统临时目录」基线内（两个平台均成立）
    outside = os.path.join(os.path.expanduser("~"), "hfh_sandbox_probe.txt")
    plugin_dir = _write_plugin(
        tmp_path,
        "read_outside",
        "import os\n"
        "def read_outside(**kwargs):\n"
        f"    with open({outside!r}, 'r', encoding='utf-8') as f:\n"
        "        return {'ok': True}\n",
    )
    result = execute_in_sandbox(
        plugin_dir=plugin_dir,
        plugin_name="plugin_read_outside",
        tool_name="read_outside",
        tool_input={},
        config=SubprocessConfig(runner_mode="subprocess", timeout_seconds=20),
    )
    assert result.success is False
    assert "SANDBOX VIOLATION" in (result.error or "")


def test_network_default_deny_blocks_connect_in_subprocess(tmp_path):
    # 未声明 allowed_domains 的插件：socket 连接必须被 default-deny 拒绝
    plugin_dir = _write_plugin(
        tmp_path,
        "net_probe",
        "import socket\n"
        "def net_probe(**kwargs):\n"
        "    socket.create_connection(('93.184.216.34', 80), timeout=1)\n"
        "    return {'ok': True}\n",
    )
    result = execute_in_sandbox(
        plugin_dir=plugin_dir,
        plugin_name="plugin_net_probe",
        tool_name="net_probe",
        tool_input={},
        config=SubprocessConfig(runner_mode="subprocess", timeout_seconds=20),
    )
    assert result.success is False
    assert "SANDBOX VIOLATION" in (result.error or "")
