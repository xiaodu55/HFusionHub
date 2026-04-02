"""Plugin admin API — internal endpoints for Python AI service.

Protected by X-Internal-Token.  Handles plugin install, enable, disable,
uninstall, and manifest verification from the Java backend.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.core.plugin.registry import (
    list_plugins,
    list_all_tool_specs,
    get_plugin,
    enable_plugin,
    disable_plugin,
    load_and_register_wheel,
    unregister_plugin,
    verify_manifest_integrity,
    clear_registry,
)
from app.core.plugin.audit import (
    record_install,
    record_enable,
    record_disable,
    record_uninstall,
    get_audit_log,
)
from app.core.plugin.loader import PluginLoadError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/plugin", tags=["Plugin Admin"])


# ── Request/Response models ──────────────────────────────────────────

class PluginInstallRequest(BaseModel):
    wheel_path: str
    plugin_id: Optional[str] = None
    expected_hash: str  # Mandatory SHA-256 hash of the wheel archive
    operator_id: Optional[int] = None


class PluginActionRequest(BaseModel):
    plugin_id: str
    reason: Optional[str] = None
    operator_id: Optional[int] = None


class PluginInfo(BaseModel):
    plugin_id: str
    name: str
    version: str
    manifest_hash: str
    enabled: bool
    tool_count: int


class PluginListResponse(BaseModel):
    plugins: List[PluginInfo]
    total: int


# ── Auth helper ──────────────────────────────────────────────────────

def _verify_internal_token(x_internal_token: Optional[str] = Header(None)) -> None:
    """Verify the X-Internal-Token header matches the configured token."""
    import os
    expected = os.environ.get("HFUSIONHUB_INTERNAL_TOKEN", "")
    if not expected or x_internal_token != expected:
        raise HTTPException(status_code=403, detail="Forbidden: invalid X-Internal-Token")


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/list", response_model=PluginListResponse)
async def list_installed_plugins(
    x_internal_token: Optional[str] = Header(None),
) -> PluginListResponse:
    """List all registered plugins."""
    _verify_internal_token(x_internal_token)

    plugins = list_plugins(enabled_only=False)
    items = [
        PluginInfo(
            plugin_id=p.plugin_id,
            name=p.name,
            version=p.version,
            manifest_hash=p.manifest_hash,
            enabled=p.enabled,
            tool_count=len(p.tool_specs),
        )
        for p in plugins
    ]
    return PluginListResponse(plugins=items, total=len(items))


@router.get("/tool-specs")
async def get_all_plugin_tool_specs(
    x_internal_token: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Get all plugin tool specs (for ToolRegistry integration)."""
    _verify_internal_token(x_internal_token)

    specs = list_all_tool_specs(enabled_only=True)
    return {"tool_specs": specs, "total": len(specs)}


@router.post("/install")
async def install_plugin(
    req: PluginInstallRequest,
    x_internal_token: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Install a plugin from a wheel file."""
    _verify_internal_token(x_internal_token)

    try:
        registered = load_and_register_wheel(
            wheel_path=req.wheel_path,
            plugin_id=req.plugin_id,
            expected_hash=req.expected_hash,
        )
        record_install(
            plugin_id=registered.plugin_id,
            plugin_name=registered.name,
            manifest_hash=registered.manifest_hash,
            operator_id=req.operator_id,
        )
        return {
            "status": "installed",
            "plugin_id": registered.plugin_id,
            "name": registered.name,
            "version": registered.version,
            "tool_count": len(registered.tool_specs),
        }
    except PluginLoadError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("插件安装失败")
        raise HTTPException(status_code=500, detail=f"插件安装失败: {e}")


@router.post("/enable")
async def enable(
    req: PluginActionRequest,
    x_internal_token: Optional[str] = Header(None),
) -> Dict[str, str]:
    """Enable a plugin."""
    _verify_internal_token(x_internal_token)

    plugin = get_plugin(req.plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail="插件不存在")

    if plugin.enabled:
        return {"status": "already_enabled", "plugin_id": req.plugin_id}

    enable_plugin(req.plugin_id)
    record_enable(
        plugin_id=req.plugin_id,
        plugin_name=plugin.name,
        operator_id=req.operator_id,
    )
    return {"status": "enabled", "plugin_id": req.plugin_id}


@router.post("/disable")
async def disable(
    req: PluginActionRequest,
    x_internal_token: Optional[str] = Header(None),
) -> Dict[str, str]:
    """Disable a plugin."""
    _verify_internal_token(x_internal_token)

    plugin = get_plugin(req.plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail="插件不存在")

    if not plugin.enabled:
        return {"status": "already_disabled", "plugin_id": req.plugin_id}

    disable_plugin(req.plugin_id)
    record_disable(
        plugin_id=req.plugin_id,
        plugin_name=plugin.name,
        reason=req.reason,
        operator_id=req.operator_id,
    )
    return {"status": "disabled", "plugin_id": req.plugin_id}


@router.post("/uninstall")
async def uninstall(
    req: PluginActionRequest,
    x_internal_token: Optional[str] = Header(None),
) -> Dict[str, str]:
    """Uninstall a plugin."""
    _verify_internal_token(x_internal_token)

    plugin = get_plugin(req.plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail="插件不存在")

    record_uninstall(
        plugin_id=req.plugin_id,
        plugin_name=plugin.name,
        reason=req.reason,
        operator_id=req.operator_id,
    )
    unregister_plugin(req.plugin_id)
    return {"status": "uninstalled", "plugin_id": req.plugin_id}


@router.post("/verify")
async def verify_integrity(
    req: PluginActionRequest,
    x_internal_token: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Verify a plugin's manifest hash integrity."""
    _verify_internal_token(x_internal_token)

    plugin = get_plugin(req.plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail="插件不存在")

    # Re-compute hash from stored manifest
    from app.core.plugin.manifest import compute_manifest_hash
    current_hash = compute_manifest_hash(plugin.descriptor.manifest)
    is_valid = current_hash == plugin.manifest_hash

    return {
        "plugin_id": req.plugin_id,
        "valid": is_valid,
        "current_hash": current_hash,
        "stored_hash": plugin.manifest_hash,
    }


@router.get("/audit-logs")
async def audit_logs(
    plugin_id: Optional[str] = None,
    limit: int = 50,
    x_internal_token: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Get plugin audit log entries."""
    _verify_internal_token(x_internal_token)

    entries = get_audit_log(plugin_id=plugin_id, limit=limit)
    return {
        "entries": [e.to_dict() for e in entries],
        "total": len(entries),
    }
