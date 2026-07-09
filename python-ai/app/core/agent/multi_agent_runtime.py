"""Bounded, evidence-preserving P10 multi-agent orchestration.

The existing collaboration prototype is deliberately not exposed directly to
chat.  This runtime makes the rollout safe by keeping exactly one authorised
knowledge-base scope, executing no write tools, and allowing a deterministic
critic to veto an answer whose citations cannot prove that scope.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from .agent import Agent, AgentResponse
from .workflow_runtime import (
    NO_SUFFICIENT_EVIDENCE_REPLY,
    SERVICE_UNAVAILABLE_REPLY,
    AgentRun,
    AgentRunEvent,
    AgentRunStore,
    get_agent_run_store,
)

logger = logging.getLogger(__name__)


def _parse_stream_event(chunk: str) -> Optional[Dict[str, Any]]:
    """Return a structured SSE event dict if ``chunk`` is one, else ``None``.

    The delegate emits JSON-serialised ``{"event": ...}`` objects alongside
    free-text deltas.  Only a JSON object carrying an ``event`` key is treated
    as a structured event; anything else (including LLM text that merely starts
    with a brace but is not a dict event) is a text chunk.
    """
    if not isinstance(chunk, str) or not chunk.strip().startswith("{"):
        return None
    try:
        parsed = json.loads(chunk)
    except (TypeError, ValueError):
        return None
    if isinstance(parsed, dict) and "event" in parsed:
        return parsed
    return None


class BoundedMultiAgentWorkflow(Agent):
    """Bounded multi-agent orchestration over the P9 single-agent workflow.

    Three bounded modes (Batch 9 — no DSL, all roles reuse the same delegate,
    KB scope, timeout and deterministic critic):

    - ``pipeline``（默认）: researcher → evidence critic → synthesis（原 P10 行为）；
    - ``supervisor``: 检索研究员先产出初答与证据，supervisor 按确定性规则并行
      分派「补充分析」专家复核遗漏要点，最后确定性合并（不引入自由 LLM 汇总，
      sources 只能来自同 KB 的 delegate 产物）；
    - ``handoff``: 顺序移交——检索棒证据不足时移交一次「扩展检索棒」（改写
      提示重跑 delegate），仍不足则走既有 insufficient 语义。移交次数由
      ``max_handoffs`` 硬上限（默认 1）。

    ``delegate`` is the P9 bounded single-agent workflow.  The critic does not
    ask an LLM to judge its own work: it validates only stable citation fields.
    """

    _VALID_MODES = ("pipeline", "supervisor", "handoff")

    def __init__(
        self,
        delegate: Agent,
        knowledge_base_id: Optional[int],
        timeout_seconds: float = 60.0,
        run_store: Optional[AgentRunStore] = None,
        mode: str = "pipeline",
        max_handoffs: int = 1,
    ):
        if mode not in self._VALID_MODES:
            raise ValueError(f"unknown multi-agent mode: {mode!r}")
        self.delegate = delegate
        self.knowledge_base_id = knowledge_base_id
        self.timeout_seconds = max(0.001, timeout_seconds)
        self.run_store = run_store or get_agent_run_store()
        self.mode = mode
        self.max_handoffs = max(1, max_handoffs)

    @property
    def _has_selected_knowledge_base(self) -> bool:
        return bool(self.knowledge_base_id and self.knowledge_base_id > 0)

    @staticmethod
    def _finish(run: AgentRun, status: str, reason: str, started: float) -> None:
        run.status = status
        run.finish_reason = reason
        run.duration_ms = round((time.monotonic() - started) * 1000, 2)

    @staticmethod
    def _event(run: AgentRun, name: str, status: str, started: float, error_code: Optional[str] = None) -> None:
        run.events.append(AgentRunEvent(
            name=name,
            status=status,
            duration_ms=round((time.monotonic() - started) * 1000, 2),
            error_code=error_code,
        ))

    def _validate_sources(self, sources: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """Reject a citation list not backed by chunks from the authorised KB."""
        if not sources:
            return False, "missing_evidence"
        for source in sources:
            if not isinstance(source, dict):
                return False, "invalid_citation"
            if source.get("knowledge_base_id") != self.knowledge_base_id:
                return False, "scope_mismatch"
            if source.get("document_id") is None or source.get("chunk_id") is None:
                return False, "invalid_citation"
        return True, "accepted"

    def _validate_evidence(self, response: AgentResponse) -> Tuple[bool, str]:
        """Reject anything not backed by chunks from the authorised KB."""
        if response.finish_reason == "insufficient_evidence":
            return False, "insufficient_evidence"
        return self._validate_sources(response.sources)

    def _insufficient(self, run: AgentRun, started: float, reason: str,
                      original: Optional[AgentResponse] = None) -> AgentResponse:
        self._finish(run, "insufficient_evidence", reason, started)
        # The delegate (ReactAgent) already produces a tailored reply for the
        # insufficient_evidence case (e.g. "knowledge base is empty / still
        # parsing").  Preserve that content instead of stamping a generic
        # refusal — otherwise the empty-KB hint is lost.  For every other
        # rejection reason (missing_evidence / invalid_citation / scope_mismatch)
        # the generic refusal is kept because the answer may be hallucinated.
        preserve = (
            reason == "insufficient_evidence"
            and original is not None
            and bool(getattr(original, "content", ""))
        )
        content = original.content if preserve else NO_SUFFICIENT_EVIDENCE_REPLY
        return AgentResponse(
            content=content,
            finish_reason="insufficient_evidence",
            sources=[],
            agent_run_id=run.run_id,
            status="insufficient_evidence",
        )

    async def run(
        self,
        query: str,
        history: List[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> AgentResponse:
        # P10 is meaningful only with an explicit Java-authorised KB.  Preserve
        # P9's ordinary-chat behaviour if this class is used directly without
        # one, rather than accidentally making an unscoped collaboration.
        if not self._has_selected_knowledge_base:
            return await self.delegate.run(query=query, history=history, **kwargs)

        if self.mode == "supervisor":
            return await self._run_supervisor(query, history, **kwargs)
        if self.mode == "handoff":
            return await self._run_handoff(query, history, **kwargs)
        return await self._run_pipeline(query, history, **kwargs)

    async def _run_pipeline(
        self,
        query: str,
        history: List[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> AgentResponse:

        run = self.run_store.start(self.knowledge_base_id)
        started = time.monotonic()
        research_started = time.monotonic()
        try:
            response = await asyncio.wait_for(
                self.delegate.run(query=query, history=history, **kwargs),
                timeout=self.timeout_seconds,
            )
            self._event(run, "retrieval_agent", "completed", research_started)
        except asyncio.TimeoutError:
            self._event(run, "retrieval_agent", "failed", research_started, "timeout")
            self._finish(run, "failed", "multi_agent_timeout", started)
            return AgentResponse(
                content=NO_SUFFICIENT_EVIDENCE_REPLY,
                finish_reason="multi_agent_timeout",
                sources=[],
                agent_run_id=run.run_id,
                status="failed",
            )
        except Exception:
            self._event(run, "retrieval_agent", "failed", research_started, "agent_failure")
            self._finish(run, "failed", "multi_agent_failure", started)
            return AgentResponse(
                content=NO_SUFFICIENT_EVIDENCE_REPLY,
                finish_reason="multi_agent_failure",
                sources=[],
                agent_run_id=run.run_id,
                status="failed",
            )

        critic_started = time.monotonic()
        accepted, reason = self._validate_evidence(response)
        self._event(run, "evidence_critic", "completed" if accepted else "rejected", critic_started,
                    None if accepted else reason)
        if not accepted:
            return self._insufficient(run, started, reason, original=response)

        synthesis_started = time.monotonic()
        # The synthesis role preserves the answer and citations verbatim.  It
        # is intentionally not another free-form LLM call in this MVP.
        response.agent_run_id = run.run_id
        response.status = response.status or "completed"
        self._event(run, "synthesis_agent", "completed", synthesis_started)
        self._finish(run, "completed", response.finish_reason or "stop", started)
        return response

    async def _run_delegate_safely(
        self,
        run: AgentRun,
        event_name: str,
        query: str,
        history: List[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> Optional[AgentResponse]:
        """单次 delegate 调用：超时/异常只记事件并返回 None（专家失败隔离）。"""
        stage_started = time.monotonic()
        try:
            response = await asyncio.wait_for(
                self.delegate.run(query=query, history=history, **kwargs),
                timeout=self.timeout_seconds,
            )
            self._event(run, event_name, "completed", stage_started)
            return response
        except asyncio.TimeoutError:
            self._event(run, event_name, "failed", stage_started, "timeout")
            return None
        except Exception:
            self._event(run, event_name, "failed", stage_started, "agent_failure")
            return None

    @staticmethod
    def _merge_sources(*source_lists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """按 (document_id, chunk_id) 去重合并多棒来源，保持出现顺序。"""
        seen = set()
        merged: List[Dict[str, Any]] = []
        for sources in source_lists:
            for source in sources or []:
                if not isinstance(source, dict):
                    continue
                key = (source.get("document_id"), source.get("chunk_id"))
                if key in seen:
                    continue
                seen.add(key)
                merged.append(source)
        return merged

    async def _run_supervisor(
        self,
        query: str,
        history: List[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> AgentResponse:
        """supervisor 模式：检索研究员 → 确定性分派补充分析 → 确定性合并。

        分派规则是确定性的（初答证据有效即分派一次补充复核），补充专家复用
        同一 delegate 与 KB scope；合并只拼接文本与来源，不引入自由 LLM 汇总，
        sources 不可能凭空产生或跨 scope 泄漏。
        """
        run = self.run_store.start(self.knowledge_base_id)
        started = time.monotonic()

        base = await self._run_delegate_safely(run, "retrieval_agent", query, history, **kwargs)
        if base is None:
            self._finish(run, "failed", "multi_agent_failure", started)
            return AgentResponse(
                content=NO_SUFFICIENT_EVIDENCE_REPLY,
                finish_reason="multi_agent_failure",
                sources=[],
                agent_run_id=run.run_id,
                status="failed",
            )
        accepted, reason = self._validate_evidence(base)
        if not accepted:
            return self._insufficient(run, started, reason, original=base)

        # supervisor 分派：补充分析专家（同一 delegate，限定为“查漏”指令）
        supplement_prompt = (
            f"原始问题：{query}\n\n"
            f"初步回答：\n{(base.content or '')[:800]}\n\n"
            "请仅依据知识库补充上述初步回答遗漏的重要要点（最多 3 条，"
            "每条一行）；若无遗漏，直接回复“无补充”。"
        )
        dispatch_started = time.monotonic()
        supplement = await self._run_delegate_safely(
            run, "supervisor_analysis", supplement_prompt, history, **kwargs)
        supplement_ok = (
            supplement is not None
            and self._validate_evidence(supplement)[0]
            and "无补充" not in (supplement.content or "")
        )
        self._event(run, "supervisor_dispatch", "completed", dispatch_started)

        synthesis_started = time.monotonic()
        if supplement_ok:
            merged = AgentResponse(
                content=f"{base.content}\n\n【补充要点】\n{supplement.content}",
                answer=f"{base.content}\n\n【补充要点】\n{supplement.content}",
                sources=self._merge_sources(base.sources, supplement.sources),
                status=base.status or "completed",
                finish_reason=base.finish_reason or "stop",
                steps=base.steps,
                model=base.model,
                token_count=base.token_count + (supplement.token_count or 0),
                token_usage=base.token_usage,
                tool_calls_count=base.tool_calls_count + (supplement.tool_calls_count or 0),
                style_used=base.style_used,
                agent_run_id=run.run_id,
            )
            self._event(run, "synthesis_agent", "completed", synthesis_started)
            self._finish(run, "completed", merged.finish_reason, started)
            return merged

        base.agent_run_id = run.run_id
        base.status = base.status or "completed"
        self._event(run, "synthesis_agent", "completed", synthesis_started)
        self._finish(run, "completed", base.finish_reason or "stop", started)
        return base

    async def _run_handoff(
        self,
        query: str,
        history: List[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> AgentResponse:
        """handoff 模式：顺序移交——证据不足时移交扩展检索棒（次数硬上限）。

        每一棒产物都过同一确定性证据门控；任一棒通过即 early exit。
        """
        run = self.run_store.start(self.knowledge_base_id)
        started = time.monotonic()
        current_query = query
        last_response: Optional[AgentResponse] = None
        last_reason = "missing_evidence"

        for hop in range(1 + self.max_handoffs):
            response = await self._run_delegate_safely(
                run,
                "retrieval_agent" if hop == 0 else "handoff_agent",
                current_query,
                history,
                **kwargs,
            )
            if response is None:
                break
            last_response = response
            accepted, reason = self._validate_evidence(response)
            if accepted:
                response.agent_run_id = run.run_id
                response.status = response.status or "completed"
                self._finish(run, "completed", response.finish_reason or "stop", started)
                return response
            last_reason = reason
            if hop < self.max_handoffs:
                handoff_started = time.monotonic()
                self._event(run, "handoff", "completed", handoff_started,
                            f"hop_{hop + 1}:{reason}")
                current_query = (
                    f"{query}\n\n"
                    "（前一轮检索未找到足够证据；请使用同义改写、相关联的表述或"
                    "相邻章节重新检索后再回答。）"
                )

        return self._insufficient(run, started, last_reason, original=last_response)

    async def run_stream(
        self,
        query: str,
        history: List[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """Stream delegate output incrementally with a streaming evidence gate.

        The delegate (ReactAgent.run_stream) emits a ``step_completed`` event
        carrying its retrieval ``sources`` before any final text.  This wrapper
        captures those sources and runs the same deterministic P10 critic as
        the non-streaming path *before forwarding the first text chunk*, so the
        streaming answer cannot silently bypass evidence review.  If the
        delegate produced no usable sources it has already applied its own
        insufficient-evidence / empty-KB gate, so it is passed through
        untouched.  Rejected output is replaced with the generic refusal.
        """
        if not self._has_selected_knowledge_base:
            async for chunk in self.delegate.run_stream(query=query, history=history, **kwargs):
                yield chunk
            return

        # supervisor/handoff 模式：非流式执行 + 一次性发流（事件契约与
        # pipeline 流式一致：run_started → step_completed → 文本 → run_completed）。
        if self.mode != "pipeline":
            started = time.monotonic()
            response = await self.run(query=query, history=history, **kwargs)
            run_id = response.agent_run_id or "unknown"
            timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
            yield json.dumps({
                "event": "run_started", "agent_run_id": run_id, "timestamp": timestamp,
            }, ensure_ascii=False)
            yield json.dumps({
                "event": "step_completed", "sequence": 1, "step_type": "synthesis",
                "action": self.mode, "input_summary": "", "output_summary": "",
                "sources": response.sources or None,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "error_code": None, "timestamp": timestamp,
            }, ensure_ascii=False)
            if response.content:
                yield response.content
            yield json.dumps({
                "event": "run_completed", "status": response.status or "completed",
                "agent_run_id": run_id, "token_usage": response.token_usage,
                "tool_calls_count": response.tool_calls_count,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            }, ensure_ascii=False)
            return

        sources: List[Dict[str, Any]] = []
        gated = False
        async for chunk in self.delegate.run_stream(query=query, history=history, **kwargs):
            event = _parse_stream_event(chunk)
            if event is not None:
                # Structured SSE event — record retrieval sources and pass
                # through.  Never gates on events themselves.
                if event.get("event") == "step_completed":
                    event_sources = event.get("sources") or []
                    if event_sources:
                        sources = event_sources
                yield chunk
                continue

            # First free-text chunk: the retrieval event (if any) has already
            # been seen, so run the deterministic critic on its sources now.
            if not gated:
                gated = True
                if sources:
                    accepted, reason = self._validate_sources(sources)
                    if not accepted:
                        logger.info(
                            "[P10:stream] evidence gate rejected streaming answer (%s)", reason
                        )
                        yield NO_SUFFICIENT_EVIDENCE_REPLY
                        return
            yield chunk

    def get_tools(self) -> List[Dict[str, Any]]:
        return self.delegate.get_tools()
