"""
Tests for B4 — flag-gated web_search exposure.

The registry keeps web_search invisible to V1 agents by default (contract
preserved); when the registry is created with ``enable_web_search=True`` the
tool becomes visible, and the policy engine still gates execution (approval /
mode / production lockout).
"""

import pytest

from app.core.agent.execution_context import AgentExecutionContext
from app.core.tools.registry import ToolRegistry
from app.core.tools.result import ToolResult


def _ctx(**overrides):
    base = dict(user_id=1, knowledge_base_id=1, mode="read_only")
    base.update(overrides)
    return AgentExecutionContext(**base)


def test_default_registry_excludes_web_search_from_v1_tools():
    reg = ToolRegistry(knowledge_base_id=1)
    names = {t["name"] for t in reg.get_tools(v1_only=True)}
    assert "web_search" not in names
    assert names == {"search_knowledge_base", "read_chunk", "list_document_chunks"}


def test_flag_enabled_registry_includes_web_search():
    reg = ToolRegistry(knowledge_base_id=1, enable_web_search=True)
    names = {t["name"] for t in reg.get_tools(v1_only=True)}
    assert "web_search" in names
    assert "search_knowledge_base" in names


def test_flag_enabled_registry_still_hides_write_note():
    """enable_web_search must NOT implicitly enable write tools."""
    reg = ToolRegistry(knowledge_base_id=1, enable_web_search=True, agent_version="1.0")
    names = {t["name"] for t in reg.get_tools(v1_only=True)}
    assert "write_note" not in names


@pytest.mark.asyncio
async def test_default_registry_rejects_web_search_execution():
    reg = ToolRegistry(knowledge_base_id=1)
    result = await reg.execute("web_search", {"query": "test"}, context=_ctx())
    assert result.error_code == "knowledge_base_scope_denied"


@pytest.mark.asyncio
async def test_flag_enabled_registry_read_only_mode_requires_approval():
    """Exposed but read_only mode → external tool → approval_required."""
    reg = ToolRegistry(knowledge_base_id=1, enable_web_search=True)
    result = await reg.execute("web_search", {"query": "test"}, context=_ctx())
    assert result.error_code == "approval_required"


@pytest.mark.asyncio
async def test_flag_enabled_registry_approval_bypass_runs_tool(monkeypatch):
    """Admin in read_write mode with EXTERNAL_HTTP permission runs the tool."""
    reg = ToolRegistry(knowledge_base_id=1, enable_web_search=True)

    async def fake_execute(query, max_results=5, **kwargs):
        return [{"title": "t", "url": "https://example.com", "snippet": "s"}]

    monkeypatch.setattr(reg._instances["web_search"], "execute", fake_execute)

    ctx = _ctx(
        mode="read_write",
        user_role="admin",
        permissions=frozenset({"knowledge_base:read", "external:http"}),
    )
    result = await reg.execute("web_search", {"query": "test"}, context=ctx)
    assert result.error_code is None
    assert result.ok is True
