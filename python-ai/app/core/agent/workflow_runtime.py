"""Bounded, read-only execution records for the P9 single-agent workflow.

The runtime deliberately records operational metadata rather than prompts,
thoughts, tool arguments, observations, or retrieved document text.  Those
items can contain user data and already have their own scoped RAG trace.

Agent V1: enforces a tool whitelist (search_knowledge_base, read_chunk,
list_document_chunks) and returns standardised status codes.
"""

from __future__ import annotations

import asyncio
import builtins
import json
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Any, AsyncGenerator
from uuid import uuid4

from .agent import Agent, AgentResponse
from .agent_observability import AgentTrace, get_agent_trace_store

# ── Agent V1 status constants ──
STATUS_COMPLETED = "completed"
STATUS_INSUFFICIENT_EVIDENCE = "insufficient_evidence"
STATUS_WAITING_APPROVAL = "waiting_approval"
STATUS_TOOL_ERROR = "tool_error"
STATUS_TIMEOUT = "timeout"
STATUS_FAILED = "failed"

NO_SUFFICIENT_EVIDENCE_REPLY = (
    "我在当前知识库中未检索到足够依据，无法基于资料回答这个问题。"
    "建议：1) 到「文档」页确认相关资料已完成解析；2) 换一种问法，或补充包含该内容的资料。"
    "我不会编造知识库范围外的内容。"
)
SERVICE_UNAVAILABLE_REPLY = "抱歉，AI 服务暂时不可用，请稍后重试。"


@dataclass
class AgentRunEvent:
    name: str
    status: str
    attempt: int = 0
    duration_ms: float = 0.0
    error_code: str | None = None
    failed_tool: str | None = None


@dataclass
class AgentRun:
    run_id: str
    knowledge_base_id: int | None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: str = "running"
    finish_reason: str | None = None
    duration_ms: float = 0.0
    events: list[AgentRunEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return data


class AgentRunStore:
    """Thread-safe, bounded in-memory run store with no conversation content."""

    def __init__(self, max_runs: int = 500):
        self._runs: deque[AgentRun] = deque(maxlen=max(1, max_runs))
        self._lock = Lock()

    def start(self, knowledge_base_id: int | None) -> AgentRun:
        run = AgentRun(run_id=str(uuid4()), knowledge_base_id=knowledge_base_id)
        with self._lock:
            self._runs.appendleft(run)
        return run

    def list(self, limit: int = 50, knowledge_base_id: int | None = None) -> builtins.list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 200))
        with self._lock:
            runs = list(self._runs)
        if knowledge_base_id is not None:
            runs = [run for run in runs if run.knowledge_base_id == knowledge_base_id]
        return [run.to_dict() for run in runs[:safe_limit]]

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            for run in self._runs:
                if run.run_id == run_id:
                    return run.to_dict()
        return None

    def clear(self) -> None:
        with self._lock:
            self._runs.clear()


_agent_run_store = AgentRunStore()


def get_agent_run_store() -> AgentRunStore:
    return _agent_run_store


