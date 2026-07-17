"""
MCP (Model Context Protocol) API endpoints — JSON-RPC 2.0 over HTTP.

Security boundary:
  - initialize / tools/list — public (protocol handshake, schema discovery)
  - tools/call              — requires X-Internal-Token (same as other Python routes)
  - search_knowledge_base   — additionally requires X-HFusionHub-KB-ID header

Connect with MCP Inspector:
  npx @anthropic-ai/mcp-inspector http://localhost:9000/mcp
  (add X-Internal-Token and X-HFusionHub-KB-ID headers for tool execution)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..core.tools.mcp_server import get_mcp_tool_schemas, mcp_sse_endpoint

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])

# Methods that do not require authentication
_PUBLIC_METHODS = {"initialize", "notifications/initialized", "tools/list"}


class MCPRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: dict[str, Any] | None = None
    id: int | str | None = None


def _extract_kb_id(http_request: Request) -> int | None:
    """Extract knowledge_base_id from X-HFusionHub-KB-ID header."""
    kb_header = http_request.headers.get("X-HFusionHub-KB-ID")
    if kb_header:
        try:
            return int(kb_header)
        except (TypeError, ValueError):
            pass
    return None


@router.post("")
async def mcp_handler(request: MCPRequest, http_request: Request):
    """
    MCP JSON-RPC 2.0 endpoint.

    Public methods (no auth):
      - initialize, notifications/initialized, tools/list

    Authenticated methods (require X-Internal-Token header):
      - tools/call
    """
    method = request.method
    body = request.model_dump(exclude_none=True)

    # --- Auth check for non-public methods ---
    if method not in _PUBLIC_METHODS:
        token = http_request.headers.get("X-Internal-Token")
        if not token:
            raise HTTPException(status_code=401, detail="X-Internal-Token header required for tool execution")
        import hmac as _hmac

        from app.utils.config import config
        expected = config.INTERNAL_API_TOKEN
        if not expected or not _hmac.compare_digest(token, expected):
            raise HTTPException(status_code=403, detail="Invalid internal token")

    # --- KB ID extraction (for search_knowledge_base) ---
    knowledge_base_id = _extract_kb_id(http_request)
    if method == "tools/call" and request.params:
        tool_name = request.params.get("name", "")
        if tool_name == "search_knowledge_base" and knowledge_base_id is None:
            raise HTTPException(
                status_code=400,
                detail="X-HFusionHub-KB-ID header required for search_knowledge_base tool"
            )

    try:
        result = await mcp_sse_endpoint(body, knowledge_base_id=knowledge_base_id)
    except Exception as exc:
        logger.exception("MCP request failed")
        raise HTTPException(status_code=500, detail=f"MCP error: {exc}")

    if result is None:
        return {"jsonrpc": "2.0", "result": None}

    return result


@router.get("/health")
async def mcp_health():
    """Health check for MCP endpoint (public)."""
    tools = get_mcp_tool_schemas()
    return {
        "status": "healthy",
        "protocol": "json-rpc-2.0",
        "tool_count": len(tools),
        "tools": [t["name"] for t in tools],
    }


@router.get("/tools")
async def mcp_list_tools():
    """List available MCP tools — schemas only, no data access (public)."""
    return {
        "tools": get_mcp_tool_schemas(),
    }
