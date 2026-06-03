"""HFusionHub Plugin Runner — isolated container execution service.

Independent FastAPI service that manages Docker containers for plugin execution.
Communicates with Docker daemon via TCP+TLS (NOT docker socket).

Security model:
  - No docker.sock mount — uses remote Docker API over TLS
  - All plugin containers: cap_drop=ALL, pids_limit=256, no-new-privileges
  - Network policies enforced via iptables inside containers
  - Image allowlist — only pre-built hfusionhub-plugin-* images allowed
  - Constant-time token comparison
  - Read-only root filesystem with tmpfs /tmp
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

PLUGIN_RUNNER_TOKEN = os.environ.get("PLUGIN_RUNNER_TOKEN", "")
PLUGIN_ARTIFACTS_DIR = os.environ.get("PLUGIN_ARTIFACTS_DIR", "/opt/plugin-artifacts")
IMAGE_ALLOWLIST_PREFIX = "hfusionhub-plugin-"
# Docker SDK images.list(name=...) does a reference glob; a bare prefix matches
# nothing (repo segments aren't filtered by substring), so append '*' to match
# all hfusionhub-plugin-* images regardless of tag.
IMAGE_ALLOWLIST_GLOB = f"{IMAGE_ALLOWLIST_PREFIX}*"

# Domains that plugin containers are NEVER allowed to reach, regardless of config
GLOBAL_BLOCKED_DOMAINS = [
    "169.254.169.254",   # AWS metadata
    "metadata.google.internal",  # GCP metadata
    "169.254.169.254.nip.io",   # metadata fallback
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(PLUGIN_ARTIFACTS_DIR, exist_ok=True)
    logger.info("Plugin Runner started, artifacts dir: %s", PLUGIN_ARTIFACTS_DIR)
    yield
    logger.info("Plugin Runner shutting down")


app = FastAPI(title="HFusionHub Plugin Runner", lifespan=lifespan)


def _verify_token(x_runner_token: Optional[str] = Header(None)) -> None:
    if not PLUGIN_RUNNER_TOKEN:
        raise HTTPException(status_code=500, detail="PLUGIN_RUNNER_TOKEN not configured")
    if not x_runner_token:
        raise HTTPException(status_code=403, detail="Forbidden: missing runner token")
    if not hmac.compare_digest(x_runner_token, PLUGIN_RUNNER_TOKEN):
        raise HTTPException(status_code=403, detail="Forbidden: invalid runner token")


# ── Models ───────────────────────────────────────────────────────────

class ContainerConfig(BaseModel):
    cpu_limit: float = 1.0
    memory_limit: str = "256m"
    timeout: float = 30.0
    network: str = "plugin-isolated"
    read_only_rootfs: bool = True
    allowed_domains: List[str] = Field(default_factory=list)
    blocked_domains: List[str] = Field(default_factory=list)
    tmpfs_size: str = "100m"
    pids_limit: int = 256


class ExecuteRequest(BaseModel):
    image_tag: str
    tool_name: str
    tool_input: Dict[str, Any]
    config: ContainerConfig = ContainerConfig()
    plugin_id: Optional[str] = None
    user_id: Optional[int] = None
    image_digest: Optional[str] = None  # SHA-256 digest — validated in handler (400 if missing)


class ExecuteResponse(BaseModel):
    success: bool
    data: Any = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    duration_ms: float = 0.0
    resource_usage: Optional[Dict[str, Any]] = None
    resource_limits: Optional[Dict[str, Any]] = None
    container_id: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    docker_connected: bool
    images_count: int
    # 为什么不可用（如 dev 无 TLS Docker Engine）。有值即表示 503；
    # 健康时为空字符串。让「unhealthy」一眼可读，而不是像启动失败。
    reason: str = ""


# ── Docker client ────────────────────────────────────────────────────

_docker_client = None


def _get_docker():
    global _docker_client
    if _docker_client is None:
        import docker
        _docker_client = docker.from_env()
    return _docker_client


def _check_docker() -> bool:
    try:
        docker_client = _get_docker()
        docker_client.ping()
        return True
    except Exception:
        return False


def _validate_image_tag(image_tag: str) -> None:
    """Only allow pre-built hfusionhub-plugin-* images."""
    if not image_tag.startswith(IMAGE_ALLOWLIST_PREFIX):
        raise HTTPException(
            status_code=403,
            detail=f"Image tag must start with '{IMAGE_ALLOWLIST_PREFIX}', got: {image_tag}"
        )
    if not re.match(r'^hfusionhub-plugin-[a-zA-Z0-9_-]+:[a-zA-Z0-9._-]+$', image_tag):
        raise HTTPException(status_code=400, detail=f"Invalid image tag format: {image_tag}")


def _normalize_image_digest(raw: Optional[str]) -> Optional[str]:
    """Extract and validate a canonical sha256:<64 hex> digest.

    Accepts either a bare digest ('sha256:<64 hex>') or a repository-qualified
    digest ('repo:tag@sha256:<64 hex>', e.g. from Docker RepoDigests). Returns
    the normalized 'sha256:<64 hex>' string, or None when no complete,
    well-formed digest is present. Short prefixes or malformed strings are
    rejected (never accepted via substring matching).
    """
    if not raw:
        return None
    text = raw.strip().lower()
    if "@" in text:
        text = text.rsplit("@", 1)[1]
    m = re.fullmatch(r"sha256:[0-9a-f]{64}", text)
    return m.group(0) if m else None


def _is_ip_or_cidr(value: str) -> bool:
    """True when value is already an IP address or CIDR block.

    IP literals must be enforced directly — `dig +short <ip>` returns nothing
    for a bare address (no PTR path guaranteed), so hostname-based resolution
    would silently skip the rule.
    """
    if not value:
        return False
    try:
        ipaddress.ip_network(value, strict=False)
        return True
    except ValueError:
        return False


_HOSTNAME_RE = re.compile(
    r"(?=.{1,253}\Z)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*"
    r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.?\Z"
)


def _normalize_network_target(value: str) -> str:
    """Validate a network-policy target before it is interpolated into sh.

    Targets come from plugin configuration and later appear in a `dig` command.
    Only hostnames, IP literals, and CIDR blocks are accepted, so an untrusted
    value cannot alter the generated shell program.
    """
    target = value.strip()
    if not target:
        raise HTTPException(status_code=400, detail="Network policy target must not be empty")
    if _is_ip_or_cidr(target):
        return target
    if not _HOSTNAME_RE.fullmatch(target):
        raise HTTPException(status_code=400, detail=f"Invalid network policy target: {value!r}")
    return target.rstrip(".").lower()


def _net_rule(target: str, jump: str) -> str:
    """Emit one iptables OUTPUT rule for an IP literal/CIDR or hostname.

    IP/CIDR targets are enforced directly. Hostnames are resolved at runtime
    via `dig +short` (iptables cannot resolve names itself); unresolvable
    names produce no rule without aborting the entrypoint.
    """
    if _is_ip_or_cidr(target):
        return f"iptables -A OUTPUT -d {target} -j {jump}"
    return f"for ip in $(dig +short {target} 2>/dev/null); do iptables -A OUTPUT -d $ip -j {jump}; done"


def _build_network_commands(config: ContainerConfig) -> List[str]:
    """Build iptables commands to enforce network policies inside the container.

    Domain-based rules are resolved to IPs first (dig +short) because iptables
    cannot resolve hostnames itself, and unresolvable domains must not abort
    the whole entrypoint. IP/CIDR literals are enforced directly.
    """
    commands = []

    # Drop metadata endpoints always (resolve to IPs first)
    for domain in GLOBAL_BLOCKED_DOMAINS:
        if domain.startswith("*."):
            domain = domain[2:]
        commands.append(_net_rule(_normalize_network_target(domain), "DROP"))

    # If allowed_domains is set, block everything except those domains
    if config.allowed_domains:
        # Allow loopback
        commands.append("iptables -A OUTPUT -d 127.0.0.0/8 -j ACCEPT")
        # Allow DNS
        commands.append("iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT")
        commands.append("iptables -A OUTPUT -p udp --dport 53 -j ACCEPT")
        # Allow each allowed domain (resolve at runtime)
        for domain in config.allowed_domains:
            if domain.startswith("*."):
                domain = domain[2:]
            commands.append(_net_rule(_normalize_network_target(domain), "ACCEPT"))
        # Default policy: drop all other OUTPUT
        commands.append("iptables -A OUTPUT -j DROP")

    # If blocked_domains is set, drop those specifically
    if config.blocked_domains:
        for domain in config.blocked_domains:
            if domain.startswith("*."):
                domain = domain[2:]
            commands.append(_net_rule(_normalize_network_target(domain), "DROP"))

    return commands


# ── Endpoints ────────────────────────────────────────────────────────

@app.get("/health")
async def health(response: Response):
    docker_ok = _check_docker()
    images_count = 0
    if docker_ok:
        try:
            docker_client = _get_docker()
            images = docker_client.images.list(IMAGE_ALLOWLIST_GLOB)
            images_count = len(images)
        except Exception:
            pass
    reason = ""
    if not docker_ok:
        # A process that cannot reach its dedicated Docker Engine cannot
        # execute plugins. Report it as not ready so orchestrators do not
        # route work to a fail-closed runner that is effectively unavailable.
        response.status_code = 503
        reason = (
            "DOCKER_UNREACHABLE: cannot reach the TLS Docker Engine. In local "
            "dev (no TLS Docker Engine) this is expected — Python AI executes "
            "plugins in subprocess mode instead; container-mode plugins remain "
            "fail-closed."
        )

    return HealthResponse(
        status="healthy" if docker_ok else "unavailable",
        docker_connected=docker_ok,
        images_count=images_count,
        reason=reason,
    )


@app.post("/execute", response_model=ExecuteResponse)
async def execute_tool(
    req: ExecuteRequest,
    x_runner_token: Optional[str] = Header(None),
):
    _verify_token(x_runner_token)
    _validate_image_tag(req.image_tag)

    start_time = time.monotonic()
    docker_client = _get_docker()
    container = None

    try:
        # Validate digest FIRST — before any Docker operation
        expected_digest = _normalize_image_digest(req.image_digest)
        if expected_digest is None:
            raise HTTPException(
                status_code=400,
                detail="image_digest is required and must be a full sha256:<64 hex> digest"
            )

        # Docker SDK 调用是同步阻塞的；本处理器是 async —— 全部卸载到
        # 线程（第十五轮 P0-7），否则一个插件执行会冻结整个事件循环，
        # 串行化 runner 的所有请求。
        # Resolve image: try local first, then pull from registry
        try:
            pulled_image = await asyncio.to_thread(docker_client.images.get, req.image_tag)
            logger.info("Using local image: %s", req.image_tag)
        except Exception:
            logger.info("Pulling image: %s", req.image_tag)
            pulled_image = await asyncio.to_thread(docker_client.images.pull, req.image_tag)

        # Verify digest against actual image via constant-time comparison.
        # Prefer the registry RepoDigest (manifest digest); fall back to the
        # image Id (config digest) for locally-built images that were never
        # pushed. Both are normalized to sha256:<64 hex> before comparing.
        actual_digest = None
        for repo_digest in pulled_image.attrs.get("RepoDigests", []):
            candidate = _normalize_image_digest(repo_digest)
            if candidate is not None:
                actual_digest = candidate
                break
        if actual_digest is None:
            actual_digest = _normalize_image_digest(pulled_image.attrs.get("Id"))

        if actual_digest is None:
            raise HTTPException(
                status_code=400,
                detail=f"Image has no valid digest to verify against: RepoDigests={pulled_image.attrs.get('RepoDigests', [])}, Id={pulled_image.attrs.get('Id')}"
            )
        if not hmac.compare_digest(actual_digest, expected_digest):
            raise HTTPException(
                status_code=400,
                detail=f"Image digest mismatch: expected {expected_digest}, got {actual_digest}"
            )
        logger.info("Image digest verified via constant-time compare: %s", expected_digest)

        # Build network policy commands
        network_commands = _build_network_commands(req.config)

        # Prepare entrypoint that enforces network policy THEN invokes the fixed
        # plugin entry point. Tool name + JSON input are passed via env vars.
        script_lines = ["#!/bin/sh", "set -e"]
        for cmd in network_commands:
            script_lines.append(cmd)
        script_lines.append(
            '[ -f /opt/plugin/run_tool.py ] || { echo "missing /opt/plugin/run_tool.py"; exit 2; }'
        )
        script_lines.append("python /opt/plugin/run_tool.py")
        entrypoint_script = "\n".join(script_lines)

        # Resolve the network: use the configured isolated network if it
        # exists; otherwise fall back to the default bridge. The network-policy
        # enforcement itself happens INSIDE the container via iptables OUTPUT
        # rules, so connectivity isolation does not depend on a custom network.
        network_name = req.config.network
        try:
            await asyncio.to_thread(docker_client.networks.get, network_name)
        except Exception:
            logger.warning(
                "Network '%s' not found — falling back to default bridge", network_name
            )
            network_name = None

        container = await asyncio.to_thread(
            docker_client.containers.run,
            image=pulled_image.id,
            detach=True,
            network=network_name,
            mem_limit=req.config.memory_limit,
            cpu_quota=int(req.config.cpu_limit * 100000),
            cpu_period=100000,
            pids_limit=req.config.pids_limit,
            read_only=req.config.read_only_rootfs,
            tmpfs={"/tmp": f"size={req.config.tmpfs_size}"} if req.config.read_only_rootfs else {},
            environment={
                "PLUGIN_TOOL_NAME": req.tool_name,
                "PLUGIN_TOOL_INPUT": json.dumps(req.tool_input),
            },
            network_disabled=False,
            cap_drop=["ALL"],
            cap_add=["NET_ADMIN", "NET_RAW"],
            command=["/bin/sh", "-c", entrypoint_script],
            security_opt=["no-new-privileges:true"],
            labels={
                "com.hfusionhub.plugin": "true",
                "com.hfusionhub.plugin_id": req.plugin_id or "unknown",
            },
        )

        deadline = time.monotonic() + req.config.timeout
        while True:
            try:
                await asyncio.to_thread(container.reload)
                state = container.attrs.get("State", {})
                if state.get("Status") in {"exited", "dead"}:
                    break
            except Exception as e:
                logger.warning("Failed to inspect plugin container state: %s", e)
                break

            if time.monotonic() >= deadline:
                try:
                    await asyncio.to_thread(container.kill)
                except Exception as e:
                    logger.warning("Failed to kill timed out plugin container: %s", e)
                try:
                    await asyncio.to_thread(container.wait, timeout=5)
                except Exception:
                    pass
                try:
                    container.remove(force=True)
                except Exception:
                    pass
                elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)
                return ExecuteResponse(
                    success=False,
                    error=f"Container timeout after {req.config.timeout}s",
                    error_code="container_timeout",
                    duration_ms=elapsed_ms,
                    container_id=container.short_id,
                )

            await asyncio.sleep(0.2)

        try:
            result = await asyncio.to_thread(container.wait, timeout=5)
            exit_code = result.get("StatusCode", -1)
        except Exception as e:
            try:
                container.kill()
            except Exception:
                pass
            elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)
            return ExecuteResponse(
                success=False,
                error=f"Container wait failed: {e}",
                error_code="container_wait_failed",
                duration_ms=elapsed_ms,
                container_id=container.short_id,
            )

        def _read_logs():
            return (
                container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace"),
                container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace"),
            )

        logs, stderr = await asyncio.to_thread(_read_logs)
        elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)

        def _read_stats():
            return container.stats(stream=False)

        resource_usage = {}
        try:
            stats = await asyncio.to_thread(_read_stats)
            cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - \
                        stats["precpu_stats"]["cpu_usage"]["total_usage"]
            system_delta = stats["cpu_stats"]["system_cpu_usage"] - \
                          stats["precpu_stats"]["system_cpu_usage"]
            num_cpus = stats["cpu_stats"]["online_cpus"]
            cpu_percent = (cpu_delta / system_delta * num_cpus * 100.0) if system_delta > 0 else 0.0
            mem_usage = stats["memory_stats"].get("usage", 0)
            resource_usage = {
                "cpu_percent": round(cpu_percent, 2),
                "memory_bytes": mem_usage,
            }
        except Exception:
            pass

        # Report the ACTUAL resource limits enforced on the container so tests
        # (and audits) can verify Memory/NanoCpus/PidsLimit/read-only rootfs.
        resource_limits = {}
        try:
            hc = container.attrs.get("HostConfig", {})
            resource_limits = {
                "memory_bytes": hc.get("Memory"),
                "nano_cpus": hc.get("NanoCpus"),
                "cpu_quota": hc.get("CpuQuota"),
                "cpu_period": hc.get("CpuPeriod"),
                "pids_limit": hc.get("PidsLimit"),
                "read_only_rootfs": hc.get("ReadonlyRootfs"),
                "cap_drop": hc.get("CapDrop"),
                "security_opt": hc.get("SecurityOpt"),
                "tmpfs": list((hc.get("Tmpfs") or {}).keys()),
            }
        except Exception as e:
            logger.warning("Failed to read container resource limits: %s", e)

        if exit_code != 0:
            return ExecuteResponse(
                success=False,
                error=stderr or f"Container exited with code {exit_code}",
                error_code="container_error",
                duration_ms=elapsed_ms,
                resource_usage=resource_usage,
                resource_limits=resource_limits,
                container_id=container.short_id,
            )

        # The fixed entry point (run_tool.py) emits a single JSON object:
        # {"success": bool, "data": ..., "error": ...}. Unwrap it so the
        # plugin's actual tool result lands in ExecuteResponse.data.
        #
        # Fail-closed 解析（第十五轮 P0-7）：容器正常退出但最后一行不是可解析
        # 的契约 JSON 时，一律按失败上报——旧实现对这种输出报告 success=True
        # 并把原文塞进 raw_output，会让调用方把不可信输出当成功结果。
        logs_stripped = logs.strip()
        tool_result = None
        if logs_stripped:
            try:
                tool_result = json.loads(logs_stripped.split("\n")[-1])
            except (json.JSONDecodeError, IndexError):
                tool_result = None

        if isinstance(tool_result, dict) and "success" in tool_result:
            tool_success = bool(tool_result.get("success"))
            tool_error = tool_result.get("error")
            tool_data = tool_result.get("data")
            return ExecuteResponse(
                success=tool_success,
                data=tool_data,
                error=tool_error if not tool_success else None,
                error_code="plugin_execution_error" if not tool_success else None,
                duration_ms=elapsed_ms,
                resource_usage=resource_usage,
                resource_limits=resource_limits,
                container_id=container.short_id,
            )

        return ExecuteResponse(
            success=False,
            error=(
                (logs_stripped[-2000:] if logs_stripped else "容器未输出任何结果")
                + " （输出不符合插件契约 JSON：{\"success\": ...}）"
            ),
            error_code="tool_output_unparseable",
            duration_ms=elapsed_ms,
            resource_usage=resource_usage,
            resource_limits=resource_limits,
            container_id=container.short_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)
        logger.exception("Container execution failed")
        return ExecuteResponse(
            success=False,
            error=str(e),
            error_code="execution_error",
            duration_ms=elapsed_ms,
            container_id=container.short_id if container else None,
        )
    finally:
        if container:
            try:
                await asyncio.to_thread(container.remove, force=True)
            except Exception:
                pass


@app.get("/images")
async def list_images(x_runner_token: Optional[str] = Header(None)):
    _verify_token(x_runner_token)
    docker_client = _get_docker()
    images = docker_client.images.list(IMAGE_ALLOWLIST_GLOB)
    return {
        "images": [
            {
                "tag": tag,
                "id": img.short_id,
                "size": img.attrs.get("Size", 0),
                "created": img.attrs.get("Created", ""),
            }
            for img in images
            for tag in img.tags
            if tag.startswith(IMAGE_ALLOWLIST_PREFIX)
        ],
        "total": len(images),
    }


@app.delete("/images/{image_tag:path}")
async def remove_image(image_tag: str, x_runner_token: Optional[str] = Header(None)):
    _verify_token(x_runner_token)
    _validate_image_tag(image_tag)
    docker_client = _get_docker()
    try:
        docker_client.images.remove(image_tag, force=True)
        return {"status": "removed", "image_tag": image_tag}
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Image not found: {e}")


if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host="0.0.0.0", port=9100)
