"""Plugin registry — manages installed plugins, enforces sandboxed execution.

All plugin tool execution goes through execute_plugin_tool() which runs
in a sandboxed subprocess.  The main process NEVER imports plugin code.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .loader import PluginDescriptor, load_plugin_from_wheel, load_plugin_from_directory, PluginLoadError
from .manifest import compute_manifest_hash
from .sandbox import PluginSandbox, SandboxConfig
from .sandbox_runner import SubprocessConfig, execute_in_sandbox, SubprocessResult
from .audit import (
    record_install, record_enable, record_disable, record_uninstall,
    record_tool_execution, record_audit, ACTION_SANDBOX_VIOLATION,
)

logger = logging.getLogger(__name__)

_registry_lock = threading.Lock()
_plugins: Dict[str, "RegisteredPlugin"] = {}


@dataclass
class RegisteredPlugin:
    """A plugin registered in the runtime registry."""
    descriptor: PluginDescriptor
    sandbox: Optional[PluginSandbox] = None
    enabled: bool = True
    tool_specs: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def plugin_id(self) -> str:
        return self.descriptor.plugin_id

    @property
    def name(self) -> str:
        return self.descriptor.name

    @property
    def version(self) -> str:
        return self.descriptor.version

    @property
    def manifest_hash(self) -> str:
        return self.descriptor.manifest_hash

    @property
    def extract_dir(self) -> str:
        return self.descriptor.extract_dir

    def to_subprocess_config(self, user_id: Optional[int] = None) -> SubprocessConfig:
        """Convert sandbox config to SubprocessConfig for the runner."""
        cfg = SubprocessConfig()
        if self.sandbox and self.sandbox._config:
            sc = self.sandbox._config
            if sc.network:
                cfg.allowed_domains = sc.network.allowed_domains
                cfg.blocked_domains = sc.network.blocked_domains
                cfg.timeout_seconds = sc.network.timeout_seconds
            if sc.filesystem:
                cfg.allowed_paths = sc.filesystem.allowed_paths
                cfg.blocked_paths = sc.filesystem.blocked_paths
            if sc.resources:
                cfg.cpu_seconds = sc.resources.cpu_seconds
                cfg.memory_mb = sc.resources.memory_mb
                cfg.timeout_seconds = sc.resources.timeout_seconds
                cfg.max_open_files = sc.resources.max_open_files
            # Container mode settings from sandbox config
            if sc.runner:
                cfg.runner_mode = sc.runner.mode or "subprocess"
                # Container mode is ALWAYS fail-closed — production cannot let a
                # plugin manifest disable it. Subprocess execution must be chosen
                # explicitly via runner.mode="subprocess", never as a fallback.
                cfg.fail_closed = True if cfg.runner_mode == "container" else sc.runner.fail_closed

        # Always set plugin identity for execution
        cfg.plugin_id = self.plugin_id
        cfg.user_id = user_id

        # Java backend for canary version fetch
        cfg.java_backend_url = os.environ.get("JAVA_BACKEND_URL", "http://localhost:8080")
        cfg.internal_token = os.environ.get("INTERNAL_API_TOKEN", "")

        return cfg


def register_plugin(descriptor: PluginDescriptor) -> RegisteredPlugin:
    plugin = RegisteredPlugin(
        descriptor=descriptor,
        sandbox=PluginSandbox.from_config_dict(descriptor.sandbox_config or {}),
        enabled=True,
        tool_specs=descriptor.tool_specs,
    )
    with _registry_lock:
        _plugins[descriptor.plugin_id] = plugin
    logger.info("插件已注册: %s (tools=%d, sandboxed=True)", descriptor.plugin_id, len(descriptor.tool_specs))
    return plugin


def unregister_plugin(plugin_id: str) -> bool:
    with _registry_lock:
        if plugin_id in _plugins:
            del _plugins[plugin_id]
            logger.info("插件已注销: %s", plugin_id)
            return True
    return False


def get_plugin(plugin_id: str) -> Optional[RegisteredPlugin]:
    with _registry_lock:
        return _plugins.get(plugin_id)


def get_plugin_by_name(name: str) -> Optional[RegisteredPlugin]:
    with _registry_lock:
        for p in _plugins.values():
            if p.name == name:
                return p
    return None


def list_plugins(enabled_only: bool = True) -> List[RegisteredPlugin]:
    with _registry_lock:
        plugins = list(_plugins.values())
    if enabled_only:
        plugins = [p for p in plugins if p.enabled]
    return plugins


def list_all_tool_specs(enabled_only: bool = True) -> List[Dict[str, Any]]:
    specs = []
    for plugin in list_plugins(enabled_only=enabled_only):
        for spec in plugin.tool_specs:
            enriched = dict(spec)
            enriched["_plugin_id"] = plugin.plugin_id
            enriched["_plugin_name"] = plugin.name
            enriched["_plugin_version"] = plugin.version
            specs.append(enriched)
    return specs


def enable_plugin(plugin_id: str) -> bool:
    with _registry_lock:
        plugin = _plugins.get(plugin_id)
        if plugin:
            plugin.enabled = True
            logger.info("插件已启用: %s", plugin_id)
            return True
    return False


def disable_plugin(plugin_id: str) -> bool:
    with _registry_lock:
        plugin = _plugins.get(plugin_id)
        if plugin:
            plugin.enabled = False
            logger.info("插件已禁用: %s", plugin_id)
            return True
    return False


def verify_manifest_integrity(plugin_id: str, expected_hash: str) -> bool:
    with _registry_lock:
        plugin = _plugins.get(plugin_id)
        if not plugin:
            return False
        return plugin.manifest_hash == expected_hash


def load_and_register_wheel(
    wheel_path: str,
    plugin_id: Optional[str] = None,
    expected_hash: Optional[str] = None,
) -> RegisteredPlugin:
    """Load and register a plugin from a wheel.

    Mandatory hash verification: expected_hash MUST be provided.
    """
    if not expected_hash:
        raise PluginLoadError("(unknown)", "安装需要提供 expected_hash（供应链完整性校验）")

    descriptor = load_plugin_from_wheel(
        wheel_path, plugin_id,
        require_hash=True, expected_hash=expected_hash,
    )
    return register_plugin(descriptor)


def load_and_register_directory(
    dir_path: str,
    plugin_id: Optional[str] = None,
) -> RegisteredPlugin:
    descriptor = load_plugin_from_directory(dir_path, plugin_id)
    return register_plugin(descriptor)


def execute_plugin_tool(
    plugin_id: str,
    tool_name: str,
    tool_input: Dict[str, Any],
    trace_id: Optional[str] = None,
    user_id: Optional[int] = None,
) -> SubprocessResult:
    """Execute a plugin tool in a sandboxed subprocess.

    This is the ONLY entry point for plugin code execution.
    The main process NEVER imports plugin modules.

    When user_id is provided and the plugin has container mode enabled,
    canary routing (execute_with_canary) is used for sticky version selection
    with digest-verified container execution.
    """
    plugin = get_plugin(plugin_id)
    if not plugin:
        return SubprocessResult(
            success=False,
            error=f"插件未注册: {plugin_id}",
            error_code="plugin_not_registered",
        )

    if not plugin.enabled:
        return SubprocessResult(
            success=False,
            error=f"插件已禁用: {plugin_id}",
            error_code="plugin_disabled",
        )

    # Build subprocess config from sandbox, passing user_id for canary routing
    sub_config = plugin.to_subprocess_config(user_id=user_id)

    start_time = time.monotonic()
    result = execute_in_sandbox(
        plugin_dir=plugin.extract_dir,
        plugin_name=plugin.name,
        tool_name=tool_name,
        tool_input=tool_input,
        config=sub_config,
    )
    duration_ms = round((time.monotonic() - start_time) * 1000, 2)

    # Audit the execution
    record_tool_execution(
        plugin_id=plugin_id,
        plugin_name=plugin.name,
        tool_name=tool_name,
        success=result.success,
        duration_ms=duration_ms,
        plugin_version=plugin.version,
        trace_id=trace_id,
        error=result.error if not result.success else None,
    )

    if not result.success and result.error_code == "plugin_timeout":
        logger.warning("插件工具执行超时: %s.%s (%.1fs)", plugin_id, tool_name, sub_config.timeout_seconds)

    return result


def clear_registry() -> int:
    with _registry_lock:
        count = len(_plugins)
        _plugins.clear()
    if count:
        logger.info("注册表已清空: %d 个插件", count)
    return count
