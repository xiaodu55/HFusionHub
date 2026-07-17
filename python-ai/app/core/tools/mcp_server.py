"""
MCP (Model Context Protocol) Server — JSON-RPC 2.0 over SSE transport.

Exposes HFusionHub tools (search_knowledge_base, calculate, get_current_time)
via the standard MCP protocol so external AI clients (Claude Desktop, MCP Inspector,
etc.) can discover and invoke them.

Implements the minimal MCP lifecycle:
  1. Client sends initialize request
  2. Server responds with capabilities
  3. Client sends notifications/initialized
  4. Client calls tools/list and tools/call
"""

from __future__ import annotations

import logging
from typing import Any

from . import ToolExecutionPolicy, execute_tool, get_tools

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP JSON-RPC types
# ---------------------------------------------------------------------------

JSONRPC_VERSION = "2.0"
PROTOCOL_VERSION = "2024-11-05"

# Tool definitions in MCP schema format
_MCP_TOOL_SCHEMAS: list[dict[str, Any]] = []

# MCP is an external/public discovery surface.  High-risk tools such as
# write_note are deliberately available only through the authenticated Agent
# approval flow and must never appear in an MCP tools/list response.
MCP_PUBLIC_TOOL_NAMES = {
    "search_knowledge_base", "read_chunk", "list_document_chunks",
    "calculate", "get_current_time", "web_search",
}


def _build_tool_schemas() -> list[dict[str, Any]]:
    """Build MCP-compliant tool schemas from registered tools."""
    raw_tools = [
        tool for tool in get_tools(v1_only=False)
        if tool["name"] in MCP_PUBLIC_TOOL_NAMES
    ]
    schemas = []
    for tool in raw_tools:
        params = tool.get("parameters", {})
        properties: dict[str, Any] = {}
        required: list[str] = []

        for param_name, param_def in params.items():
            prop: dict[str, Any] = {"type": param_def.get("type", "string")}
            if "description" in param_def:
                prop["description"] = param_def["description"]
            if "default" in param_def:
                prop["default"] = param_def["default"]
            properties[param_name] = prop
            # All parameters are required unless marked optional
            if not param_def.get("optional", False):
                required.append(param_name)

        input_schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            input_schema["required"] = required

        schemas.append({
            "name": tool["name"],
            "description": tool.get("description", ""),
            "inputSchema": input_schema,
        })

    return schemas


def get_mcp_tool_schemas() -> list[dict[str, Any]]:
    """Get (possibly cached) MCP tool schemas."""
    global _MCP_TOOL_SCHEMAS
    if not _MCP_TOOL_SCHEMAS:
        _MCP_TOOL_SCHEMAS = _build_tool_schemas()
    return _MCP_TOOL_SCHEMAS


# ---------------------------------------------------------------------------
# JSON-RPC message helpers
# ---------------------------------------------------------------------------

def _jsonrpc_response(id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": id, "result": result}


def _jsonrpc_error(id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": JSONRPC_VERSION, "id": id, "error": err}


# MCP-specific error codes
ERROR_PARSE = -32700
ERROR_INVALID_REQUEST = -32600
ERROR_METHOD_NOT_FOUND = -32601
ERROR_INVALID_PARAMS = -32602
ERROR_INTERNAL = -32603


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

async def handle_mcp_request(
    method: str,
    params: dict[str, Any] | None,
    request_id: Any,
    knowledge_base_id: int | None = None,
) -> dict[str, Any]:
    """Route a single MCP JSON-RPC request and return the response dict."""

    # === Lifecycle ===
    if method == "initialize":
        return _jsonrpc_response(request_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {
                "tools": {},
            },
            "serverInfo": {
                "name": "HFusionHub MCP Server",
                "version": "0.1.0",
            },
        })

    if method == "notifications/initialized":
        # No response for notifications in JSON-RPC
        return {}  # caller should skip sending this

    # === Tool discovery ===
    if method == "tools/list":
        return _jsonrpc_response(request_id, {
            "tools": get_mcp_tool_schemas(),
        })

    # === Tool invocation ===
    if method == "tools/call":
        if not params or "name" not in params:
            return _jsonrpc_error(request_id, ERROR_INVALID_PARAMS, "Missing tool name")
        tool_name = params["name"]
        arguments = params.get("arguments", {})

        # Build safe execution policy — Agent V1 tools + legacy tools.
        policy = ToolExecutionPolicy(
            allowed_names={
                "search_knowledge_base", "read_chunk", "list_document_chunks",
                "calculate", "get_current_time", "web_search",
            },
            knowledge_base_id=knowledge_base_id,
            timeout_seconds=30.0,
            max_search_results=10,
            max_input_characters=1024,
        )

        raw_tools = get_tools(knowledge_base_id=knowledge_base_id, v1_only=False)

        try:
            result_text = await execute_tool(tool_name, arguments, raw_tools, policy=policy)
        except Exception as exc:
            logger.exception("MCP tool call failed: %s", tool_name)
            return _jsonrpc_error(request_id, ERROR_INTERNAL, f"Tool execution failed: {exc}")

        return _jsonrpc_response(request_id, {
            "content": [
                {"type": "text", "text": result_text}
            ],
        })

    # === Unknown method ===
    if method.startswith("notifications/"):
        # Silently acknowledge notifications per JSON-RPC spec
        return {}

    return _jsonrpc_error(request_id, ERROR_METHOD_NOT_FOUND, f"Unknown method: {method}")


# ---------------------------------------------------------------------------
# SSE transport helpers
# ---------------------------------------------------------------------------

async def mcp_sse_endpoint(
    body: dict[str, Any],
    knowledge_base_id: int | None = None,
) -> dict[str, Any] | None:
    """Process a single MCP JSON-RPC message received via HTTP POST.

    Returns the JSON-RPC response dict, or None for notifications.
    """
    jsonrpc = body.get("jsonrpc")
    if jsonrpc != JSONRPC_VERSION:
        return _jsonrpc_error(body.get("id"), ERROR_INVALID_REQUEST, "Invalid JSON-RPC version")

    method = body.get("method")
    if not method:
        return _jsonrpc_error(body.get("id"), ERROR_INVALID_REQUEST, "Missing method")

    request_id = body.get("id")
    params = body.get("params")

    response = await handle_mcp_request(method, params, request_id, knowledge_base_id)

    # Notifications have no id → no response
    if request_id is None:
        return None

    return response
