"""Tests for the MCP client (external MCP server connection).

Covers the Streamable HTTP JSON-RPC handshake (initialize →
notifications/initialized → tools/list), SSE response parsing, session
id handling, auth-error surfacing, and ToolRegistry integration
(registration + execution routing).
"""

import json

import httpx
import pytest

from app.core.tools.mcp_client import (
    ConnectionStatus,
    MCPClientManager,
    MCPServerConnection,
    TransportType,
)


def _make_manager() -> MCPClientManager:
    return MCPClientManager()


def _connected_server(manager: MCPClientManager, server_id: str = "s1") -> MCPServerConnection:
    conn = MCPServerConnection(
        server_id=server_id,
        name="S1",
        url="http://mcp.test/mcp",
        transport=TransportType.STREAMABLE_HTTP,
    )
    manager._servers[server_id] = conn
    return conn


def _install_transport(manager: MCPClientManager, handler) -> None:
    manager._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _jsonrpc_result(payload, result):
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload.get("id"), "result": result})


class TestConnectHandshake:
    @pytest.mark.asyncio
    async def test_connect_performs_protocol_handshake_on_base_url(self):
        """initialize → notifications/initialized → tools/list, all to base URL."""
        calls = []

        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.read())
            calls.append({"url": str(request.url), "method": payload.get("method"), "id": payload.get("id")})
            method = payload.get("method")
            if method == "initialize":
                return _jsonrpc_result(payload, {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "t", "version": "1"},
                })
            if method == "notifications/initialized":
                return httpx.Response(202, content=b"", headers={"Content-Type": "application/json"})
            if method == "tools/list":
                return _jsonrpc_result(payload, {
                    "tools": [{"name": "hello", "description": "d", "inputSchema": {"type": "object"}}],
                })
            return httpx.Response(500, text="unexpected")

        manager = _make_manager()
        _connected_server(manager)
        _install_transport(manager, handler)

        ok = await manager.connect("s1")
        assert ok
        conn = manager.get_server("s1")
        assert conn.status == ConnectionStatus.CONNECTED
        assert conn.tools == [{"name": "hello", "description": "d", "inputSchema": {"type": "object"}}]
        # Every message hits the base URL — never a REST-style /tools/list path.
        assert [c["method"] for c in calls] == ["initialize", "notifications/initialized", "tools/list"]
        assert all(c["url"] == "http://mcp.test/mcp" for c in calls)
        assert calls[0]["id"] is not None  # initialize is a request, not a notification

    @pytest.mark.asyncio
    async def test_connect_parses_sse_response(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.read())
            method = payload.get("method")
            if method == "initialize":
                return _jsonrpc_result(payload, {
                    "protocolVersion": "2025-06-18", "capabilities": {}, "serverInfo": {"name": "t", "version": "1"},
                })
            if method == "notifications/initialized":
                return httpx.Response(202, content=b"", headers={"Content-Type": "application/json"})
            if method == "tools/list":
                body = (
                    'event: message\n'
                    f'data: {json.dumps({"jsonrpc": "2.0", "id": payload.get("id"), "result": {"tools": [{"name": "sse_tool", "description": "d", "inputSchema": {}}]}})}\n\n'
                )
                return httpx.Response(200, content=body.encode(), headers={"Content-Type": "text/event-stream"})
            return httpx.Response(500, text="unexpected")

        manager = _make_manager()
        _connected_server(manager)
        _install_transport(manager, handler)

        ok = await manager.connect("s1")
        assert ok
        assert manager.get_server("s1").tools[0]["name"] == "sse_tool"

    @pytest.mark.asyncio
    async def test_connect_echoes_session_id(self):
        seen_headers = []

        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.read())
            seen_headers.append(request.headers.get("mcp-session-id"))
            method = payload.get("method")
            if method == "initialize":
                return httpx.Response(
                    200,
                    headers={"Mcp-Session-Id": "sess-123", "Content-Type": "application/json"},
                    json={"jsonrpc": "2.0", "id": payload.get("id"), "result": {
                        "protocolVersion": "2025-06-18", "capabilities": {}, "serverInfo": {"name": "t", "version": "1"},
                    }},
                )
            if method == "notifications/initialized":
                return httpx.Response(202, content=b"", headers={"Content-Type": "application/json"})
            if method == "tools/list":
                return _jsonrpc_result(payload, {"tools": []})
            return httpx.Response(500, text="unexpected")

        manager = _make_manager()
        _connected_server(manager)
        _install_transport(manager, handler)

        await manager.connect("s1")
        # initialize has no session yet; the two follow-ups must echo it.
        assert seen_headers[0] is None
        assert seen_headers[1] == "sess-123"
        assert seen_headers[2] == "sess-123"


