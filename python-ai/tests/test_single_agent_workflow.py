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
    assert response.status == "tool_error"  # Agent V1: non-timeout errors → tool_error
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


@pytest.mark.asyncio
async def test_stream_timeout_emits_structured_run_error_frame():
    """M11: 超时不再把错误文案伪装成内容块，而是发结构化 run_error SSE 帧。"""
    import json as _json

    class _StreamTimeout(_Agent):
        async def run_stream(self, **kwargs):
            raise asyncio.TimeoutError()
            yield  # pragma: no cover - make it an async generator

    store = AgentRunStore()
    workflow = SingleAgentWorkflow(_StreamTimeout(), knowledge_base_id=7, run_store=store)

    chunks = [chunk async for chunk in workflow.run_stream(query="q")]
    assert chunks, "run_error frame must be emitted"
    frame = _json.loads(chunks[-1])
    assert frame["event"] == "run_error"
    assert frame["status"] == "timeout"
    assert frame["error_code"] == "timeout"
    # 错误文案不作为普通内容块下发
    assert all(NO_SUFFICIENT_EVIDENCE_REPLY not in c for c in chunks)


@pytest.mark.asyncio
async def test_stream_error_emits_run_error_frame_with_error_code():
    """M11: 异常以 run_error 帧透传，保留真实 error_code，不泄露给 content。"""
    import json as _json

    class _StreamError(_Agent):
        async def run_stream(self, **kwargs):
            raise RuntimeError("boom")
            yield  # pragma: no cover

    store = AgentRunStore()
    workflow = SingleAgentWorkflow(_StreamError(), knowledge_base_id=7, run_store=store)

    chunks = [chunk async for chunk in workflow.run_stream(query="q")]
    frame = _json.loads(chunks[-1])
    assert frame["event"] == "run_error"
    assert frame["status"] == "agent_failure"
    assert frame["error_code"] == "agent_failure"
    run = store.get(frame["agent_run_id"])
    assert run["status"] == "tool_error"
