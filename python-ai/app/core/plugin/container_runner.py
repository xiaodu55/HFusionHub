"""Docker container-based plugin runner — communicates with plugin-runner service.

This module replaces subprocess execution with real container isolation.
Python AI sends execution requests to the independent plugin-runner service,
which holds Docker daemon privileges.

Key changes from v1:
- No /build endpoint — uses pre-built registry images with digest verification
- Sticky canary routing via compute_sticky_version()
- Runner unreachable = hard failure (no subprocess fallback)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from app.core.llm.http_client import get_shared_client

logger = logging.getLogger(__name__)

PLUGIN_RUNNER_URL = os.environ.get("PLUGIN_RUNNER_URL", "http://localhost:9100")
PLUGIN_RUNNER_TOKEN = os.environ.get("PLUGIN_RUNNER_TOKEN", "")
DEFAULT_TIMEOUT = float(os.environ.get("PLUGIN_RUNNER_TIMEOUT", "60"))


@dataclass
class ContainerConfig:
    """Resource limits for container execution."""
    cpu_limit: float = 1.0
    memory_limit: str = "256m"
    timeout: float = 30.0
    network: str = "plugin-isolated"
    read_only_rootfs: bool = True
    allowed_domains: List[str] = field(default_factory=list)
    blocked_domains: List[str] = field(default_factory=list)
    tmpfs_size: str = "100m"
    pids_limit: int = 256


@dataclass
class ContainerResult:
    """Result from container execution."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    duration_ms: float = 0.0
    resource_usage: Optional[Dict[str, Any]] = None
    container_id: Optional[str] = None


@dataclass
class PluginVersionInfo:
    """Plugin version info from Java backend for canary routing."""
    version: str
    container_image: str
    image_digest: str
    canary_weight: float
    is_stable: bool


async def execute_in_container(
    image_tag: str,
    tool_name: str,
    tool_input: Dict[str, Any],
    config: ContainerConfig = ContainerConfig(),
    plugin_id: Optional[str] = None,
    user_id: Optional[int] = None,
    image_digest: Optional[str] = None,
) -> ContainerResult:
    """Execute a plugin tool in a Docker container via plugin-runner service.

    Image digest is mandatory for supply chain integrity.
    """
    if not image_digest or not image_digest.strip():
        return ContainerResult(
            success=False,
            error="image_digest is required for container execution",
            error_code="missing_digest",
            duration_ms=0.0,
        )
    if not PLUGIN_RUNNER_TOKEN:
        return ContainerResult(
            success=False,
            error="PLUGIN_RUNNER_TOKEN is not configured; execution blocked (fail_closed)",
            error_code="runner_not_configured",
            duration_ms=0.0,
        )

    start_time = time.monotonic()

    # R15-14：复用共享连接池（长超时用于整段插件执行），替代每次新建 AsyncClient
    client = get_shared_client("plugin-runner", timeout=config.timeout + 5.0)
    try:
        resp = await client.post(
            f"{PLUGIN_RUNNER_URL}/execute",
            json={
                "image_tag": image_tag,
                "tool_name": tool_name,
                "tool_input": tool_input,
                "config": {
                    "cpu_limit": config.cpu_limit,
                    "memory_limit": config.memory_limit,
                    "timeout": config.timeout,
                    "network": config.network,
                    "read_only_rootfs": config.read_only_rootfs,
                    "allowed_domains": config.allowed_domains,
                    "blocked_domains": config.blocked_domains,
                    "tmpfs_size": config.tmpfs_size,
                    "pids_limit": config.pids_limit,
                },
                "plugin_id": plugin_id,
                "user_id": user_id,
                "image_digest": image_digest,
            },
            headers={"X-Runner-Token": PLUGIN_RUNNER_TOKEN},
        )
        resp.raise_for_status()
        result = resp.json()
        elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)

        return ContainerResult(
            success=result.get("success", False),
            data=result.get("data"),
            error=result.get("error"),
            error_code=result.get("error_code"),
            duration_ms=elapsed_ms,
            resource_usage=result.get("resource_usage"),
            container_id=result.get("container_id"),
        )
    except httpx.ConnectError:
        elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)
        logger.error("Plugin runner unreachable at %s", PLUGIN_RUNNER_URL)
        return ContainerResult(
            success=False,
            error="Plugin runner unreachable — execution blocked (fail_closed)",
            error_code="runner_unreachable",
            duration_ms=elapsed_ms,
        )
    except httpx.TimeoutException:
        elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)
        return ContainerResult(
            success=False,
            error=f"Plugin runner timeout after {config.timeout}s",
            error_code="runner_timeout",
            duration_ms=elapsed_ms,
        )
    except httpx.HTTPStatusError as e:
        elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)
        if e.response.status_code == 400:
            try:
                detail = e.response.json().get("detail", str(e))
            except Exception:
                detail = str(e)
            return ContainerResult(
                success=False,
                error=detail,
                error_code="runner_rejected",
                duration_ms=elapsed_ms,
            )
        raise
    except Exception as e:
        elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)
        logger.exception("Container execution failed")
        return ContainerResult(
            success=False,
            error=str(e),
            error_code="runner_error",
            duration_ms=elapsed_ms,
        )


