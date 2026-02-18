"""Bounded, evidence-preserving P10 multi-agent orchestration.

The existing collaboration prototype is deliberately not exposed directly to
chat.  This runtime makes the rollout safe by keeping exactly one authorised
knowledge-base scope, executing no write tools, and allowing a deterministic
critic to veto an answer whose citations cannot prove that scope.
"""

from __future__ import annotations

import asyncio
import json
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


class BoundedMultiAgentWorkflow(Agent):
    """Run a researcher, a deterministic evidence critic, then synthesize.

    ``delegate`` is the P9 bounded single-agent workflow.  The P10 critic does
    not ask an LLM to judge its own work: it validates only stable citation
    fields.  Synthesis returns the researcher's already source-backed answer
    unchanged, so sources cannot be invented or lost between roles.
    """

    def __init__(
        self,
        delegate: Agent,
        knowledge_base_id: Optional[int],
        timeout_seconds: float = 60.0,
        run_store: Optional[AgentRunStore] = None,
    ):
        self.delegate = delegate
        self.knowledge_base_id = knowledge_base_id
        self.timeout_seconds = max(0.001, timeout_seconds)
        self.run_store = run_store or get_agent_run_store()

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

    def _validate_evidence(self, response: AgentResponse) -> Tuple[bool, str]:
        """Reject anything not backed by chunks from the authorised KB."""
        if response.finish_reason == "insufficient_evidence":
            return False, "insufficient_evidence"
        if not response.sources:
            return False, "missing_evidence"
        for source in response.sources:
            if not isinstance(source, dict):
                return False, "invalid_citation"
            if source.get("knowledge_base_id") != self.knowledge_base_id:
                return False, "scope_mismatch"
            if source.get("document_id") is None or source.get("chunk_id") is None:
                return False, "invalid_citation"
        return True, "accepted"

    def _insufficient(self, run: AgentRun, started: float, reason: str) -> AgentResponse:
        self._finish(run, "insufficient_evidence", reason, started)
        return AgentResponse(
            content=NO_SUFFICIENT_EVIDENCE_REPLY,
            finish_reason="insufficient_evidence",
            sources=[],
            agent_run_id=run.run_id,
            agent_status="insufficient_evidence",
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
                agent_status="failed",
            )
        except Exception:
            self._event(run, "retrieval_agent", "failed", research_started, "agent_failure")
            self._finish(run, "failed", "multi_agent_failure", started)
            return AgentResponse(
                content=NO_SUFFICIENT_EVIDENCE_REPLY,
                finish_reason="multi_agent_failure",
                sources=[],
                agent_run_id=run.run_id,
                agent_status="failed",
            )

        critic_started = time.monotonic()
        accepted, reason = self._validate_evidence(response)
        self._event(run, "evidence_critic", "completed" if accepted else "rejected", critic_started,
                    None if accepted else reason)
        if not accepted:
            return self._insufficient(run, started, reason)

        synthesis_started = time.monotonic()
        # The synthesis role preserves the answer and citations verbatim.  It
        # is intentionally not another free-form LLM call in this MVP.
        response.agent_run_id = run.run_id
        response.agent_status = "completed"
        self._event(run, "synthesis_agent", "completed", synthesis_started)
        self._finish(run, "completed", response.finish_reason or "stop", started)
        return response

    async def run_stream(
        self,
        query: str,
        history: List[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """Buffer P10 output until citation review has completed safely."""
        response = await self.run(query=query, history=history, **kwargs)
        if response.content:
            yield response.content
        if response.sources:
            yield json.dumps({"sources": response.sources}, ensure_ascii=False)

    def get_tools(self) -> List[Dict[str, Any]]:
        return self.delegate.get_tools()
