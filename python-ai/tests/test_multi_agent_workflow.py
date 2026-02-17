"""P10 tests for evidence-reviewed multi-agent collaboration."""

import asyncio

import pytest

from app.core.agent.agent import Agent, AgentResponse
from app.core.agent.multi_agent_runtime import BoundedMultiAgentWorkflow
from app.core.agent.workflow_runtime import AgentRunStore, NO_SUFFICIENT_EVIDENCE_REPLY


class _Delegate(Agent):
    def __init__(self, response=None, error=None):
        self.response = response or AgentResponse(content="answer")
        self.error = error
        self.calls = 0

    async def run(self, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return self.response

    async def run_stream(self, **kwargs):
        yield "unexpected"

    def get_tools(self):
        return []


def _source(kb_id=7):
    return {
        "knowledge_base_id": kb_id,
        "document_id": 5,
        "chunk_id": "chunk-1",
        "title": "policy",
    }


@pytest.mark.asyncio
async def test_multi_agent_preserves_authorised_evidence_and_records_roles():
    store = AgentRunStore()
    delegate = _Delegate(AgentResponse(content="grounded", sources=[_source()]))
    workflow = BoundedMultiAgentWorkflow(delegate, knowledge_base_id=7, run_store=store)

    response = await workflow.run(query="private question")

    assert response.content == "grounded"
    assert response.sources == [_source()]
    assert response.agent_status == "completed"
    run = store.get(response.agent_run_id)
    assert [event["name"] for event in run["events"]] == [
        "retrieval_agent", "evidence_critic", "synthesis_agent",
    ]
    assert "private question" not in str(run)


@pytest.mark.asyncio
async def test_cross_kb_citation_is_rejected_without_leaking_answer():
    store = AgentRunStore()
    workflow = BoundedMultiAgentWorkflow(
        _Delegate(AgentResponse(content="secret", sources=[_source(kb_id=8)])),
        knowledge_base_id=7,
        run_store=store,
    )

    response = await workflow.run(query="private question")

    assert response.content == NO_SUFFICIENT_EVIDENCE_REPLY
    assert response.sources == []
    run = store.get(response.agent_run_id)
    assert run["finish_reason"] == "scope_mismatch"
    assert run["events"][-1]["error_code"] == "scope_mismatch"
    assert "secret" not in str(run)


@pytest.mark.asyncio
async def test_missing_evidence_is_rejected_even_when_delegate_returns_text():
    workflow = BoundedMultiAgentWorkflow(
        _Delegate(AgentResponse(content="ungrounded", sources=[])),
        knowledge_base_id=7,
        run_store=AgentRunStore(),
    )

    response = await workflow.run(query="question")

    assert response.content == NO_SUFFICIENT_EVIDENCE_REPLY
    assert response.finish_reason == "insufficient_evidence"


@pytest.mark.asyncio
async def test_timeout_is_evidence_safe():
    class _SlowDelegate(_Delegate):
        async def run(self, **kwargs):
            await asyncio.sleep(0.02)
            return AgentResponse(content="late", sources=[_source()])

    workflow = BoundedMultiAgentWorkflow(
        _SlowDelegate(), knowledge_base_id=7, timeout_seconds=0.001, run_store=AgentRunStore()
    )

    response = await workflow.run(query="question")

    assert response.content == NO_SUFFICIENT_EVIDENCE_REPLY
    assert response.finish_reason == "multi_agent_timeout"


@pytest.mark.asyncio
async def test_no_selected_kb_delegates_without_collaboration():
    delegate = _Delegate(AgentResponse(content="ordinary chat"))
    workflow = BoundedMultiAgentWorkflow(delegate, knowledge_base_id=None, run_store=AgentRunStore())

    response = await workflow.run(query="hello")

    assert response.content == "ordinary chat"
    assert delegate.calls == 1
