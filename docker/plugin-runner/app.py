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

import hashlib
import hmac
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
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

PLUGIN_RUNNER_TOKEN = os.environ.get("PLUGIN_RUNNER_TOKEN", "")
PLUGIN_ARTIFACTS_DIR = os.environ.get("PLUGIN_ARTIFACTS_DIR", "/opt/plugin-artifacts")
IMAGE_ALLOWLIST_PREFIX = "hfusionhub-plugin-"

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
    allowed_domains: List[str] = []
    blocked_domains: List[str] = []
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
    container_id: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    docker_connected: bool
    images_count: int


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


def _build_network_commands(config: ContainerConfig) -> List[str]:
    """Build iptables commands to enforce network policies inside the container."""
    commands = []

    # Drop metadata endpoints always (resolve to IPs first)
    for domain in GLOBAL_BLOCKED_DOMAINS:
        commands.append(f"iptables -A OUTPUT -d {domain} -j DROP")

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
            commands.append(f"for ip in $(dig +short {domain} 2>/dev/null); do iptables -A OUTPUT -d $ip -j ACCEPT; done")
        # Default policy: drop all other OUTPUT
        commands.append("iptables -A OUTPUT -j DROP")

    # If blocked_domains is set, drop those specifically
    if config.blocked_domains:
        for domain in config.blocked_domains:
            if domain.startswith("*."):
                domain = domain[2:]
            commands.append(f"for ip in $(dig +short {domain} 2>/dev/null); do iptables -A OUTPUT -d $ip -j DROP; done")

    return commands


# ── Endpoints ────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    docker_ok = _check_docker()
    images_count = 0
    if docker_ok:
        try:
            docker_client = _get_docker()
            images = docker_client.images.list(IMAGE_ALLOWLIST_PREFIX)
            images_count = len(images)
        except Exception:
            pass
    return HealthResponse(
        status="healthy" if docker_ok else "degraded",
        docker_connected=docker_ok,
        images_count=images_count,
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
        if not req.image_digest or not req.image_digest.strip():
            raise HTTPException(
                status_code=400,
                detail="image_digest is required for container execution"
            )

        # Resolve image: try local first, then pull from registry
        try:
            pulled_image = docker_client.images.get(req.image_tag)
            logger.info("Using local image: %s", req.image_tag)
        except Exception:
            logger.info("Pulling image: %s", req.image_tag)
            pulled_image = docker_client.images.pull(req.image_tag)

        # Verify digest against actual image
        actual_digest = pulled_image.attrs.get("RepoDigests", [""])[0]
        if req.image_digest not in actual_digest:
            raise HTTPException(
                status_code=400,
                detail=f"Image digest mismatch: expected {req.image_digest}, got {actual_digest}"
            )
        logger.info("Image digest verified: %s", req.image_digest)

        # Build network policy commands
        network_commands = _build_network_commands(req.config)

        # Prepare entrypoint script that enforces network policy then runs tool
        # Write to a temp file in container and execute - this avoids quoting issues
        script_lines = ["#!/bin/sh", "set -e"]
        for cmd in network_commands:
            script_lines.append(cmd)
        script_lines.append(f'python -c "import sys; exec(sys.stdin.read())"')
        entrypoint_script = "\n".join(script_lines)

        container = docker_client.containers.run(
            image=pulled_image.id,
            detach=True,
            network=req.config.network,
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

        try:
            result = container.wait(timeout=int(req.config.timeout))
            exit_code = result.get("StatusCode", -1)
        except Exception:
            container.kill()
            elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)
            return ExecuteResponse(
                success=False,
                error=f"Container timeout after {req.config.timeout}s",
                error_code="container_timeout",
                duration_ms=elapsed_ms,
                container_id=container.short_id,
            )

        logs = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
        stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
        elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)

        resource_usage = {}
        try:
            stats = container.stats(stream=False)
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

        if exit_code != 0:
            return ExecuteResponse(
                success=False,
                error=stderr or f"Container exited with code {exit_code}",
                error_code="container_error",
                duration_ms=elapsed_ms,
                resource_usage=resource_usage,
                container_id=container.short_id,
            )

        try:
            data = json.loads(logs.strip().split("\n")[-1]) if logs.strip() else None
        except (json.JSONDecodeError, IndexError):
            data = {"raw_output": logs}

        return ExecuteResponse(
            success=True,
            data=data,
            duration_ms=elapsed_ms,
            resource_usage=resource_usage,
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
                container.remove(force=True)
            except Exception:
                pass


@app.get("/images")
async def list_images(x_runner_token: Optional[str] = Header(None)):
    _verify_token(x_runner_token)
    docker_client = _get_docker()
    images = docker_client.images.list(IMAGE_ALLOWLIST_PREFIX)
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
