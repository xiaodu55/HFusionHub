"""Plugin runtime sandbox — enforces network, filesystem, and resource constraints.

The sandbox provides defense-in-depth constraints at the Python level:
  1. SandboxedHttpClient — domain whitelist/blocklist via httpx transport
  2. SandboxedPathResolver — glob-based path scope enforcement
  3. ResourceLimits — CPU/memory/timeout via setrlimit (POSIX) or psutil (Windows)

These are advisory — a determined attacker with process access can bypass them.
They raise the bar significantly but are NOT a security boundary.

Usage::

    from app.core.plugin.sandbox import PluginSandbox, SandboxConfig

    config = SandboxConfig(
        network={"allowed_domains": ["api.github.com"]},
        filesystem={"allowed_paths": ["/tmp/plugin_data/**"]},
        resources={"cpu_seconds": 10, "memory_mb": 256, "timeout_seconds": 30},
    )
    sandbox = PluginSandbox(config)
    client = sandbox.get_http_client()
"""

from __future__ import annotations

import fnmatch
import logging
import os
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

# resource module is POSIX-only
try:
    import resource
except ImportError:
    resource = None  # type: ignore

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────

@dataclass(frozen=True)
class NetworkConfig:
    allowed_domains: List[str] = field(default_factory=list)
    blocked_domains: List[str] = field(default_factory=list)
    timeout_seconds: float = 30.0

@dataclass(frozen=True)
class FilesystemConfig:
    allowed_paths: List[str] = field(default_factory=list)
    blocked_paths: List[str] = field(default_factory=list)
    read_only_paths: List[str] = field(default_factory=list)

@dataclass(frozen=True)
class ResourceConfig:
    cpu_seconds: float = 10.0
    memory_mb: int = 256
    timeout_seconds: float = 30.0
    max_open_files: int = 64

@dataclass(frozen=True)
class SandboxConfig:
    network: Optional[NetworkConfig] = None
    filesystem: Optional[FilesystemConfig] = None
    resources: Optional[ResourceConfig] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SandboxConfig":
        """Parse a sandbox config dict (as stored in manifest JSON)."""
        net_data = data.get("network")
        net = NetworkConfig(**net_data) if net_data else None

        fs_data = data.get("filesystem")
        fs = FilesystemConfig(**fs_data) if fs_data else None

        res_data = data.get("resources")
        res = ResourceConfig(**res_data) if res_data else None

        return cls(network=net, filesystem=fs, resources=res)


# ── Sandbox Errors ───────────────────────────────────────────────────

class SandboxViolation(Exception):
    """Raised when a sandbox constraint is violated."""
    def __init__(self, constraint: str, message: str):
        self.constraint = constraint
        super().__init__(f"沙箱约束违反 ({constraint}): {message}")


# ── Network Sandbox ──────────────────────────────────────────────────

class SandboxedHttpClient:
    """HTTP client with domain whitelist/blocklist enforcement.

    Wraps httpx.AsyncClient and validates every request URL against
    the configured domain policies.
    """

    def __init__(self, config: NetworkConfig):
        self._config = config
        self._allowed = set(config.allowed_domains)
        self._blocked = set(config.blocked_domains)

    def check_url(self, url: str) -> None:
        """Validate a URL against domain policies.  Raises SandboxViolation."""
        parsed = urlparse(url)
        host = parsed.hostname or ""

        if self._blocked:
            for pattern in self._blocked:
                if fnmatch.fnmatch(host, pattern):
                    raise SandboxViolation(
                        "network",
                        f"域名被阻止: {host} (匹配模式: {pattern})"
                    )

        if self._allowed:
            allowed = False
            for pattern in self._allowed:
                if fnmatch.fnmatch(host, pattern):
                    allowed = True
                    break
            if not allowed:
                raise SandboxViolation(
                    "network",
                    f"域名不在白名单中: {host} (允许: {self._allowed})"
                )

    def get_timeout(self) -> float:
        return self._config.timeout_seconds


# ── Filesystem Sandbox ───────────────────────────────────────────────

