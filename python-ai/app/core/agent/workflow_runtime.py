"""Bounded, read-only execution records for the P9 single-agent workflow.

The runtime deliberately records operational metadata rather than prompts,
thoughts, tool arguments, observations, or retrieved document text.  Those
items can contain user data and already have their own scoped RAG trace.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any, AsyncGenerator, Deque, Dict, List, Optional
from uuid import uuid4

from .agent import Agent, AgentResponse

NO_SUFFICIENT_EVIDENCE_REPLY = "我在当前知识库中未检索到足够依据，无法基于资料回答这个问题。"
SERVICE_UNAVAILABLE_REPLY = "抱歉，AI 服务暂时不可用，请稍后重试。"


@dataclass
class AgentRunEvent:
    name: str
    status: str
    attempt: int = 0
    duration_ms: float = 0.0
    error_code: Optional[str] = None


@dataclass
class AgentRun:
    run_id: str
    knowledge_base_id: Optional[int]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "running"
    finish_reason: Optional[str] = None
    duration_ms: float = 0.0
    events: List[AgentRunEvent] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return data


class AgentRunStore:
    """Thread-safe, bounded in-memory run store with no conversation content."""

    def __init__(self, max_runs: int = 500):
        self._runs: Deque[AgentRun] = deque(maxlen=max(1, max_runs))
        self._lock = Lock()

    def start(self, knowledge_base_id: Optional[int]) -> AgentRun:
        run = AgentRun(run_id=str(uuid4()), knowledge_base_id=knowledge_base_id)
        with self._lock:
            self._runs.appendleft(run)
        return run

    def list(self, limit: int = 50, knowledge_base_id: Optional[int] = None) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(limit, 200))
        with self._lock:
            runs = list(self._runs)
        if knowledge_base_id is not None:
            runs = [run for run in runs if run.knowledge_base_id == knowledge_base_id]
        return [run.to_dict() for run in runs[:safe_limit]]

    def get(self, run_id: str) -> Optional[Dict[str, Any]]:
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
    """Apply a timeout, a safe retry policy and a trace to one existing agent.

    This is intentionally a small boundary around the current React agent.  It
    does not add autonomous write tools, and it never changes a selected KB
    failure into a model-only answer.
    """

    def __init__(
        self,
        delegate: Agent,
        knowledge_base_id: Optional[int] = None,
        timeout_seconds: float = 45.0,
        max_retries: int = 1,
        retry_delay_seconds: float = 0.2,
        run_store: Optional[AgentRunStore] = None,
    ):
        self.delegate = delegate
        self.knowledge_base_id = knowledge_base_id
        self.timeout_seconds = max(0.001, timeout_seconds)
        self.max_retries = max(0, max_retries)
        self.retry_delay_seconds = max(0.0, retry_delay_seconds)
        self.run_store = run_store or get_agent_run_store()

    @property
    def _has_selected_knowledge_base(self) -> bool:
        return bool(self.knowledge_base_id and self.knowledge_base_id > 0)

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

    async def run(
        self,
        query: str,
        history: List[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> AgentResponse:
        run = self.run_store.start(self.knowledge_base_id)
        started = time.monotonic()
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
                status = "insufficient_evidence" if response.finish_reason == "insufficient_evidence" else "completed"
                self._finish(run, status, response.finish_reason or status, started)
                response.agent_run_id = run.run_id
                response.agent_status = status
                return response
            except Exception as error:  # handled below; never expose error details to chat
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

                finish_reason = "agent_timeout" if code == "timeout" else "agent_failure"
                self._finish(run, "failed", finish_reason, started)
                return AgentResponse(
                    content=NO_SUFFICIENT_EVIDENCE_REPLY if self._has_selected_knowledge_base else SERVICE_UNAVAILABLE_REPLY,
                    finish_reason=finish_reason,
                    sources=[],
                    agent_run_id=run.run_id,
                    agent_status="failed",
                )

        raise AssertionError("workflow retry loop must return")

    async def run_stream(
        self,
        query: str,
        history: List[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        run = self.run_store.start(self.knowledge_base_id)
        started = time.monotonic()
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async for chunk in self.delegate.run_stream(query=query, history=history, **kwargs):
                    yield chunk
            run.events.append(AgentRunEvent(name="agent_stream", status="completed", attempt=0))
            self._finish(run, "completed", "stop", started)
        except Exception as error:
            code = self._error_code(error)
            run.events.append(AgentRunEvent(name="agent_stream", status="failed", error_code=code))
            self._finish(run, "failed", "agent_timeout" if code == "timeout" else "agent_failure", started)
            yield NO_SUFFICIENT_EVIDENCE_REPLY if self._has_selected_knowledge_base else SERVICE_UNAVAILABLE_REPLY

    def get_tools(self) -> List[Dict[str, Any]]:
        return self.delegate.get_tools()
