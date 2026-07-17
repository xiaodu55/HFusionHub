"""
MCP Client 管理 API — 注册/查看/移除外部 MCP 服务器（B5）。

前端通过 Java 透传访问（带 X-Internal-Token）；运行时修改会持久化到
``MCP_SERVERS_CONFIG_FILE``（默认 mcp_servers.json），重启后保留。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from app.core.tools.mcp_client import (
    get_mcp_client_manager,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mcp", tags=["mcp-admin"])


def _server_payload(conn) -> dict[str, Any]:
    return {
        "id": conn.server_id,
        "name": conn.name,
        "url": conn.url,
        "transport": conn.transport.value,
        "status": conn.status.value,
        "tool_count": len(conn.tools),
        "error_message": conn.error_message or None,
    }


@router.get("/servers")
async def list_servers() -> dict[str, Any]:
    manager = get_mcp_client_manager()
    return {"servers": [_server_payload(c) for c in manager.list_servers()]}


@router.post("/servers")
async def add_server(payload: dict[str, Any]) -> dict[str, Any]:
    server_id = str(payload.get("id") or "").strip()
    url = str(payload.get("url") or "").strip()
    if not server_id or not url:
        return {"success": False, "message": "id 与 url 不能为空"}
    if not url.startswith(("http://", "https://")):
        return {"success": False, "message": "url 必须是 http(s) 地址"}

    transport = str(payload.get("transport") or "sse").strip().lower()
    if transport not in ("sse", "streamable-http"):
        return {"success": False, "message": "transport 仅支持 sse / streamable-http"}

    manager = get_mcp_client_manager()
    conn = manager.add_server({
        "id": server_id,
        "name": str(payload.get("name") or server_id),
        "url": url,
        "transport": transport,
        "api_key": str(payload.get("api_key") or "").strip() or None,
    })
    ok = await manager.connect(server_id)
    return {
        "success": ok,
        "message": f"MCP 服务器 '{conn.name}' 连接{'成功' if ok else '失败'}",
        "server": _server_payload(conn),
    }


@router.post("/servers/{server_id}/reconnect")
async def reconnect(server_id: str) -> dict[str, Any]:
    manager = get_mcp_client_manager()
    conn = manager.get_server(server_id)
    if conn is None:
        return {"success": False, "message": f"服务器 {server_id} 不存在"}
    ok = await manager.connect(server_id)
    return {
        "success": ok,
        "message": f"MCP 服务器 '{conn.name}' 重新连接{'成功' if ok else '失败'}",
        "server": _server_payload(conn),
    }


@router.delete("/servers/{server_id}")
async def remove_server(server_id: str) -> dict[str, Any]:
    manager = get_mcp_client_manager()
    await manager.disconnect(server_id)
    removed = manager.remove_server(server_id)
    return {"success": removed, "message": "已移除" if removed else f"服务器 {server_id} 不存在"}
