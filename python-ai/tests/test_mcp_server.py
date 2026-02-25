"""Tests for MCP (Model Context Protocol) server."""

import pytest
from app.core.tools.mcp_server import (
    handle_mcp_request,
    get_mcp_tool_schemas,
    _jsonrpc_response,
    _jsonrpc_error,
    ERROR_METHOD_NOT_FOUND,
    ERROR_INVALID_PARAMS,
)


class TestMCPToolSchemas:
    def test_returns_four_tools(self):
        schemas = get_mcp_tool_schemas()
        assert len(schemas) == 4
        names = {s["name"] for s in schemas}
        assert names == {"search_knowledge_base", "calculate", "get_current_time", "web_search"}

    def test_each_tool_has_input_schema(self):
        for schema in get_mcp_tool_schemas():
            assert "inputSchema" in schema
            assert schema["inputSchema"]["type"] == "object"
            assert "properties" in schema["inputSchema"]


class TestInitializeHandshake:
    @pytest.mark.asyncio
    async def test_returns_protocol_version(self):
        resp = await handle_mcp_request("initialize", {"protocolVersion": "2024-11-05"}, 1)
        result = resp["result"]
        assert result["protocolVersion"] == "2024-11-05"
        assert "tools" in result["capabilities"]

    @pytest.mark.asyncio
    async def test_returns_server_info(self):
        resp = await handle_mcp_request("initialize", {}, 2)
        assert resp["result"]["serverInfo"]["name"] == "HFusionHub MCP Server"


class TestToolsList:
    @pytest.mark.asyncio
    async def test_lists_all_tools(self):
        resp = await handle_mcp_request("tools/list", None, 1)
        tools = resp["result"]["tools"]
        assert len(tools) == 4


class TestToolsCall:
    @pytest.mark.asyncio
    async def test_calculate_adds_numbers(self):
        resp = await handle_mcp_request("tools/call", {
            "name": "calculate",
            "arguments": {"expression": "3 + 4"}
        }, 1)
        content = resp["result"]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "text"
        assert "7" in content[0]["text"]

    @pytest.mark.asyncio
    async def test_get_current_time_returns_time(self):
        resp = await handle_mcp_request("tools/call", {
            "name": "get_current_time",
            "arguments": {}
        }, 2)
        content = resp["result"]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "text"

    @pytest.mark.asyncio
    async def test_calculate_rejects_empty_expression(self):
        resp = await handle_mcp_request("tools/call", {
            "name": "calculate",
            "arguments": {"expression": ""}
        }, 3)
        content = resp["result"]["content"]
        assert "拒绝" in content[0]["text"] or "invalid" in content[0]["text"].lower()

    @pytest.mark.asyncio
    async def test_unknown_tool_is_rejected(self):
        resp = await handle_mcp_request("tools/call", {
            "name": "delete_everything",
            "arguments": {}
        }, 4)
        assert resp["result"]["content"][0]["text"].startswith("错误")

    @pytest.mark.asyncio
    async def test_missing_tool_name_returns_error(self):
        resp = await handle_mcp_request("tools/call", {}, 5)
        assert resp["error"]["code"] == ERROR_INVALID_PARAMS


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_unknown_method_returns_error(self):
        resp = await handle_mcp_request("unknown/method", None, 1)
        assert resp["error"]["code"] == ERROR_METHOD_NOT_FOUND

    @pytest.mark.asyncio
    async def test_notification_returns_empty(self):
        resp = await handle_mcp_request("notifications/initialized", {}, None)
        assert resp == {}


class TestJSONRPCHelpers:
    def test_jsonrpc_response_format(self):
        resp = _jsonrpc_response(1, {"key": "value"})
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        assert resp["result"] == {"key": "value"}

    def test_jsonrpc_error_format(self):
        err = _jsonrpc_error(2, -32600, "Invalid Request")
        assert err["jsonrpc"] == "2.0"
        assert err["id"] == 2
        assert err["error"]["code"] == -32600
        assert err["error"]["message"] == "Invalid Request"
