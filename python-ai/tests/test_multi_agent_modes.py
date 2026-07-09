"""Batch 9 单元测试：多 Agent supervisor / handoff 模式（无 DSL）。

delegate 全部用可脚本化的 FakeAgent 替身，KB=1、sources 形态与
ReactAgent 产物一致（document_id/chunk_id/knowledge_base_id）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from app.core.agent.agent import AgentResponse
from app.core.agent.multi_agent_runtime import BoundedMultiAgentWorkflow
from app.core.agent.workflow_runtime import AgentRunStore, NO_SUFFICIENT_EVIDENCE_REPLY


def _source(chunk_id: str, kb_id: int = 1) -> Dict[str, Any]:
    return {"document_id": "doc-1", "chunk_id": chunk_id,
            "knowledge_base_id": kb_id, "score": 0.9}


def _response(content: str, sources: List[Dict[str, Any]], **overrides) -> AgentResponse:
    payload: Dict[str, Any] = {
        "content": content,
        "answer": content,
        "sources": sources,
        "status": "completed" if sources else "insufficient_evidence",
        "finish_reason": "stop" if sources else "insufficient_evidence",
        "model": "fake",
        "token_count": 10,
        "tool_calls_count": 1,
        "style_used": "detailed",
    }
    payload.update(overrides)
    return AgentResponse(**payload)


class FakeAgent:
    """按脚本顺序返回 AgentResponse 的 delegate 替身。"""

    def __init__(self, responses):
        self._responses = list(responses)
        self.queries: List[str] = []

    async def run(self, query: str, history=None, **kwargs):
        self.queries.append(query)
        if not self._responses:
            raise AssertionError("FakeAgent responses exhausted")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def run_stream(self, query: str, history=None, **kwargs):
        yield "fake"

    def get_tools(self):
        return []


def _workflow(delegate, mode, **kwargs) -> BoundedMultiAgentWorkflow:
    return BoundedMultiAgentWorkflow(
        delegate=delegate,
        knowledge_base_id=1,
        timeout_seconds=5.0,
        run_store=AgentRunStore(),
        mode=mode,
        **kwargs,
    )


# ── 模式校验 ───────────────────────────────────────────────────────────────


def test_unknown_mode_rejected():
    with pytest.raises(ValueError, match="unknown multi-agent mode"):
        _workflow(FakeAgent([]), "chaos")


# ── supervisor ─────────────────────────────────────────────────────────────


class TestSupervisorMode:
    @pytest.mark.asyncio
    async def test_supplement_merged_when_valid(self):
        base = _response("初步回答", [_source("c1")])
        supplement = _response("遗漏要点 X", [_source("c2")])
        wf = _workflow(FakeAgent([base, supplement]), "supervisor")

        result = await wf.run("问题")
        assert "【补充要点】" in result.content
        assert "遗漏要点 X" in result.content
        chunk_ids = {s["chunk_id"] for s in result.sources}
        assert chunk_ids == {"c1", "c2"}
        assert result.agent_run_id  # run id 关联

    @pytest.mark.asyncio
    async def test_supplement_without_evidence_discarded(self):
        base = _response("初步回答", [_source("c1")])
        supplement = _response("无证据的补充", [])  # 无来源 → 不采纳
        wf = _workflow(FakeAgent([base, supplement]), "supervisor")

        result = await wf.run("问题")
        assert result.content == "初步回答"
        assert {s["chunk_id"] for s in result.sources} == {"c1"}

    @pytest.mark.asyncio
    async def test_supplement_no_addition_discarded(self):
        base = _response("初步回答", [_source("c1")])
        supplement = _response("无补充", [_source("c2")])
        wf = _workflow(FakeAgent([base, supplement]), "supervisor")

        result = await wf.run("问题")
        assert result.content == "初步回答"

    @pytest.mark.asyncio
    async def test_base_without_evidence_skips_dispatch(self):
        base = _response("无证据回答", [])
        wf = _workflow(FakeAgent([base]), "supervisor")

        result = await wf.run("问题")
        assert result.status == "insufficient_evidence"
        # 委托层自身的拒答文案按 _insufficient 语义原样保留
        assert result.content == "无证据回答"


# ── handoff ────────────────────────────────────────────────────────────────


class TestHandoffMode:
    @pytest.mark.asyncio
    async def test_first_hop_accepted_early_exit(self):
        first = _response("第一棒即命中", [_source("c1")])
        wf = _workflow(FakeAgent([first]), "handoff", max_handoffs=1)

        result = await wf.run("问题")
        assert result.content == "第一棒即命中"
        assert len(wf.delegate.queries) == 1  # 不移交

    @pytest.mark.asyncio
    async def test_handoff_second_hop_accepted(self):
        first = _response("证据不足", [])
        second = _response("扩展检索命中", [_source("c9")])
        wf = _workflow(FakeAgent([first, second]), "handoff", max_handoffs=1)

        result = await wf.run("原始问题")
        assert result.content == "扩展检索命中"
        assert len(wf.delegate.queries) == 2
        # 第二棒携带改写提示
        assert "前一轮检索未找到足够证据" in wf.delegate.queries[1]
        assert "原始问题" in wf.delegate.queries[1]

    @pytest.mark.asyncio
    async def test_all_hops_rejected_returns_insufficient(self):
        wf = _workflow(
            FakeAgent([_response("a", []), _response("b", [])]),
            "handoff", max_handoffs=1)

        result = await wf.run("问题")
        assert result.status == "insufficient_evidence"
        assert len(wf.delegate.queries) == 2  # 1 次移交上限


# ── 流式包装（非 pipeline 模式）───────────────────────────────────────────


class TestStreamWrapperForNewModes:
    @pytest.mark.asyncio
    async def test_handoff_stream_emits_contract_events(self):
        first = _response("扩展检索命中", [_source("c9")])
        wf = _workflow(
            FakeAgent([_response("证据不足", []), first]),
            "handoff", max_handoffs=1)

        chunks = [chunk async for chunk in wf.run_stream("原始问题")]
        parsed = [chunk for chunk in chunks if chunk.startswith("{")]
        import json

        events = [json.loads(p) for p in parsed]
        kinds = [e["event"] for e in events]
        assert kinds[0] == "run_started"
        assert "step_completed" in kinds
        assert kinds[-1] == "run_completed"
        # 文本 chunk 原样存在
        assert "扩展检索命中" in chunks

    @pytest.mark.asyncio
    async def test_pipeline_mode_keeps_streaming_passthrough(self):
        class _StreamDelegate(FakeAgent):
            async def run_stream(self, query, history=None, **kwargs):
                yield "流式"
                yield "片段"

        wf = _workflow(_StreamDelegate([]), "pipeline")
        chunks = [chunk async for chunk in wf.run_stream("q")]
        assert chunks == ["流式", "片段"]