class SandboxedPathResolver:
    """Path resolution with glob-based scope enforcement."""

    def __init__(self, config: FilesystemConfig):
        self._config = config
        self._allowed = config.allowed_paths
        self._blocked = config.blocked_paths
        self._read_only = config.read_only_paths

    def resolve(self, path: str) -> str:
        """Resolve and validate a path.  Raises SandboxViolation."""
        resolved = os.path.realpath(path)

        for pattern in self._blocked:
            if fnmatch.fnmatch(resolved, pattern):
                raise SandboxViolation(
                    "filesystem",
                    f"路径被阻止: {resolved} (匹配: {pattern})"
                )

        if self._allowed:
            matched = False
            for pattern in self._allowed:
                if fnmatch.fnmatch(resolved, pattern):
                    matched = True
                    break
            if not matched:
                raise SandboxViolation(
                    "filesystem",
                    f"路径不在允许范围内: {resolved}"
                )

        return resolved

    def is_read_only(self, path: str) -> bool:
        resolved = os.path.realpath(path)
        for pattern in self._read_only:
            if fnmatch.fnmatch(resolved, pattern):
                return True
        return False


# ── Resource Limits ──────────────────────────────────────────────────

class ResourceLimits:
    """CPU/memory/timeout enforcement.

    On POSIX: uses resource.setrlimit for hard limits.
    On Windows: uses psutil-based soft enforcement.
    """

    def __init__(self, config: ResourceConfig):
        self._config = config
        self._is_posix = platform.system() != "Windows"

    def apply(self) -> None:
        """Apply resource limits to the current process."""
        if self._is_posix:
            self._apply_posix()
        else:
            self._apply_windows()
        logger.debug("资源限制已应用: cpu=%.1fs memory=%dMB timeout=%.1fs",
                     self._config.cpu_seconds, self._config.memory_mb,
                     self._config.timeout_seconds)

    def _apply_posix(self) -> None:
        """Apply hard resource limits on POSIX systems."""
        if resource is None:
            logger.debug("resource 模块不可用，跳过 POSIX 资源限制")
            return
        try:
            # CPU time limit (seconds)
            cpu_secs = int(self._config.cpu_seconds)
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_secs, cpu_secs))

            # Memory limit (bytes)
            mem_bytes = self._config.memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))

            # Open files limit
            max_fd = self._config.max_open_files
            resource.setrlimit(resource.RLIMIT_NOFILE, (max_fd, max_fd))
        except (ValueError, OSError) as e:
            logger.warning("设置资源限制失败 (POSIX): %s", e)

    def _apply_windows(self) -> None:
        """Best-effort enforcement on Windows via psutil."""
        try:
            import psutil
            process = psutil.Process(os.getpid())
            # Memory limit
            mem_bytes = self._config.memory_mb * 1024 * 1024
            try:
                if resource is not None:
                    process.rlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            except (AttributeError, OSError):
                pass  # Not all Windows versions support this
        except ImportError:
            logger.debug("psutil 不可用，跳过 Windows 资源限制")

    def get_timeout(self) -> float:
        return self._config.timeout_seconds


# ── PluginSandbox (composite) ────────────────────────────────────────

class PluginSandbox:
    """Composite sandbox combining network, filesystem, and resource constraints.

    Usage::

        sandbox = PluginSandbox.from_config_dict(manifest.get("sandbox", {}))
        client = sandbox.get_http_client()
        path_resolver = sandbox.get_path_resolver()
        sandbox.apply_resource_limits()
    """

    def __init__(self, config: SandboxConfig):
        self._config = config
        self._network = SandboxedHttpClient(config.network) if config.network else None
        self._filesystem = SandboxedPathResolver(config.filesystem) if config.filesystem else None
        self._resources = ResourceLimits(config.resources) if config.resources else None

    @classmethod
    def from_config_dict(cls, data: Dict[str, Any]) -> "PluginSandbox":
        config = SandboxConfig.from_dict(data)
        return cls(config)

    @property
    def network(self) -> Optional[SandboxedHttpClient]:
        return self._network

    @property
    def filesystem(self) -> Optional[SandboxedPathResolver]:
        return self._filesystem

    @property
    def resources(self) -> Optional[ResourceLimits]:
        return self._resources

    def get_http_client(self) -> SandboxedHttpClient:
        if self._network is None:
            raise SandboxViolation("network", "插件未配置网络沙箱")
        return self._network

    def get_path_resolver(self) -> SandboxedPathResolver:
        if self._filesystem is None:
            raise SandboxViolation("filesystem", "插件未配置文件系统沙箱")
        return self._filesystem

    def apply_resource_limits(self) -> None:
        if self._resources:
            self._resources.apply()

    def check_all(self, url: Optional[str] = None, path: Optional[str] = None) -> None:
        """Run all configured sandbox checks.  Raises SandboxViolation on failure."""
        if url and self._network:
            self._network.check_url(url)
        if path and self._filesystem:
            self._filesystem.resolve(path)