class SingleAgentWorkflow(Agent):
    """Apply a timeout, a safe retry policy, tool whitelist and a trace to one
    existing agent.

    Agent V1: only ``search_knowledge_base``, ``read_chunk``, and
    ``list_document_chunks`` may be invoked.  Any other tool is rejected before
    the delegate agent ever sees it.

    This is intentionally a small boundary around the current React agent.  It
    does not add autonomous write tools, and it never changes a selected KB
    failure into a model-only answer.
    """

    # Agent V1 tool whitelist — hard-coded; not configurable at runtime.
    V1_ALLOWED_TOOLS: frozenset = frozenset({
        "search_knowledge_base",
        "read_chunk",
        "list_document_chunks",
    })

    def __init__(
        self,
        delegate: Agent,
        knowledge_base_id: int | None = None,
        timeout_seconds: float = 45.0,
        max_retries: int = 1,
        retry_delay_seconds: float = 0.2,
        run_store: AgentRunStore | None = None,
        allowed_tools: frozenset | None = None,
    ):
        self.delegate = delegate
        self.knowledge_base_id = knowledge_base_id
        self.timeout_seconds = max(0.001, timeout_seconds)
        self.max_retries = max(0, max_retries)
        self.retry_delay_seconds = max(0.0, retry_delay_seconds)
        self.run_store = run_store or get_agent_run_store()
        self.allowed_tools = allowed_tools or self.V1_ALLOWED_TOOLS

    @property
    def _has_selected_knowledge_base(self) -> bool:
        return bool(self.knowledge_base_id and self.knowledge_base_id > 0)

    # ── Agent V1: tool whitelist enforcement ────────────────────────────

    def _filter_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return only tools whose names are in the V1 whitelist."""
        return [t for t in tools if t.get("name") in self.allowed_tools]

    # ── Error helpers ──────────────────────────────────────────────────

    @staticmethod
    def _error_code(error: BaseException) -> str:
        if isinstance(error, asyncio.TimeoutError):
            return "timeout"
        if isinstance(error, (ConnectionError, OSError)):
            return "transient_dependency"
        return "agent_failure"

    @staticmethod
    def _retryable(error: BaseException) -> bool:
        # P9 exposes only read-only tools.  Do not broaden this retry policy
        # when a future phase introduces a mutating tool without idempotency.
        return isinstance(error, (asyncio.TimeoutError, ConnectionError, OSError))

    @staticmethod
    def _finish(run: AgentRun, status: str, finish_reason: str, started: float) -> None:
        run.status = status
        run.finish_reason = finish_reason
        run.duration_ms = round((time.monotonic() - started) * 1000, 2)

    def _record_trace(
        self,
        run: AgentRun,
        response: AgentResponse | None = None,
    ) -> None:
        """Persist operational metadata to the AgentTraceStore."""
        try:
            trace = AgentTrace(
                run_uuid=run.run_id,
                knowledge_base_id=self.knowledge_base_id,
                status=run.status,
                model=getattr(response, 'model', '') if response else '',
                duration_ms=run.duration_ms,
                token_usage=getattr(response, 'token_usage', None) if response else None,
                tool_calls_count=getattr(response, 'tool_calls_count', 0) if response else 0,
                sources_count=len(getattr(response, 'sources', [])) if response else 0,
                step_count=len(run.events),
                approval_count=0,
                total_approval_duration_ms=0.0,
                error_code=run.events[-1].error_code if run.events and run.events[-1].error_code else None,
                error_detail=getattr(response, 'error_detail', None) if response else None,
                failed_tool=getattr(response, 'failed_tool', None) if response else None,
            )
            get_agent_trace_store().record(trace)
        except Exception:
            # Trace recording is best-effort; never fail a run because of it.
            pass

    # ── Build a standardised V1 response ───────────────────────────────

    def _v1_response(
        self,
        content: str,
        status: str,
        sources: list[dict[str, Any]] | None = None,
        agent_run_id: str | None = None,
        token_usage: dict[str, int] | None = None,
        tool_calls_count: int = 0,
        max_tool_steps: int = 5,
        error_detail: str | None = None,
        failed_tool: str | None = None,
        **kwargs,
    ) -> AgentResponse:
        return AgentResponse(
            content=content,
            answer=content,
            status=status,
            finish_reason=status,
            sources=sources or [],
            agent_run_id=agent_run_id,
            token_usage=token_usage,
            tool_calls_count=tool_calls_count,
            max_tool_steps=max_tool_steps,
            error_detail=error_detail,
            failed_tool=failed_tool,
            steps=[],
            **kwargs,
        )

    # ── run ─────────────────────────────────────────────────────────────

    async def run(
        self,
        query: str,
        history: list[dict[str, str]] = None,
        **kwargs: Any,
    ) -> AgentResponse:
        run = self.run_store.start(self.knowledge_base_id)
        started = time.monotonic()

        # Enforce V1 tool whitelist on the delegate *before* execution.
        original_tools = self.delegate.get_tools()
        filtered_tools = self._filter_tools(original_tools)
        if hasattr(self.delegate, 'tools'):
            self.delegate.tools = filtered_tools  # type: ignore[attr-defined]

        for attempt in range(self.max_retries + 1):
            attempt_started = time.monotonic()
            try:
                response = await asyncio.wait_for(
                    self.delegate.run(query=query, history=history, **kwargs),
                    timeout=self.timeout_seconds,
                )
                run.events.append(AgentRunEvent(
                    name="agent", status="completed", attempt=attempt,
                    duration_ms=round((time.monotonic() - attempt_started) * 1000, 2),
                ))

                # Map finish_reason → Agent V1 status.
                fr = response.finish_reason or ""
                if fr == "insufficient_evidence":
                    v1_status = STATUS_INSUFFICIENT_EVIDENCE
                elif fr == "waiting_approval":
                    v1_status = STATUS_WAITING_APPROVAL
                elif fr in ("tool_error", "agent_failure"):
                    v1_status = STATUS_TOOL_ERROR
                elif fr in ("agent_timeout", "timeout"):
                    v1_status = STATUS_TIMEOUT
                else:
                    v1_status = STATUS_COMPLETED

                self._finish(run, v1_status, response.finish_reason or v1_status, started)
                self._record_trace(run, response)
                response.agent_run_id = run.run_id
                response.status = v1_status
                response.answer = response.answer or response.content
                return response

            except Exception as error:
                code = self._error_code(error)
                run.events.append(AgentRunEvent(
                    name="agent", status="failed", attempt=attempt,
                    duration_ms=round((time.monotonic() - attempt_started) * 1000, 2),
                    error_code=code,
                ))
                if attempt < self.max_retries and self._retryable(error):
                    run.events.append(AgentRunEvent(name="retry", status="scheduled", attempt=attempt + 1))
                    await asyncio.sleep(self.retry_delay_seconds)
                    continue

                # Build the appropriate V1 status.
                if code == "timeout":
                    v1_status = STATUS_TIMEOUT
                else:
                    v1_status = STATUS_TOOL_ERROR

                finish_reason = "agent_timeout" if code == "timeout" else "agent_failure"
                self._finish(run, v1_status, finish_reason, started)
                self._record_trace(run)

                # If the delegate already produced partial sources, preserve them.
                partial_sources = getattr(self.delegate, '_last_sources', [])

                return self._v1_response(
                    content=NO_SUFFICIENT_EVIDENCE_REPLY if self._has_selected_knowledge_base else SERVICE_UNAVAILABLE_REPLY,
                    status=v1_status,
                    sources=partial_sources if v1_status == STATUS_TIMEOUT else [],
                    agent_run_id=run.run_id,
                    tool_calls_count=getattr(self.delegate, '_tool_calls_count', 0),
                    max_tool_steps=kwargs.get("max_tool_steps", getattr(self.delegate, 'max_steps', 5)),
                    error_detail=str(error) if v1_status == STATUS_TOOL_ERROR else None,
                    failed_tool=None,
                )

        raise AssertionError("workflow retry loop must return")

    async def run_stream(
        self,
        query: str,
        history: list[dict[str, str]] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        run = self.run_store.start(self.knowledge_base_id)
        started = time.monotonic()

        # Enforce V1 tool whitelist on the delegate.
        if hasattr(self.delegate, 'tools'):
            original = self.delegate.get_tools()
            self.delegate.tools = self._filter_tools(original)  # type: ignore[attr-defined]

        try:
            async with asyncio.timeout(self.timeout_seconds):
                async for chunk in self.delegate.run_stream(query=query, history=history, **kwargs):
                    yield chunk
            run.events.append(AgentRunEvent(name="agent_stream", status="completed", attempt=0))
            self._finish(run, STATUS_COMPLETED, "stop", started)
            self._record_trace(run)
        except TimeoutError:
            run.events.append(AgentRunEvent(name="agent_stream", status="failed", error_code="timeout"))
            self._finish(run, STATUS_TIMEOUT, "agent_timeout", started)
            self._record_trace(run)
            # M11: 超时以结构化 run_error 帧透传（Java 映射为 timed_out），
            # 不再把错误文案伪装成普通内容块流入 SSE
            yield json.dumps({
                "event": "run_error",
                "status": STATUS_TIMEOUT,
                "agent_run_id": run.run_id,
                "error_code": "timeout",
                "error_detail": None,
                "failed_tool": None,
                "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
            }, ensure_ascii=False)
        except Exception as error:
            code = self._error_code(error)
            run.events.append(AgentRunEvent(name="agent_stream", status="failed", error_code=code))
            self._finish(run, STATUS_TOOL_ERROR, "agent_failure", started)
            self._record_trace(run)
            # M11: 异常同样以 run_error 帧透传，保留真实 error_code/error_detail
            yield json.dumps({
                "event": "run_error",
                "status": "agent_failure",
                "agent_run_id": run.run_id,
                "error_code": code,
                "error_detail": str(error)[:500],
                "failed_tool": None,
                "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
            }, ensure_ascii=False)

    def get_tools(self) -> list[dict[str, Any]]:
        return self._filter_tools(self.delegate.get_tools())
