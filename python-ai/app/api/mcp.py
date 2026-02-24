"""
MCP (Model Context Protocol) API endpoints.

Provides JSON-RPC 2.0 over HTTP POST for MCP-compatible clients.
Connect with the MCP Inspector at http://localhost:9000/mcp
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from ..core.tools.mcp_server import mcp_sse_endpoint
from ..core.tools.mcp_server import get_mcp_tool_schemas

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])


class MCPRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Optional[Dict[str, Any]] = None
    id: Optional[int | str] = None


@router.post("")
async def mcp_handler(request: MCPRequest, http_request: Request):
    """
    MCP JSON-RPC 2.0 endpoint.

    Supports:
      - initialize          → protocol handshake
      - notifications/initialized → post-handshake notification
      - tools/list          → list available tools
      - tools/call          → execute a tool

    Connect with MCP Inspector: npx @anthropic-ai/mcp-inspector http://localhost:9000/mcp
    """
    # Extract optional knowledge_base_id from headers or query params
    knowledge_base_id: Optional[int] = None
    kb_header = http_request.headers.get("X-HFusionHub-KB-ID")
    if kb_header:
        try:
            knowledge_base_id = int(kb_header)
        except (TypeError, ValueError):
            pass

    body = request.model_dump(exclude_none=True)

    try:
        result = await mcp_sse_endpoint(body, knowledge_base_id=knowledge_base_id)
    except Exception as exc:
        logger.exception("MCP request failed")
        raise HTTPException(status_code=500, detail=f"MCP error: {exc}")

    if result is None:
        # Notification — return 202 with no body
        return {"jsonrpc": "2.0", "result": None}

    return result


@router.get("/health")
async def mcp_health():
    """Health check for MCP endpoint."""
    tools = get_mcp_tool_schemas()
    return {
        "status": "healthy",
        "protocol": "json-rpc-2.0",
        "tool_count": len(tools),
        "tools": [t["name"] for t in tools],
    }


@router.get("/tools")
async def mcp_list_tools():
    """Convenience endpoint: list available MCP tools (non-JSON-RPC)."""
    return {
        "tools": get_mcp_tool_schemas(),
    }
