"""
工具中心 API — 向 Java 后端暴露完整的 Tool Registry 元数据。

所有端点均需 X-Internal-Token；前端通过 Java 透传访问，不直连 Python。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api.internal_auth import require_internal_token
from app.core.tools.registry import create_full_registry
from app.core.tools.spec import RiskLevel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tools", tags=["tools"])

# ── Risk level display helpers ──────────────────────────────────────────

_RISK_LABELS: dict[str, str] = {
    RiskLevel.READ_ONLY: "只读",
    RiskLevel.READ_WRITE: "读写",
    "external": "外部调用",
}

_AGENT_VERSION_LABELS: dict[str, str] = {
    "1.0": "active",        # V1 默认可用
    "1.1": "beta",          # 需审批开启
    "0.0": "experimental",  # 仅 MCP / 开发中
}


def _tool_status(agent_version: str) -> str:
    """Derive a human-readable status from agent_version gating."""
    return _AGENT_VERSION_LABELS.get(agent_version, "unknown")


def _build_tool_entry(spec, instance) -> dict[str, Any]:
    """Serialize one ToolSpec into the frontend-facing shape."""
    return {
        "name": spec.name,
        "description": spec.description,
        "risk_level": spec.risk_level,
        "risk_label": _RISK_LABELS.get(spec.risk_level, spec.risk_level),
        "timeout_seconds": spec.timeout_seconds,
        "required_permissions": list(spec.required_permissions),
        "agent_version": spec.agent_version,
        "status": _tool_status(spec.agent_version),
        "input_schema": {
            "properties": spec.input_schema.get("properties", {}),
            "required": spec.input_schema.get("required", []),
        },
        "display_name": getattr(spec, "_display_name", None),
        "example": getattr(spec, "_example", None),
        "plugin_name": getattr(spec, "_plugin_name", None),
        "category": getattr(spec, "_category", None),
    }


@router.get("/registry", dependencies=[Depends(require_internal_token)])
async def tool_registry(tenant_id: int | None = Query(default=None, ge=1)) -> dict[str, Any]:
    """返回 Tool Registry 中所有已注册工具的元数据。

    不依赖 knowledge_base_id——仅列出工具的声明式元数据（名称、用途、
    风险等级、权限要求、超时、版本门控），不做实际调用。

    前端通过 Java 的 ``/api/tools`` 透传访问此端点。
    """
    try:
        registry = create_full_registry(knowledge_base_id=None, tenant_id=tenant_id)
    except Exception as exc:
        logger.exception("Failed to create tool registry for listing")
        return {
            "tools": [],
            "total": 0,
            "error": f"无法加载工具注册表: {exc}",
        }

    tools: list[dict[str, Any]] = []
    for name, spec in registry._specs.items():
        instance = registry._instances.get(name)
        try:
            tools.append(_build_tool_entry(spec, instance))
        except Exception:
            logger.exception("Failed to serialize tool spec for %s", name)

    # Sort: active V1 tools first, then beta, then experimental
    _order = {"active": 0, "beta": 1, "experimental": 2}
    tools.sort(key=lambda t: (_order.get(t["status"], 99), t["name"]))

    return {
        "tools": tools,
        "total": len(tools),
    }
