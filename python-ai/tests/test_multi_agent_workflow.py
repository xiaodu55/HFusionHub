"""P10 tests for evidence-reviewed multi-agent collaboration."""

import asyncio
import json

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


class _StreamingDelegate(Agent):
    """A delegate whose ``run_stream`` mirrors ReactAgent: emit a retrieval
    ``step_completed`` event carrying ``sources``, then free-text chunks."""

    def __init__(self, sources=None, text="answer"):
        self.sources = sources or []
        self.text = text

    async def run(self, **kwargs):
        return AgentResponse(content=self.text, sources=self.sources)

    async def run_stream(self, **kwargs):
        if self.sources:
            yield json.dumps(
                {"event": "step_completed", "step_type": "retrieval", "sources": self.sources},
                ensure_ascii=False,
            )
        yield self.text

    def get_tools(self):
        return []


@pytest.mark.asyncio
async def test_stream_rejects_cross_kb_citation_before_text():
    """The streaming path must gate on retrieval sources before text: a
    cross-KB citation is replaced by the generic refusal, not forwarded."""
    workflow = BoundedMultiAgentWorkflow(
        _StreamingDelegate(sources=[_source(kb_id=8)]),
        knowledge_base_id=7,
        run_store=AgentRunStore(),
    )

    chunks = [chunk async for chunk in workflow.run_stream(query="q")]

    # The retrieval event passes through, but the answer text is vetoed.
    assert chunks[-1] == NO_SUFFICIENT_EVIDENCE_REPLY
    assert "answer" not in chunks[-1]


@pytest.mark.asyncio
async def test_stream_passes_authorised_evidence():
    """Authorised sources pass the streaming critic untouched."""
    workflow = BoundedMultiAgentWorkflow(
        _StreamingDelegate(sources=[_source(kb_id=7)]),
        knowledge_base_id=7,
        run_store=AgentRunStore(),
    )

    chunks = [chunk async for chunk in workflow.run_stream(query="q")]

    assert chunks[-1] == "answer"


@pytest.mark.asyncio
async def test_stream_passes_through_when_delegate_has_no_sources():
    """When the delegate produced no retrieval sources it has already applied
    its own insufficient-evidence / empty-KB gate, so the stream is forwarded
    unchanged rather than double-stamped with the generic refusal."""
    workflow = BoundedMultiAgentWorkflow(
        _StreamingDelegate(sources=[]),
        knowledge_base_id=7,
        run_store=AgentRunStore(),
    )

    chunks = [chunk async for chunk in workflow.run_stream(query="q")]

    assert chunks == ["answer"]
