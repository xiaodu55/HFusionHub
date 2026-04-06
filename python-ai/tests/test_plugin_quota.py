from types import SimpleNamespace

import pytest

from app.core.agent.execution_context import AgentExecutionContext
from app.core.plugin import quota
from app.core.tools.registry import ToolRegistry
from app.core.tools.spec import ErrorCode
from app.utils.config import config


class _Response:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class _Client:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


@pytest.mark.asyncio
async def test_quota_client_uses_internal_envelope_and_fixed_contract(monkeypatch):
    monkeypatch.setattr(config, "INTERNAL_API_TOKEN", "internal-test-token")
    client = _Client(_Response(200, {
        "code": 200,
        "data": {"operation": "reserve", "execution_id": "exec-1"},
    }))

    accepted = await quota.transition_plugin_execution(
        "reserve", tenant_id=11, user_id=7, execution_id="exec-1",
        plugin_id="plugin-1", tool_name="lookup", http_client=client,
        backend_url="http://java.test",
    )

    assert accepted is True
    assert client.calls[0][0] == "http://java.test/api/internal/plugin/executions/quota"
    assert client.calls[0][1]["json"] == {
        "operation": "RESERVE", "tenant_id": 11, "user_id": 7,
        "execution_id": "exec-1", "plugin_id": "plugin-1", "tool_name": "lookup",
    }


@pytest.mark.asyncio
async def test_plugin_execution_is_not_started_when_reservation_is_rejected(monkeypatch):
    import app.core.plugin.registry as plugin_registry

    calls = []

    async def reject_reservation(operation, **kwargs):
        calls.append(operation)
        return False

    monkeypatch.setattr(quota, "transition_plugin_execution", reject_reservation)
    monkeypatch.setattr(plugin_registry, "get_plugin", lambda _: SimpleNamespace(enabled=True))

    def should_not_run(**kwargs):
        raise AssertionError("plugin must not run without a usage reservation")

    monkeypatch.setattr(plugin_registry, "execute_plugin_tool", should_not_run)
    context = AgentExecutionContext(user_id=7, knowledge_base_id=1, tenant_id=11, agent_run_id="run-1")

    result = await ToolRegistry(knowledge_base_id=1)._execute_plugin_tool(
        plugin_id="plugin-1", tool_name="lookup", safe_input={}, timeout_seconds=3.0, context=context,
    )

    assert result.ok is False
    assert result.error_code == ErrorCode.PERMISSION_DENIED
    assert calls == ["reserve"]


@pytest.mark.asyncio
async def test_plugin_execution_reserves_then_settles_after_success(monkeypatch):
    import app.core.plugin.registry as plugin_registry

    calls = []

    async def record_transition(operation, **kwargs):
        calls.append((operation, kwargs))
        return True

    monkeypatch.setattr(quota, "transition_plugin_execution", record_transition)
    monkeypatch.setattr(plugin_registry, "get_plugin", lambda _: SimpleNamespace(enabled=True))
    monkeypatch.setattr(plugin_registry, "execute_plugin_tool", lambda **_: SimpleNamespace(
        success=True, data={"value": "ok"}, error=None, error_code=None,
    ))
    context = AgentExecutionContext(user_id=7, knowledge_base_id=1, tenant_id=11, agent_run_id="run-1")

    result = await ToolRegistry(knowledge_base_id=1)._execute_plugin_tool(
        plugin_id="plugin-1", tool_name="lookup", safe_input={}, timeout_seconds=3.0, context=context,
    )

    assert result.ok is True
    assert [operation for operation, _ in calls] == ["reserve", "settle"]
    assert calls[0][1]["execution_id"] == calls[1][1]["execution_id"]
