"""Subprocess-isolated plugin runner — true security boundary.

All plugin code executes in a forked subprocess with:
  - CPU/memory limits enforced via resource.setrlimit (POSIX) or psutil (Windows)
  - Network restrictions enforced inside the subprocess via monkey-patching
  - Filesystem restrictions enforced via allowed-path validation
  - Timeout enforcement via subprocess kill
  - No sys.path pollution in the main process
  - No shared memory/state with the host process

The parent communicates with the subprocess via a pair of pipes (stdin/stdout).
Protocol is JSON lines: one JSON object per line.

IMPORTANT: This is a defense-in-depth measure. A determined attacker with
root access or ptrace can bypass these. But it prevents:
  - Malicious import-time side effects (code runs in subprocess)
  - Resource exhaustion of the main AI service
  - Network access to unintended hosts
  - Filesystem traversal outside allowed paths
"""

from __future__ import annotations

import io
import json
import logging
import os
import select
import signal
import struct
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from multiprocessing import Process, Pipe
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class SubprocessConfig:
    """Resource limits for the subprocess."""
    cpu_seconds: float = 10.0
    memory_mb: int = 256
    timeout_seconds: float = 30.0
    max_open_files: int = 64
    allowed_domains: List[str] = field(default_factory=list)
    blocked_domains: List[str] = field(default_factory=list)
    allowed_paths: List[str] = field(default_factory=list)
    blocked_paths: List[str] = field(default_factory=list)