async def list_container_images() -> List[Dict[str, Any]]:
    """List all plugin Docker images."""
    client = get_shared_client("plugin-runner", timeout=10.0)
    resp = await client.get(
        f"{PLUGIN_RUNNER_URL}/images",
        headers={"X-Runner-Token": PLUGIN_RUNNER_TOKEN},
    )
    resp.raise_for_status()
    return resp.json().get("images", [])


async def remove_container_image(image_tag: str) -> bool:
    """Remove a plugin Docker image."""
    client = get_shared_client("plugin-runner", timeout=10.0)
    resp = await client.delete(
        f"{PLUGIN_RUNNER_URL}/images/{image_tag}",
        headers={"X-Runner-Token": PLUGIN_RUNNER_TOKEN},
    )
    return resp.status_code == 200


async def fetch_plugin_versions(plugin_id: str, java_backend_url: str, internal_token: str) -> List[PluginVersionInfo]:
    """Fetch all versions of a plugin from Java backend for canary routing."""
    client = get_shared_client("plugin-versions", timeout=10.0)
    resp = await client.get(
        f"{java_backend_url}/api/internal/plugin/{plugin_id}/versions",
        headers={"X-Internal-Token": internal_token},
    )
    resp.raise_for_status()
    data = resp.json()
    return [
            PluginVersionInfo(
                version=v["version"],
                container_image=v["container_image"],
                image_digest=v["image_digest"],
                canary_weight=float(v.get("canary_weight", 0)),
                is_stable=v.get("status") == "active" and float(v.get("canary_weight", 0)) == 0,
            )
            for v in data
        ]


def compute_sticky_version(plugin_id: str, user_id: int, versions: List[str], weights: List[float]) -> str:
    """Determine which version a user sees via sticky hash routing.

    hash(user_id + plugin_id) -> weighted selection across available versions.
    Same user always gets same version for consistency.
    """
    if not versions:
        raise ValueError("No versions available")
    if len(versions) == 1:
        return versions[0]

    key = f"{user_id}:{plugin_id}"
    h = int(hashlib.sha256(key.encode()).hexdigest(), 16)
    slot = (h % 10000) / 10000.0

    cumulative = 0.0
    for version, weight in zip(versions, weights):
        cumulative += weight
        if slot < cumulative:
            return version

    return versions[-1]


def select_canary_version(
    plugin_versions: List[PluginVersionInfo],
    user_id: int,
    plugin_id: str,
) -> Optional[PluginVersionInfo]:
    """Select the appropriate version for a user based on canary weights.

    Returns the version to execute (with its container_image and image_digest).
    If no canary weights configured, returns the stable version (canary_weight=0, is_stable=True).
    """
    if not plugin_versions:
        return None

    # Filter to stable + canary versions
    available = [v for v in plugin_versions if v.is_stable or v.canary_weight > 0]
    if not available:
        return None

    # If only one stable version, use it
    stable_versions = [v for v in available if v.is_stable]
    if len(stable_versions) == 1 and all(v.canary_weight == 0 for v in available):
        return stable_versions[0]

    # Build version list and weights for sticky routing.
    # Canary versions use their declared weight (0.0-1.0).
    # Stable versions split the remaining traffic equally.
    canary_weight_sum = sum(v.canary_weight for v in available)
    stable_count = len(stable_versions)

    if canary_weight_sum >= 1.0 or stable_count == 0:
        # All traffic goes to canary versions; stable gets nothing
        pass

    versions = [v.version for v in available]
    weights = []
    remaining_for_stable = max(0.0, 1.0 - canary_weight_sum)
    stable_weight_each = remaining_for_stable / stable_count if stable_count > 0 else 0.0

    for v in available:
        if v.is_stable:
            weights.append(stable_weight_each)
        else:
            weights.append(v.canary_weight)

    # Normalize weights so they sum to 1.0
    total_weight = sum(weights)
    if total_weight == 0:
        # No canary weights, use stable version
        return stable_versions[0] if stable_versions else available[0]
    normalized_weights = [w / total_weight for w in weights]

    selected_version = compute_sticky_version(plugin_id, user_id, versions, normalized_weights)

    # Find the matching PluginVersionInfo
    for v in available:
        if v.version == selected_version:
            return v

    return available[0]


async def execute_with_canary(
    plugin_id: str,
    tool_name: str,
    tool_input: Dict[str, Any],
    user_id: int,
    config: ContainerConfig,
    java_backend_url: str,
    internal_token: str,
) -> ContainerResult:
    """Execute a plugin tool with canary routing.

    Fetches plugin versions from Java, selects version via sticky routing,
    then executes via plugin-runner with digest verification.
    """
    try:
        versions = await fetch_plugin_versions(plugin_id, java_backend_url, internal_token)
    except Exception as e:
        logger.error("Failed to fetch plugin versions from Java backend: %s", e)
        return ContainerResult(
            success=False,
            error=f"Failed to fetch plugin versions: {e}",
            error_code="version_fetch_failed",
            duration_ms=0.0,
        )

    selected = select_canary_version(versions, user_id, plugin_id)

    if not selected:
        return ContainerResult(
            success=False,
            error=f"No executable version found for plugin {plugin_id}",
            error_code="no_version",
            duration_ms=0.0,
        )

    return await execute_in_container(
        image_tag=selected.container_image,
        tool_name=tool_name,
        tool_input=tool_input,
        config=config,
        plugin_id=plugin_id,
        user_id=user_id,
        image_digest=selected.image_digest,
    )
