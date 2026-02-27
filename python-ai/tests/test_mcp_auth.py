"""MCP endpoint authentication tests — verifies FastAPI route-level security."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.utils.config import config


@pytest.fixture
def any_token():
    """Return a configured token for test requests."""
    return config.INTERNAL_API_TOKEN or "test-token"


@pytest.mark.asyncio
async def test_mcp_initialize_is_public(any_token):
    """initialize handshake must NOT require authentication."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/mcp", json={
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
            "id": 1,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["protocolVersion"] == "2024-11-05"


@pytest.mark.asyncio
async def test_mcp_tools_list_is_public():
    """tools/list must NOT require authentication."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/mcp", json={
            "jsonrpc": "2.0",
            "method": "tools/list",
            "id": 2,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["result"]["tools"]) >= 3


@pytest.mark.asyncio
async def test_mcp_tools_call_requires_auth():
    """tools/call must be rejected without X-Internal-Token."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/mcp", json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "calculate", "arguments": {"expression": "1+1"}},
            "id": 3,
        })
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_mcp_tools_call_succeeds_with_valid_token(any_token):
    """tools/call must succeed with a valid X-Internal-Token."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/mcp", json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "calculate", "arguments": {"expression": "2+3"}},
            "id": 4,
        }, headers={"X-Internal-Token": any_token})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "result" in data
        content = data["result"]["content"][0]["text"]
        assert "5" in content


@pytest.mark.asyncio
async def test_mcp_tools_call_rejected_with_wrong_token(any_token):
    """tools/call must be rejected with an invalid token."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/mcp", json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "calculate", "arguments": {"expression": "1+1"}},
            "id": 5,
        }, headers={"X-Internal-Token": "wrong-token-obviously"})
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_mcp_search_knowledge_base_requires_kb_id_header(any_token):
    """search_knowledge_base must require X-HFusionHub-KB-ID header."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/mcp", json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "search_knowledge_base", "arguments": {"query": "test"}},
            "id": 6,
        }, headers={"X-Internal-Token": any_token})
        # Should fail because no KB ID header
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