class TestAuthErrors:
    @pytest.mark.asyncio
    async def test_connect_reports_auth_error(self):
        """A 401 (e.g. Notion missing token) surfaces status ERROR + message."""

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                401,
                headers={"Content-Type": "application/json"},
                json={"error": "invalid_token", "error_description": "Missing or invalid access token"},
            )

        manager = _make_manager()
        _connected_server(manager)
        _install_transport(manager, handler)

        ok = await manager.connect("s1")
        assert not ok
        conn = manager.get_server("s1")
        assert conn.status == ConnectionStatus.ERROR
        assert "401" in conn.error_message
        assert conn.tools == []


class TestToolExecution:
    @pytest.mark.asyncio
    async def test_call_tool_sends_jsonrpc_and_normalises_text(self):
        seen = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.read())
            method = payload.get("method")
            if method == "initialize":
                return _jsonrpc_result(payload, {
                    "protocolVersion": "2025-06-18", "capabilities": {}, "serverInfo": {"name": "t", "version": "1"},
                })
            if method == "notifications/initialized":
                return httpx.Response(202, content=b"", headers={"Content-Type": "application/json"})
            if method == "tools/list":
                return _jsonrpc_result(payload, {"tools": [{"name": "hello", "description": "d", "inputSchema": {}}]})
            if method == "tools/call":
                seen["name"] = payload["params"]["name"]
                seen["arguments"] = payload["params"]["arguments"]
                return _jsonrpc_result(payload, {
                    "content": [{"type": "text", "text": "hi"}],
                })
            return httpx.Response(500, text="unexpected")

        manager = _make_manager()
        _connected_server(manager)
        _install_transport(manager, handler)
        await manager.connect("s1")

        result = await manager.call_tool("s1", "hello", {"x": 1})
        assert seen["name"] == "hello"
        assert seen["arguments"] == {"x": 1}
        # text blocks are normalised to a plain list of strings
        assert result.get("content") == ["hi"]

    @pytest.mark.asyncio
    async def test_call_tool_disconnected_server_returns_error(self):
        manager = _make_manager()
        result = await manager.call_tool("ghost", "hello", {})
        assert "error" in result
        assert "not connected" in result["error"]


class TestRegistryIntegration:
    @pytest.mark.asyncio
    async def test_registry_registers_and_routes_mcp_tools(self):
        from app.core.tools.mcp_client import get_mcp_client_manager
        from app.core.tools.registry import ToolRegistry

        seen = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.read())
            method = payload.get("method")
            if method == "tools/call":
                seen["name"] = payload["params"]["name"]
                return _jsonrpc_result(payload, {"content": [{"type": "text", "text": "mcp-ok"}]})
            return httpx.Response(
                500, json={"jsonrpc": "2.0", "id": payload.get("id"), "error": {"code": -32000, "message": "unexpected"}},
            )

        mgr = get_mcp_client_manager()
        mgr._servers.clear()
        if mgr._http_client is not None:
            await mgr._http_client.aclose()
            mgr._http_client = None
        conn = MCPServerConnection(
            server_id="s1",
            name="S1",
            url="http://mcp.test/mcp",
            transport=TransportType.STREAMABLE_HTTP,
            status=ConnectionStatus.CONNECTED,
            tools=[{"name": "hello", "description": "d", "inputSchema": {"type": "object", "properties": {}}}],
        )
        mgr._servers["s1"] = conn
        mgr._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

        try:
            registry = ToolRegistry(knowledge_base_id=1)
            assert "mcp:s1:hello" in registry._specs

            result = await registry.execute("mcp:s1:hello", {})
            assert result.success, result.message
            assert seen["name"] == "hello"
            assert result.data.get("content") == ["mcp-ok"]
        finally:
            mgr._servers.clear()
            if mgr._http_client is not None:
                await mgr._http_client.aclose()
                mgr._http_client = None
