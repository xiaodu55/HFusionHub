"""Test plugin tools for the container integration fixture image.

These tools are copied into /opt/plugin/plugin.py of the test image and
discovered by /opt/plugin/run_tool.py. They exercise the fixed entry-point
contract, network policy, and resource-limit introspection.
"""

import json
import os
import time


def echo_tool(text: str = "") -> dict:
    """Deterministic tool — returns a predictable JSON result."""
    return {"echo": text, "tool": "echo_tool", "source": "container"}


def network_probe_tool(url: str = "") -> dict:
    """Attempt an outbound HTTP request (used to verify network policy)."""
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            status = resp.status
        return {"ok": True, "status": status}
    except Exception as e:  # noqa: BLE001 — report the failure to the test
        return {"ok": False, "error": str(e)}


def resource_report_tool() -> dict:
    """Report resource limits visible inside the running container."""
    info = {}
    for key, path in (
        ("pids", "/sys/fs/cgroup/pids/pids.max"),
        ("memory", "/sys/fs/cgroup/memory/memory.limit_in_bytes"),
        ("cpu_quota", "/sys/fs/cgroup/cpu/cpu.cfs_quota_us"),
        ("cpu_period", "/sys/fs/cgroup/cpu/cpu.cfs_period_us"),
    ):
        try:
            with open(path) as f:
                info[key] = f.read().strip()
        except Exception:
            info[key] = None

    # Test whether the root filesystem is writable.
    marker = "/tmp/sandbox-write-test"
    try:
        with open(marker, "w") as f:
            f.write("x")
        os.remove(marker)
        info["rootfs_writable"] = True
    except Exception:
        info["rootfs_writable"] = False

    # read-only flag is NOT honored by -o flag; /tmp is tmpfs (writable).
    info["tmpfs_writable"] = True
    info["tool"] = "resource_report_tool"
    return info


def sleep_tool(seconds: float = 0.1) -> dict:
    time.sleep(float(seconds))
    return {"slept": float(seconds), "tool": "sleep_tool"}