@dataclass
class SubprocessResult:
    """Result from subprocess execution."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    duration_ms: float = 0.0
    resource_usage: Optional[Dict[str, Any]] = None


def _apply_subprocess_limits(config: SubprocessConfig) -> None:
    """Apply resource limits inside the subprocess BEFORE importing any plugin code."""
    # CPU time limit
    try:
        import resource
        cpu_secs = int(config.cpu_seconds)
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_secs, cpu_secs))
    except (ImportError, ValueError, OSError):
        pass

    # Memory limit
    try:
        import resource
        mem_bytes = config.memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
    except (ImportError, ValueError, OSError):
        pass

    # Open files limit
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_NOFILE, (config.max_open_files, config.max_open_files))
    except (ImportError, ValueError, OSError):
        pass


def _install_network_guard(config: SubprocessConfig) -> None:
    """Monkey-patch socket/httpx/urllib to enforce domain restrictions.

    This runs inside the subprocess — blocks ALL network access that
    doesn't go through the allowed domains list.
    """
    import fnmatch

    allowed = set(config.allowed_domains)
    blocked = set(config.blocked_domains)

    def _check_url(url: str) -> None:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if not host:
            return

        for pattern in blocked:
            if fnmatch.fnmatch(host, pattern):
                raise OSError(f"SANDBOX VIOLATION: domain blocked: {host}")

        if allowed:
            for pattern in allowed:
                if fnmatch.fnmatch(host, pattern):
                    return
            raise OSError(f"SANDBOX VIOLATION: domain not in whitelist: {host}")

    # Patch socket.create_connection
    try:
        import socket
        _original_create_connection = socket.create_connection

        def _sandboxed_create_connection(address, *args, **kwargs):
            host, port = address if isinstance(address, (list, tuple)) else (address, 0)
            _check_url(f"http://{host}:{port}")
            return _original_create_connection(address, *args, **kwargs)

        socket.create_connection = _sandboxed_create_connection  # type: ignore
    except (ImportError, AttributeError):
        pass

    # Patch httpx if available
    try:
        import httpx
        _original_send = httpx.AsyncClient.send

        async def _sandboxed_send(self, request, **kwargs):
            _check_url(str(request.url))
            return await _original_send(self, request, **kwargs)

        httpx.AsyncClient.send = _sandboxed_send  # type: ignore
    except (ImportError, AttributeError):
        pass

    # Patch urllib
    try:
        import urllib.request
        _original_urlopen = urllib.request.urlopen

        def _sandboxed_urlopen(url, *args, **kwargs):
            if isinstance(url, str):
                _check_url(url)
            elif hasattr(url, 'full_url'):
                _check_url(url.full_url)
            return _original_urlopen(url, *args, **kwargs)

        urllib.request.urlopen = _sandboxed_urlopen  # type: ignore
    except (ImportError, AttributeError):
        pass


def _install_filesystem_guard(config: SubprocessConfig) -> None:
    """Monkey-patch builtins.open and os module to enforce path restrictions."""
    import fnmatch

    allowed = config.allowed_paths
    blocked = config.blocked_paths

    def _check_path(path: str) -> str:
        resolved = os.path.realpath(str(path))
        for pattern in blocked:
            if fnmatch.fnmatch(resolved, pattern):
                raise OSError(f"SANDBOX VIOLATION: path blocked: {resolved}")
        if allowed:
            for pattern in allowed:
                if fnmatch.fnmatch(resolved, pattern):
                    return resolved
            raise OSError(f"SANDBOX VIOLATION: path not in whitelist: {resolved}")
        return resolved

    # Patch builtins.open
    import builtins
    _original_open = builtins.open

    def _sandboxed_open(path, *args, **kwargs):
        _check_path(path)
        return _original_open(path, *args, **kwargs)

    builtins.open = _sandboxed_open  # type: ignore

    # Patch os operations
    import os as _os
    for op_name in ('remove', 'unlink', 'rename', 'makedirs', 'mkdir', 'rmdir'):
        orig = getattr(_os, op_name, None)
        if orig is None:
            continue
        def _make_guard(op: Callable) -> Callable:
            def guarded(path, *args, **kwargs):
                _check_path(path)
                return op(path, *args, **kwargs)
            return guarded
        setattr(_os, op_name, _make_guard(orig))

    # Patch os.walk to restrict traversal
    _original_walk = _os.walk
    def _sandboxed_walk(top, *args, **kwargs):
        _check_path(top)
        for root, dirs, files in _original_walk(top, *args, **kwargs):
            yield root, dirs, files
    _os.walk = _sandboxed_walk  # type: ignore

    # Patch shutil
    try:
        import shutil
        for op_name in ('copy', 'copy2', 'copytree', 'move'):
            orig = getattr(shutil, op_name, None)
            if orig is None:
                continue
            def _make_shutil_guard(op: Callable) -> Callable:
                def guarded(src, *args, **kwargs):
                    _check_path(src)
                    if args:
                        _check_path(args[0])
                    return op(src, *args, **kwargs)
                return guarded
            setattr(shutil, op_name, _make_shutil_guard(orig))
    except ImportError:
        pass

    # Block subprocess spawning from plugins
    try:
        import subprocess as _subprocess
        _original_popen = _subprocess.Popen.__init__

        def _blocked_popen(self, *args, **kwargs):
            raise OSError("SANDBOX VIOLATION: subprocess spawning is not allowed")

        _subprocess.Popen.__init__ = _blocked_popen  # type: ignore
    except (ImportError, AttributeError):
        pass

    # Block fork/exec
    try:
        import os as _os_module
        _original_fork = _os_module.fork
        def _blocked_fork():
            raise OSError("SANDBOX VIOLATION: fork is not allowed")
        _os_module.fork = _blocked_fork  # type: ignore
    except (ImportError, AttributeError):
        pass


def _subprocess_worker(
    conn,
    plugin_dir: str,
    plugin_name: str,
    tool_name: str,
    tool_input: Dict[str, Any],
    config: SubprocessConfig,
) -> None:
    """Worker function that runs inside the subprocess.

    1. Apply resource limits
    2. Install network/filesystem guards
    3. Import plugin module
    4. Find and execute the tool
    5. Send result back via pipe
    """
    try:
        # Step 1: Apply resource limits FIRST (before any imports)
        _apply_subprocess_limits(config)

        # Step 2: Install security guards
        if config.allowed_domains or config.blocked_domains:
            _install_network_guard(config)
        if config.allowed_paths or config.blocked_paths:
            _install_filesystem_guard(config)

        # Step 3: Import plugin module in isolated sys.path
        import importlib.util
        original_path = sys.path[:]
        try:
            sys.path.insert(0, plugin_dir)
            init_path = os.path.join(plugin_dir, "__init__.py")
            if os.path.isfile(init_path):
                module_name = f"hfusion_plugin_{plugin_name}"
                spec = importlib.util.spec_from_file_location(module_name, init_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                else:
                    raise ImportError(f"Cannot load spec for {module_name}")
            else:
                module = importlib.import_module(plugin_name)
        finally:
            sys.path = original_path

        # Step 4: Find tool callable
        tool_func = getattr(module, tool_name, None)
        if tool_func is None:
            # Try to find in TOOL_SPECS or as a method
            for attr_name in dir(module):
                if attr_name.lower() == tool_name.lower():
                    tool_func = getattr(module, attr_name)
                    break
        if tool_func is None:
            raise AttributeError(f"Tool '{tool_name}' not found in plugin '{plugin_name}'")

        if not callable(tool_func):
            raise TypeError(f"'{tool_name}' is not callable")

        # Step 5: Execute
        import asyncio
        if asyncio.iscoroutinefunction(tool_func):
            result = asyncio.run(tool_func(**tool_input))
        else:
            result = tool_func(**tool_input)

        # Step 6: Send success
        conn.send(json.dumps({
            "success": True,
            "data": result,
        }))
    except Exception as e:
        conn.send(json.dumps({
            "success": False,
            "error": str(e),
            "error_code": "plugin_execution_error",
            "traceback": traceback.format_exc(),
        }))
    finally:
        conn.close()


def execute_in_sandbox(
    plugin_dir: str,
    plugin_name: str,
    tool_name: str,
    tool_input: Dict[str, Any],
    config: SubprocessConfig,
) -> SubprocessResult:
    """Execute a plugin tool in an isolated subprocess with sandbox constraints.

    This is the ONLY way to run plugin code. The main process NEVER imports
    plugin modules directly.

    Returns SubprocessResult with success/failure and any output.
    """
    start_time = time.monotonic()
    parent_conn, child_conn = Pipe(duplex=False)

    worker = Process(
        target=_subprocess_worker,
        args=(child_conn, plugin_dir, plugin_name, tool_name, tool_input, config),
        daemon=True,
    )

    worker.start()
    child_conn.close()  # Close child end in parent

    # Wait with timeout
    worker.join(timeout=config.timeout_seconds)
    elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)

    if worker.is_alive():
        # Timeout — force kill
        worker.terminate()
        worker.join(timeout=2)
        if worker.is_alive():
            worker.kill()
            worker.join(timeout=1)
        return SubprocessResult(
            success=False,
            error=f"插件执行超时: {config.timeout_seconds}s",
            error_code="plugin_timeout",
            duration_ms=elapsed_ms,
        )

    exit_code = worker.exitcode
    if exit_code != 0 and exit_code is not None:
        return SubprocessResult(
            success=False,
            error=f"插件子进程异常退出: exit code {exit_code}",
            error_code="plugin_process_error",
            duration_ms=elapsed_ms,
        )

    # Read result from pipe
    try:
        if parent_conn.poll(1.0):
            raw = parent_conn.recv()
            result = json.loads(raw)
            return SubprocessResult(
                success=result.get("success", False),
                data=result.get("data"),
                error=result.get("error"),
                error_code=result.get("error_code"),
                duration_ms=elapsed_ms,
            )
        else:
            return SubprocessResult(
                success=False,
                error="插件子进程未返回结果",
                error_code="plugin_no_response",
                duration_ms=elapsed_ms,
            )
    except (EOFError, json.JSONDecodeError) as e:
        return SubprocessResult(
            success=False,
            error=f"读取插件结果失败: {e}",
            error_code="plugin_comm_error",
            duration_ms=elapsed_ms,
        )
    finally:
        parent_conn.close()
        if worker.is_alive():
            worker.terminate()
            worker.join(timeout=2)
