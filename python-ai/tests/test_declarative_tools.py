from unittest.mock import AsyncMock

import pytest

from app.core.agent.execution_context import AgentExecutionContext
from app.core.tools import registry as registry_module
from app.core.tools.declarative_http_tool import DeclarativeHttpTool
from app.core.tools.registry import ToolRegistry


def _spec(tenant_id=7):
    return {
        "name": "custom_weather",
        "display_name": "查询天气",
        "description": "查询实时天气",
        "example": "查询北京天气",
        "input_schema": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "城市"}},
            "required": ["city"],
        },
        "output_schema": {"type": "object"},
        "risk_level": "read_only",
        "required_permissions": [],
        "timeout_seconds": 8,
        "agent_version": "1.0",
        "category": "external",
        "execution": {"type": "http_get", "url": "https://api.example.com/weather"},
        "_plugin_id": "plugin-1",
        "_plugin_name": "天气插件",
        "_plugin_kind": "declarative",
        "_tenant_id": tenant_id,
    }


def test_registry_loads_tenant_scoped_declarative_tool(monkeypatch):
    monkeypatch.setattr(registry_module, "_fetch_remote_plugin_specs", lambda tenant_id: [_spec(tenant_id)])
    registry = ToolRegistry(knowledge_base_id=1, tenant_id=7)

    spec = registry.get_spec("custom_weather")

    assert spec is not None
    assert getattr(spec, "_display_name") == "查询天气"
    assert getattr(spec, "_tenant_id") == 7
    assert "custom_weather" in {tool["name"] for tool in registry.get_tools()}


@pytest.mark.asyncio
async def test_declarative_tool_executes_for_matching_tenant(monkeypatch):
    monkeypatch.setattr(registry_module, "_fetch_remote_plugin_specs", lambda tenant_id: [_spec(tenant_id)])
    execute = AsyncMock(return_value={"status_code": 200, "data": {"temperature": 21}})
    monkeypatch.setattr(DeclarativeHttpTool, "execute", execute)
    registry = ToolRegistry(knowledge_base_id=1, tenant_id=7)
    context = AgentExecutionContext(user_id=3, knowledge_base_id=1, tenant_id=7)

    result = await registry.execute("custom_weather", {"city": "北京"}, context=context)

    assert result.ok is True
    assert result.data["data"]["temperature"] == 21
    execute.assert_awaited_once_with(city="北京")


@pytest.mark.asyncio
async def test_declarative_tool_rejects_cross_tenant_execution(monkeypatch):
    monkeypatch.setattr(registry_module, "_fetch_remote_plugin_specs", lambda tenant_id: [_spec(7)])
    registry = ToolRegistry(knowledge_base_id=1, tenant_id=7)
    context = AgentExecutionContext(user_id=3, knowledge_base_id=1, tenant_id=8)

    result = await registry.execute("custom_weather", {"city": "北京"}, context=context)

    assert result.ok is False
    assert result.error_code == "permission_denied"


def test_declarative_tool_rejects_private_endpoint(monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("127.0.0.1", 443))],
    )

    with pytest.raises(ValueError, match="内网"):
        DeclarativeHttpTool._validate_public_https("https://internal.example.com/data")
