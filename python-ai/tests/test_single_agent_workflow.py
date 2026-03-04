"""P9 regression tests for the bounded single-agent runtime."""

import asyncio

import pytest

from app.core.agent.agent import Agent, AgentResponse
from app.core.agent.workflow_runtime import (
    NO_SUFFICIENT_EVIDENCE_REPLY,
    AgentRunStore,
    SingleAgentWorkflow,
)
from app.core.tools import ToolExecutionPolicy


class _Agent(Agent):
    def __init__(self, responses=None, error=None):
        self.responses = list(responses or [AgentResponse(content="ok")])
        self.error = error
        self.calls = 0

    async def run(self, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return self.responses.pop(0)

    async def run_stream(self, **kwargs):
        yield "ok"

    def get_tools(self):
        return []


@pytest.mark.asyncio
async def test_scoped_failure_returns_evidence_safe_reply_and_private_trace():
    store = AgentRunStore()
    workflow = SingleAgentWorkflow(_Agent(error=RuntimeError("secret prompt")), knowledge_base_id=9, run_store=store)

    response = await workflow.run(query="private question")

    assert response.content == NO_SUFFICIENT_EVIDENCE_REPLY
    assert response.agent_status == "tool_error"  # Agent V1: non-timeout errors → tool_error
    assert response.status == "tool_error"
    run = store.get(response.agent_run_id)
    assert run["knowledge_base_id"] == 9
    assert run["status"] == "tool_error"  # V1: run status matches response status
    assert "private question" not in str(run)
    assert "secret prompt" not in str(run)


@pytest.mark.asyncio
async def test_timeout_is_retried_once_then_completes():
    class _TimeoutThenSuccess(_Agent):
        async def run(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise asyncio.TimeoutError()
            return AgentResponse(content="recovered")

    store = AgentRunStore()
    delegate = _TimeoutThenSuccess()
    workflow = SingleAgentWorkflow(delegate, max_retries=1, retry_delay_seconds=0, run_store=store)

    response = await workflow.run(query="retry")

    assert response.content == "recovered"
    assert delegate.calls == 2
    assert [event["name"] for event in store.get(response.agent_run_id)["events"]] == ["agent", "retry", "agent"]


def test_tool_policy_cannot_change_the_authorised_knowledge_base():
    policy = ToolExecutionPolicy(
        allowed_names={"search_knowledge_base"}, knowledge_base_id=3, max_search_results=4,
    )

    normalized = policy.normalize("search_knowledge_base", {
        "query": "release date", "knowledge_base_id": 999, "top_k": 999,
    })

    assert normalized == {"query": "release date", "top_k": 4}


def test_tool_policy_rejects_unapproved_tool():
    policy = ToolExecutionPolicy(allowed_names={"calculate"})
    with pytest.raises(ValueError, match="tool_not_allowed"):
        policy.normalize("get_current_time", {})
