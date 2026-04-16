"""
Chat API Routes — Chat with AI agent (Agent V1).

Two entry points:
- ``POST /api/chat`` — General chat (knowledge_base_id optional).
- ``POST /api/agent/v1/chat`` — Agent V1 (knowledge_base_id REQUIRED,
  returns 422 without it).  Only V1-whitelisted tools are available.

Contract (Agent V1, non-streaming):
  Java ``AiClient.ChatResponse`` deserialises these JSON keys from Python.
  The primary answer field is ``content``; ``answer`` is a V1 mirror.

  ┌──────────────────┬──────────┬────────────────────────────┐
  │ JSON key         │ Type     │ Java field / note           │
  ├──────────────────┼──────────┼────────────────────────────┤
  │ content          │ string   │ AiClient.ChatResponse.     │
  │                  │          │ content (primary)          │
  │ answer           │ string   │ V1 mirror of content       │
  │ model            │ string   │ ChatResponse.model         │
  │ token_count      │ int      │ ChatResponse.tokenCount    │
  │ sources          │ [object] │ ChatResponse.sources       │
  │ steps            │ [object] │ ChatResponse.steps         │
  │ auto_detected_kb_│ int|null │ ChatResponse.autoDetected  │
  │ id               │          │ KbId                       │
  │ status           │ string   │ V1: completed|insufficient │
  │                  │          │ _evidence|tool_error|timeout│
  │ agent_run_id     │ string   │ V1: UUID of agent run      │
  │ token_usage      │ object   │ V1: {prompt,completion,    │
  │                  │          │     total}_tokens           │
  │ tool_calls_count │ int      │ V1: tool invocation count  │
  │ style_used       │ string   │ V1: concise|detailed|report│
  │ max_tool_steps   │ int      │ V1: configured max steps   │
  │ error_detail     │ string   │ V1: on tool_error/timeout  │
  │ failed_tool      │ string   │ V1: tool name that failed  │
  └──────────────────┴──────────┴────────────────────────────┘

SSE events (streaming):
  data: {"content": "chunk text..."}
  data: {"sources": [{"document_id": ..., "chunk_id": ..., ...}]}
  data: [DONE]

Agent structured events (intercepted by Java for persistence):
  data: {"event":"run_started","agent_run_id":"uuid","timestamp":"ISO"}
  data: {"event":"step_completed","sequence":1,"step_type":"retrieval",...}
  data: {"event":"run_completed","status":"completed","token_usage":{...},...}
  data: {"event":"run_error","status":"tool_error","error_code":"...",...}
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time as time_module
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.agent import get_agent, get_agent_run_store
from app.core.agent.agent import AgentResponse
from app.core.agent.execution_context import AgentExecutionContext
from app.core.llm.custom_provider import build_user_llm
from app.core.tenant.context import get_tenant_id
from app.core.policy.engine import PolicyContext, PolicyEngine
from app.core.policy.masking import build_arguments_summary
from app.core.rag.intent_tree_router import resolve_intent_route
from app.utils.config import config

router = APIRouter()
logger = logging.getLogger(__name__)

active_requests: Dict[str, asyncio.Task] = {}

CHAT_MESSAGE_MAX_LENGTH = 4000
CHAT_HISTORY_MAX_ITEMS = 50
CHAT_REQUEST_ID_MAX_LENGTH = 80
CHAT_MODEL_MAX_LENGTH = 100
SYSTEM_PROMPT_MAX_LENGTH = 8000

_INPUT_SUMMARY_MAX_LENGTH = 2000
_OUTPUT_SUMMARY_MAX_LENGTH = 2000

_VALID_STYLES = {"concise", "detailed", "report"}

# ── Content guardrails (output check) ─────────────────────────────────────
# The policy engine is stateless (pure decision function), so a single
# module-level instance is safe to share.  When the guardrails block an AI
# response, the content field is replaced with this refusal so the user is
# never served unsafe model output.
_GUARD_POLICY_ENGINE = PolicyEngine()
_GUARDED_RESPONSE = "抱歉，我无法提供该内容（内容安全校验未通过）。"


def _truncate(text: Optional[str], max_len: int) -> Optional[str]:
    """Truncate text to max_len characters, adding ellipsis if truncated."""
    if text is None:
        return None
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def _now_iso() -> str:
    """Return current UTC timestamp as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _build_step_event(
    sequence: int,
    step_type: str,
    action: Optional[str] = None,
    input_summary: Optional[str] = None,
    output_summary: Optional[str] = None,
    sources: Optional[List[Dict[str, Any]]] = None,
    duration_ms: float = 0.0,
    error_code: Optional[str] = None,
) -> str:
    """Build a structured step_completed SSE event JSON string."""
    return json.dumps({
        "event": "step_completed",
        "sequence": sequence,
        "step_type": step_type,
        "action": action,
        "input_summary": _truncate(input_summary, _INPUT_SUMMARY_MAX_LENGTH),
        "output_summary": _truncate(output_summary, _OUTPUT_SUMMARY_MAX_LENGTH),
        "sources": sources,
        "duration_ms": round(duration_ms, 2),
        "error_code": error_code,
        "timestamp": _now_iso(),
    }, ensure_ascii=False)


def _build_run_event(
    status: str,
    agent_run_id: Optional[str] = None,
    token_usage: Optional[Dict[str, int]] = None,
    tool_calls_count: int = 0,
) -> str:
    """Build a structured run_completed SSE event JSON string."""
    return json.dumps({
        "event": "run_completed",
        "status": status,
        "agent_run_id": agent_run_id,
        "token_usage": token_usage,
        "tool_calls_count": tool_calls_count,
        "timestamp": _now_iso(),
    }, ensure_ascii=False)


def _build_run_error_event(
    status: str,
    error_code: str,
    error_detail: Optional[str] = None,
    failed_tool: Optional[str] = None,
    agent_run_id: Optional[str] = None,
) -> str:
    """Build a structured run_error SSE event JSON string."""
    return json.dumps({
        "event": "run_error",
        "status": status,
        "error_code": error_code,
        "error_detail": error_detail,
        "failed_tool": failed_tool,
        "agent_run_id": agent_run_id,
        "timestamp": _now_iso(),
    }, ensure_ascii=False)


def _build_run_started_event(agent_run_id: str) -> str:
    """Build a structured run_started SSE event JSON string."""
    return json.dumps({
        "event": "run_started",
        "agent_run_id": agent_run_id,
        "timestamp": _now_iso(),
    }, ensure_ascii=False)


def _agent_chunk_to_sse(chunk: str) -> Optional[str]:
    """Convert one agent chunk into a browser-facing SSE event.

    Handles:
    - Structured event dicts (event field) → pass through for Java interception
    - Sources dicts → sources SSE event
    - Evaluation dicts → suppressed (internal only)
    - Plain text → content SSE event
    """
    try:
        parsed = json.loads(chunk)
        if isinstance(parsed, dict):
            # Structured agent events — pass through for Java to intercept
            if "event" in parsed:
                return f"data: {json.dumps(parsed, ensure_ascii=False)}\n\n"
            sources = parsed.get("sources")
            if sources:
                return f"data: {json.dumps({'sources': sources}, ensure_ascii=False)}\n\n"
            if "evaluation" in parsed:
                return None
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    return f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"


def _track_active_request(request_id: str) -> Optional[asyncio.Task]:
    task = asyncio.current_task()
    if task is not None:
        active_requests[request_id] = task
    return task


# ── Models ──────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"] = Field(..., description="Message role")
    content: str = Field(..., min_length=1, max_length=CHAT_MESSAGE_MAX_LENGTH)


class ChatRequest(BaseModel):
    """General chat request — knowledge_base_id is optional."""
    message: str = Field(..., min_length=1, max_length=CHAT_MESSAGE_MAX_LENGTH)
    conversation_id: Optional[int] = Field(None, ge=1)
    knowledge_base_id: Optional[int] = Field(None, ge=1)
    user_id: Optional[int] = Field(None, ge=1, description="Authenticated user ID — from Java session")
    history: List[ChatMessage] = Field(default_factory=list, max_length=CHAT_HISTORY_MAX_ITEMS)
    system_prompt: Optional[str] = Field(None, max_length=SYSTEM_PROMPT_MAX_LENGTH,
                                          description="System instruction prepended to history (max 8000 chars)")
    model: Optional[str] = Field(None, max_length=CHAT_MODEL_MAX_LENGTH)
    stream: bool = Field(False)
    request_id: Optional[str] = Field(None, max_length=CHAT_REQUEST_ID_MAX_LENGTH)
    style: Optional[str] = Field("detailed")
    max_tool_steps: Optional[int] = Field(5, ge=1, le=10)
    temperature: Optional[float] = Field(0.3, ge=0.0, le=2.0)
    intent_context: List[Dict[str, Any]] = Field(default_factory=list, max_length=500)
    provider_config: Optional[Dict[str, Any]] = Field(
        None, description="Request-scoped provider credentials from the Java backend"
    )


class AgentV1Request(BaseModel):
    """Agent V1 request — knowledge_base_id and user_id are REQUIRED.

    ``user_id`` comes from the Java backend after session authentication.
    The model CANNOT forge or override it — Python strips any model-supplied
    ``user_id`` from tool input before execution (see ToolRegistry).

    ``capability_profile`` (Agent V1 Step 5):
      - ``null`` / absent → V1.0 (3 read-only KB tools, no approval flow).
      - ``"approval_write"`` → V1.1 write capability.  The agent CAN see
        write_note but the registry gates every write call behind
        approval_required.  Java MUST set this explicitly; the model
        cannot upgrade its own capability.
    """
    message: str = Field(..., min_length=1, max_length=CHAT_MESSAGE_MAX_LENGTH)
    knowledge_base_id: int = Field(..., ge=1, description="REQUIRED — target knowledge base ID")
    user_id: int = Field(..., ge=1, description="REQUIRED — authenticated user ID from Java")
    conversation_id: Optional[int] = Field(None, ge=1)
    history: List[ChatMessage] = Field(default_factory=list, max_length=CHAT_HISTORY_MAX_ITEMS)
    system_prompt: Optional[str] = Field(None, max_length=SYSTEM_PROMPT_MAX_LENGTH,
                                          description="System instruction prepended to history (max 8000 chars)")
    model: Optional[str] = Field(None, max_length=CHAT_MODEL_MAX_LENGTH)
    stream: bool = Field(False)
    request_id: Optional[str] = Field(None, max_length=CHAT_REQUEST_ID_MAX_LENGTH)
    style: Optional[str] = Field("detailed")
    max_tool_steps: Optional[int] = Field(5, ge=1, le=10)
    temperature: Optional[float] = Field(0.3, ge=0.0, le=2.0)
    capability_profile: Optional[str] = Field(None, pattern="^(approval_write)$")
    user_role: Optional[str] = Field(None, pattern="^(user|admin)$",
                                     description="Authenticated user role from Java (user|admin)")
    environment: Optional[str] = Field(None, max_length=32,
                                       description="Deployment environment override")
    intent_context: List[Dict[str, Any]] = Field(default_factory=list, max_length=500)
    provider_config: Optional[Dict[str, Any]] = Field(
        None, description="Request-scoped provider credentials from the Java backend"
    )


class ChatResponse(BaseModel):
    """Chat response — backward-compatible with Java AiClient.ChatResponse.

    JSON keys ``content``, ``token_count``, ``model``, ``sources``, ``steps``,
    and ``auto_detected_kb_id`` are consumed by Java's Jackson mapper.
    Additional V1 keys (``answer``, ``status``, ``agent_run_id``, …) are
    available for V1-aware consumers.
    """

    # ── Java-compat keys (keep these names exactly) ──
    content: str = Field("", description="Final answer text (Markdown) — Java primary field")
    model: str = Field("", description="LLM model used")
    token_count: int = Field(0, description="Token count — Java tokenCount via @JsonProperty")
    sources: List[Dict[str, Any]] = Field(default_factory=list, description="Source citations")
    steps: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Agent ReAct steps")
    auto_detected_kb_id: Optional[int] = Field(None, description="Auto-detected knowledge base ID")

    # ── Agent V1 keys ──
    answer: str = Field("", description="V1 mirror of content")
    status: str = Field("completed", description="completed | insufficient_evidence | tool_error | timeout")
    agent_run_id: Optional[str] = Field(None, description="UUID of the agent run")
    token_usage: Optional[Dict[str, int]] = Field(None, description="{prompt_tokens, completion_tokens, total_tokens}")
    tool_calls_count: int = Field(0, description="Number of tool invocations")
    style_used: str = Field("detailed", description="concise | detailed | report")
    max_tool_steps: int = Field(5, description="Configured max ReAct steps")
    error_detail: Optional[str] = Field(None, description="Error detail on tool_error / timeout")
    failed_tool: Optional[str] = Field(None, description="Tool name that failed")
    step_events: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Structured step events for Java persistence")


# ── Helper ──────────────────────────────────────────────────────────────

def _build_history_with_system_prompt(
    history: List[Dict[str, str]],
    system_prompt: Optional[str],
    current_message: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Prepend system_prompt to history if provided, bypassing the 4000-char
    ChatMessage limit (system prompts can be up to SYSTEM_PROMPT_MAX_LENGTH)."""
    normalized_history = list(history)
    # Java persists the current user turn before calling this API. The agent
    # appends ``current_message`` itself, so forwarding that final history turn
    # duplicates the request and can destabilize local providers.
    if (
        current_message
        and normalized_history
        and normalized_history[-1].get("role") == "user"
        and normalized_history[-1].get("content") == current_message
    ):
        normalized_history.pop()
    if system_prompt and system_prompt.strip():
        return [{"role": "system", "content": system_prompt}] + normalized_history
    return normalized_history


def _resolve_chat_route(request: ChatRequest) -> tuple[Dict[str, Any], Optional[int], Optional[int]]:
    route = resolve_intent_route(
        request.message,
        request.intent_context,
        explicit_knowledge_base_id=request.knowledge_base_id,
    )
    knowledge_base_id = request.knowledge_base_id or route.get("knowledge_base_id")
    return route, knowledge_base_id, route.get("top_k")


def _clarification_response(route: Dict[str, Any], style: str) -> ChatResponse:
    message = route.get("message") or "请先选择一个知识库作为回答范围。"
    return ChatResponse(
        content=message,
        answer=message,
        status="clarification",
        style_used=style,
        auto_detected_kb_id=None,
    )


def _build_chat_response(response, style: str, extra_step_events: Optional[List[Dict[str, Any]]] = None) -> ChatResponse:
    """Build a ChatResponse from AgentResponse, syncing Java and V1 fields.

    When *extra_step_events* is provided (e.g. from the decide/resume flow),
    those events are used directly instead of deriving them from response.steps.
    """
    # ── Content guardrails: output check before returning the response ──
    # Blocks critical injection echoes / inappropriate content and masks PII
    # in the final answer.  Streamed responses (SSE) are not guarded here —
    # the non-streaming path is the single choke point for the Java contract.
    final_text = response.content or response.answer or ""
    safe_text, guard_verdict = _GUARD_POLICY_ENGINE.guard_model_output(
        final_text,
        PolicyContext(
            user_id=0,
            knowledge_base_id=getattr(response, "knowledge_base_id", 0) or 0,
            environment=config.SERVER_ENV,
        ),
    )
    if guard_verdict is not None:
        logger.warning("AI response blocked by guardrails: %s", guard_verdict.reason)
        safe_text = _GUARDED_RESPONSE

    # Build step_events from AgentResponse.steps for Java persistence.
    if extra_step_events is not None:
        step_events = list(extra_step_events)
    else:
        step_events = []
        for i, s in enumerate(response.steps or [], start=1):
            step_events.append({
                "sequence": i,
                "step_type": "tool_call" if s.action else "model_generation",
                "action": s.action,
                "input_summary": _truncate(
                    json.dumps(s.action_input, ensure_ascii=False) if s.action_input else s.thought,
                    _INPUT_SUMMARY_MAX_LENGTH,
                ),
                "output_summary": _truncate(s.observation, _OUTPUT_SUMMARY_MAX_LENGTH),
                "sources": None,
                "duration_ms": 0,
                "error_code": None,
            })

    return ChatResponse(
        # Java-compat
        content=safe_text,
        model=response.model or "",
        token_count=response.token_count,
        sources=response.sources,
        steps=[{
            "thought": s.thought,
            "action": s.action,
            "action_input": s.action_input,
            "observation": s.observation,
        } for s in (response.steps or [])],
        auto_detected_kb_id=response.auto_detected_kb_id,
        # V1
        answer=safe_text,
        status=response.status or "completed",
        agent_run_id=response.agent_run_id,
        token_usage=response.token_usage or {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": response.token_count,
        },
        tool_calls_count=response.tool_calls_count,
        style_used=response.style_used or style,
        max_tool_steps=response.max_tool_steps,
        error_detail=response.error_detail,
        failed_tool=response.failed_tool,
        step_events=step_events,
    )


# ── Routes ──────────────────────────────────────────────────────────────

@router.post("/api/chat")
async def chat(request: ChatRequest):
    """
    General chat — knowledge_base_id is optional.

    For Agent V1 (KB-required, V1 tools only), use ``POST /api/agent/v1/chat``.
    """
    import time as _time
    _start = _time.perf_counter()
    _is_error = False
    try:
        style = request.style if request.style in _VALID_STYLES else "detailed"
        route, routed_knowledge_base_id, route_top_k = _resolve_chat_route(request)
        if route.get("status") == "ambiguous":
            return _clarification_response(route, style)

        history = _build_history_with_system_prompt(
            [{"role": msg.role, "content": msg.content} for msg in request.history],
            request.system_prompt,
            request.message,
        )

        # Build execution context when user_id and KB are both present.
        execution_context = None
        if request.user_id and routed_knowledge_base_id:
            execution_context = AgentExecutionContext(
                user_id=request.user_id,
                knowledge_base_id=routed_knowledge_base_id,
                tenant_id=get_tenant_id(),
                permissions=frozenset({"knowledge_base:read"}),
                agent_run_id=request.request_id or str(uuid4()),
                mode="read_only",
            )

        agent = get_agent(
            knowledge_base_id=routed_knowledge_base_id,
            model=request.model,
            execution_context=execution_context,
            retrieval_top_k=route_top_k,
            llm=build_user_llm(request.provider_config),
        )

        if request.stream:
            async def sse_generator():
                try:
                    async for chunk in agent.run_stream(
                        query=request.message,
                        history=history,
                        style=style,
                        max_tool_steps=request.max_tool_steps,
                    ):
                        event = _agent_chunk_to_sse(chunk)
                        if event is not None:
                            yield event
                except Exception as e:
                    logger.error("Streaming error: %s", e)
                    yield f"data: {json.dumps({'content': '', 'error': str(e)}, ensure_ascii=False)}\n\n"
                finally:
                    yield "data: [DONE]\n\n"

            return StreamingResponse(sse_generator(), media_type="text/event-stream")

        response = await agent.run(
            query=request.message,
            history=history,
            style=style,
            max_tool_steps=request.max_tool_steps,
        )

        return _build_chat_response(response, style)

    except Exception as e:
        _is_error = True
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}") from e
    finally:
        from app.api.metrics import record_chat_request
        record_chat_request(_time.perf_counter() - _start, is_error=_is_error)


@router.post("/api/agent/v1/chat")
async def agent_v1_chat(request: AgentV1Request):
    """
    Agent V1 — knowledge-base research agent.

    ``knowledge_base_id`` and ``user_id`` are REQUIRED.  Returns 422 without them.
    Only V1-whitelisted tools (search_knowledge_base, read_chunk,
    list_document_chunks) are available.

    Agent V1 Step 3: An immutable ``AgentExecutionContext`` is created from
    the Java-supplied fields.  The model cannot forge ``user_id`` or
    ``knowledge_base_id`` — the Registry strips them from tool input.
    """
    import time as _time
    _start = _time.perf_counter()
    _is_error = False
    try:
        style = request.style if request.style in _VALID_STYLES else "detailed"

        history = _build_history_with_system_prompt(
            [{"role": msg.role, "content": msg.content} for msg in request.history],
            request.system_prompt,
            request.message,
        )

        # Agent V1 Step 3: build immutable execution context.
        # V1 is always read_only — write / external tools are rejected by
        # the Registry even if they were registered.
        execution_context = AgentExecutionContext(
            user_id=request.user_id,
            knowledge_base_id=request.knowledge_base_id,
            tenant_id=get_tenant_id(),
            permissions=frozenset({"knowledge_base:read"}),
            agent_run_id=request.request_id or str(uuid4()),
            mode="read_only",
            capability_profile=request.capability_profile,
            user_role=request.user_role or "user",
            environment=request.environment,
        )

        # Agent V1: knowledge_base_id is always present (enforced by Pydantic).
        agent = get_agent(
            knowledge_base_id=request.knowledge_base_id,
            model=request.model,
            execution_context=execution_context,
            llm=build_user_llm(request.provider_config),
        )

        if request.stream:
            async def sse_generator():
                try:
                    async for chunk in agent.run_stream(
                        query=request.message,
                        history=history,
                        style=style,
                        max_tool_steps=request.max_tool_steps,
                    ):
                        event = _agent_chunk_to_sse(chunk)
                        if event is not None:
                            yield event
                except Exception as e:
                    logger.error("Agent V1 streaming error: %s", e)
                    yield f"data: {json.dumps({'content': '', 'error': str(e)}, ensure_ascii=False)}\n\n"
                finally:
                    yield "data: [DONE]\n\n"

            return StreamingResponse(sse_generator(), media_type="text/event-stream")

        response = await agent.run(
            query=request.message,
            history=history,
            style=style,
            max_tool_steps=request.max_tool_steps,
        )

        return _build_chat_response(response, style)

    except Exception as e:
        _is_error = True
        raise HTTPException(status_code=500, detail=f"Agent V1 error: {str(e)}") from e
    finally:
        from app.api.metrics import record_chat_request
        record_chat_request(_time.perf_counter() - _start, is_error=_is_error)


@router.post("/api/agent/v1/chat/stream")
async def agent_v1_chat_stream(request: AgentV1Request):
    """
    Agent V1 streaming — knowledge-base research agent (SSE).

    ``knowledge_base_id`` and ``user_id`` are REQUIRED.  Returns 422 without them.
    Only V1-whitelisted tools (search_knowledge_base, read_chunk,
    list_document_chunks) are available.

    Emits structured agent events (run_started, step_completed, run_completed,
    run_error) alongside content chunks for Java backend persistence.
    """
    try:
        style = request.style if request.style in _VALID_STYLES else "detailed"

        history = _build_history_with_system_prompt(
            [{"role": msg.role, "content": msg.content} for msg in request.history],
            request.system_prompt,
            request.message,
        )

        execution_context = AgentExecutionContext(
            user_id=request.user_id,
            knowledge_base_id=request.knowledge_base_id,
            tenant_id=get_tenant_id(),
            permissions=frozenset({"knowledge_base:read"}),
            agent_run_id=request.request_id or str(uuid4()),
            mode="read_only",
            capability_profile=request.capability_profile,
            user_role=request.user_role or "user",
            environment=request.environment,
        )

        agent = get_agent(
            knowledge_base_id=request.knowledge_base_id,
            model=request.model,
            execution_context=execution_context,
        )

        request_id = request.request_id or str(uuid4())
        agent_run_id = execution_context.agent_run_id

        async def event_generator():
            serving_task = _track_active_request(request_id)
            # Track run-level metrics for run_completed event.
            run_start_time = time_module.monotonic()
            total_tool_calls = 0
            # Track whether a terminal event was already emitted by the agent
            # (run_error from exception handlers, or approval_required).
            _terminal_event_emitted = False

            # Emit run_started event before agent execution.
            yield _agent_chunk_to_sse(_build_run_started_event(agent_run_id))

            try:
                async for chunk in agent.run_stream(
                    query=request.message,
                    history=history,
                    style=style,
                    max_tool_steps=request.max_tool_steps,
                ):
                    # Detect terminal events emitted by the agent itself.
                    try:
                        parsed = json.loads(chunk)
                        if isinstance(parsed, dict):
                            evt = parsed.get("event")
                            if evt in ("run_error", "approval_required"):
                                _terminal_event_emitted = True
                            if evt == "step_completed" and parsed.get("step_type") == "tool_call":
                                total_tool_calls += 1
                    except (json.JSONDecodeError, TypeError, ValueError):
                        pass

                    event = _agent_chunk_to_sse(chunk)
                    if event is not None:
                        yield event

                # Emit run_completed ONLY if no terminal event was emitted.
                if not _terminal_event_emitted:
                    run_duration = (time_module.monotonic() - run_start_time) * 1000
                    yield _agent_chunk_to_sse(_build_run_event(
                        status="completed",
                        agent_run_id=agent_run_id,
                        token_usage=None,  # Will be populated by Java from final response
                        tool_calls_count=total_tool_calls,
                    ))

            except asyncio.CancelledError:
                logger.info("Agent V1 stream %s was cancelled", request_id)
                yield _agent_chunk_to_sse(
                    _build_run_error_event(
                        status="cancelled",
                        error_code="cancelled",
                        error_detail="用户取消",
                        agent_run_id=agent_run_id,
                    )
                )
                yield f"data: {json.dumps({'content': '', 'cancelled': True}, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.error("Agent V1 streaming error for request %s: %s", request_id, e, exc_info=True)
                yield _agent_chunk_to_sse(
                    _build_run_error_event(
                        status="failed",
                        error_code="internal_error",
                        error_detail=str(e)[:500],
                        agent_run_id=agent_run_id,
                    )
                )
                yield f"data: {json.dumps({'content': '', 'error': str(e)}, ensure_ascii=False)}\n\n"
            finally:
                try:
                    yield "data: [DONE]\n\n"
                except Exception:
                    pass
                if active_requests.get(request_id) is serving_task:
                    active_requests.pop(request_id, None)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Request-ID": request_id,
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent V1 stream error: {str(e)}") from e


@router.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """Chat with AI agent (streaming only)."""
    try:
        style = request.style if request.style in _VALID_STYLES else "detailed"
        route, routed_knowledge_base_id, route_top_k = _resolve_chat_route(request)
        request_id = request.request_id or str(uuid4())
        if route.get("status") == "ambiguous":
            async def clarification_stream():
                yield f"data: {json.dumps({'content': route.get('message'), 'route': route}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            return StreamingResponse(
                clarification_stream(), media_type="text/event-stream",
                headers={"X-Request-ID": request_id},
            )

        history = _build_history_with_system_prompt(
            [{"role": msg.role, "content": msg.content} for msg in request.history],
            request.system_prompt,
            request.message,
        )

        agent = get_agent(
            knowledge_base_id=routed_knowledge_base_id,
            model=request.model,
            retrieval_top_k=route_top_k,
        )

        async def event_generator():
            serving_task = _track_active_request(request_id)
            try:
                async for chunk in agent.run_stream(
                    query=request.message,
                    history=history,
                    style=style,
                    max_tool_steps=request.max_tool_steps,
                ):
                    event = _agent_chunk_to_sse(chunk)
                    if event is not None:
                        yield event

            except asyncio.CancelledError:
                logger.info("Request %s was cancelled", request_id)
                yield f"data: {json.dumps({'content': '', 'cancelled': True}, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.error("Streaming error for request %s: %s", request_id, e, exc_info=True)
                yield f"data: {json.dumps({'content': '', 'error': str(e)}, ensure_ascii=False)}\n\n"
            finally:
                try:
                    yield "data: [DONE]\n\n"
                except Exception:
                    pass
                if active_requests.get(request_id) is serving_task:
                    active_requests.pop(request_id, None)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Request-ID": request_id,
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat stream error: {str(e)}") from e


# ── Agent V1 Step 5: Approval endpoints ──────────────────────────────────

class AgentResumeRequest(BaseModel):
    """Resume a paused agent run after approval decision.

    Java passes the full execution context so Python can re-run the agent
    with a scoped grant for the approved tool.  All fields are REQUIRED
    (validated by Java before calling this endpoint).
    """
    approval_id: str = Field(..., min_length=1, max_length=36)
    decision: str = Field(..., pattern="^(approved|denied)$")
    reason: Optional[str] = Field(None, max_length=500)
    user_id: int = Field(..., ge=1, description="Authenticated user ID making the decision")
    knowledge_base_id: int = Field(..., ge=1)
    tool_name: str = Field(..., min_length=1, max_length=50)
    tool_input: Dict[str, Any] = Field(..., description="Original tool parameters (for hash verification)")
    expected_tool_input_hash: Optional[str] = Field(None, min_length=64, max_length=64,
                                                     pattern="^[0-9a-fA-F]{64}$")
    query: str = Field(..., min_length=1, max_length=CHAT_MESSAGE_MAX_LENGTH,
                       description="Original user query (to re-run agent)")
    history: List[ChatMessage] = Field(default_factory=list, max_length=CHAT_HISTORY_MAX_ITEMS)
    conversation_id: Optional[int] = Field(None, ge=1)
    model: Optional[str] = Field(None, max_length=CHAT_MODEL_MAX_LENGTH)
    execution_token: Optional[str] = Field(None, max_length=64,
                                           description="One-time DB token issued by Java on approval (REQUIRED for approved executions)")
    user_role: Optional[str] = Field(None, pattern="^(user|admin)$")
    environment: Optional[str] = Field(None, max_length=32)


@router.post("/api/agent/v1/chat/decide")
async def agent_v1_decide(request: AgentResumeRequest):
    """Approve or deny a pending tool approval — Agent V1 Step 5.

    Called by the Java backend AFTER updating MySQL agent_approval.
    MySQL is the single source of truth; this endpoint handles the
    actual tool execution.

    **Approved flow:**
      1. Validate the approval (parameter hash must match).
      2. Register a one-time scoped grant for (tool_name, tool_input_hash).
      3. Execute the approved tool DIRECTLY via ToolRegistry — NO LLM re-run.
         This guarantees exactly one execution with the exact approved parameters.
      4. Return a structured ChatResponse with step_events.

    **Denied flow:**
      Return ``{status: "denied"}`` — Java has already updated MySQL.
    """
    from app.core.tools.registry import register_scoped_grant, create_v1_registry, consume_scoped_grant
    from app.core.tools.result import ToolResult

    if request.decision == "denied":
        logger.info("Approval %s DENIED by user %d: %s",
                     request.approval_id, request.user_id, request.reason or "")
        return {
            "status": "denied",
            "approval_id": request.approval_id,
            "reason": request.reason,
        }

    # ── Approved: validate, then execute the tool directly ────────────────

    # Step 1: Validate parameter hash.
    input_canonical = json.dumps(request.tool_input, sort_keys=True, ensure_ascii=False,
                                 separators=(",", ":"))
    input_hash = hashlib.sha256(input_canonical.encode("utf-8")).hexdigest()
    if request.expected_tool_input_hash is None:
        raise HTTPException(status_code=400, detail="expected tool input hash is required for approval")
    if not hmac.compare_digest(input_hash, request.expected_tool_input_hash):
        logger.warning("Approval %s parameter hash mismatch", request.approval_id)
        raise HTTPException(status_code=409, detail="approved tool parameters do not match")
    logger.info(
        "Approval %s APPROVED by user %d: tool=%s hash=%s... user=%d kb=%d",
        request.approval_id, request.user_id, request.tool_name,
        input_hash[:16], request.user_id, request.knowledge_base_id,
    )

    # Step 1.5: Consume the one-time execution token BEFORE anything runs.
    # MySQL is the single source of truth: exactly one replica may consume the
    # token; every other attempt (replay / cross-replica / stale) is rejected
    # with 409 and the approved tool is NOT executed.
    from app.core.tools.execution_token import consume_execution_token
    consumed = await consume_execution_token(
        approval_id=request.approval_id,
        execution_token=request.execution_token,
    )
    if not consumed:
        logger.warning(
            "Execution-token not consumed, rejecting approval execution: "
            "approval=%s token_present=%s",
            request.approval_id, bool(request.execution_token),
        )
        raise HTTPException(
            status_code=409,
            detail="execution token is missing, already used, or revoked",
        )

    # Step 2: Create V1.1 registry for the approved KB, then register a
    # one-shot scoped grant so the write tool passes the approval gate.
    registry = create_v1_registry(
        knowledge_base_id=request.knowledge_base_id,
        agent_version="1.1",
    )
    grant_token = register_scoped_grant(
        tool_name=request.tool_name,
        tool_input=request.tool_input,
        user_id=request.user_id,
        knowledge_base_id=request.knowledge_base_id,
    )

    # Step 3: Build a read_write execution context.
    execution_context = AgentExecutionContext(
        user_id=request.user_id,
        knowledge_base_id=request.knowledge_base_id,
        tenant_id=get_tenant_id(),
        permissions=frozenset({"knowledge_base:read", "knowledge_base:write"}),
        agent_run_id=str(uuid4()),
        mode="read_write",
        capability_profile="approval_write",
        user_role=request.user_role or "user",
        environment=request.environment,
    )

    # Step 4: Execute the approved tool DIRECTLY.
    # This is intentionally NOT an agent re-run — we execute exactly the
    # tool+parameters that the human approved, exactly once.  No LLM
    # involvement means no token cost and no non-determinism.
    started = time_module.monotonic()
    try:
        result: ToolResult = await asyncio.wait_for(
            registry.execute(
                tool_name=request.tool_name,
                tool_input=request.tool_input,
                context=execution_context,
            ),
            timeout=30.0,
        )
    except asyncio.TimeoutError:
        elapsed_ms = round((time_module.monotonic() - started) * 1000, 2)
        logger.error(
            "Approval tool execution TIMEOUT: approval=%s tool=%s timeout_ms=%s",
            request.approval_id, request.tool_name, elapsed_ms,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Tool execution timed out after {elapsed_ms}ms: {request.tool_name}",
        )
    except Exception as e:
        elapsed_ms = round((time_module.monotonic() - started) * 1000, 2)
        logger.error(
            "Approval tool execution FAILED: approval=%s tool=%s elapsed_ms=%s error=%s",
            request.approval_id, request.tool_name, elapsed_ms, e, exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Tool execution error: {request.tool_name}: {e}",
        )

    elapsed_ms = round((time_module.monotonic() - started) * 1000, 2)

    # Step 5: Build the response from the tool result.
    style = "detailed"

    if result.ok:
        logger.info(
            "Approval tool executed OK: approval=%s tool=%s elapsed_ms=%s",
            request.approval_id, request.tool_name, elapsed_ms,
        )
        # Build an AgentResponse with the tool result
        step_event = {
            "sequence": 1,
            "step_type": "tool_call",
            "action": request.tool_name,
            "knowledge_base_id": request.knowledge_base_id,
            "input_summary": _truncate(
                build_arguments_summary(request.tool_input),
                _INPUT_SUMMARY_MAX_LENGTH,
            ),
            "output_summary": _truncate(
                json.dumps(result.data, ensure_ascii=False) if result.data else "",
                _OUTPUT_SUMMARY_MAX_LENGTH,
            ),
            "sources": None,
            "duration_ms": elapsed_ms,
            "error_code": None,
        }
        response = AgentResponse(
            content=f"工具 '{request.tool_name}' 执行成功。",
            answer=f"工具 '{request.tool_name}' 执行成功。",
            status="completed",
            sources=[],
            steps=[],
            model=request.model or "",
            token_count=0,
            token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            tool_calls_count=1,
            style_used=style,
            max_tool_steps=5,
            agent_run_id=execution_context.agent_run_id,
            error_detail=None,
            failed_tool=None,
        )
        return _build_chat_response(response, style, extra_step_events=[step_event])
    else:
        logger.error(
            "Approval tool returned FAILURE: approval=%s tool=%s error_code=%s message=%s",
            request.approval_id, request.tool_name, result.error_code, result.message,
        )
        step_event = {
            "sequence": 1,
            "step_type": "tool_call",
            "action": request.tool_name,
            "knowledge_base_id": request.knowledge_base_id,
            "input_summary": _truncate(
                build_arguments_summary(request.tool_input),
                _INPUT_SUMMARY_MAX_LENGTH,
            ),
            "output_summary": _truncate(result.message, _OUTPUT_SUMMARY_MAX_LENGTH),
            "sources": None,
            "duration_ms": elapsed_ms,
            "error_code": result.error_code,
        }
        response = AgentResponse(
            content=f"工具 '{request.tool_name}' 执行失败: {result.message}",
            answer=f"工具 '{request.tool_name}' 执行失败: {result.message}",
            status="tool_error",
            sources=[],
            steps=[],
            model=request.model or "",
            token_count=0,
            token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            tool_calls_count=1,
            style_used=style,
            max_tool_steps=5,
            agent_run_id=execution_context.agent_run_id,
            error_detail=result.message,
            failed_tool=request.tool_name,
        )
        return _build_chat_response(response, style, extra_step_events=[step_event])


# ── Legacy agent-runs (kept for backward compat) ──────────────────────────

@router.get("/api/chat/agent-runs")
async def list_agent_runs(limit: int = 50, knowledge_base_id: Optional[int] = None):
    """Operational metadata only; prompts and retrieved text are never stored."""
    return {"items": get_agent_run_store().list(limit=limit, knowledge_base_id=knowledge_base_id)}


@router.get("/api/chat/agent-runs/{run_id}")
async def get_agent_run(run_id: str):
    run = get_agent_run_store().get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return run


@router.get("/api/chat/health")
async def chat_health():
    """Health check for chat service — Agent V1 aware.

    In addition to LLM availability, reports whether the Agent V1 route
    is registered so operators can detect a stale deployment where the
    service is alive but running old code without the V1 endpoint.
    """
    from app.core.llm import get_llm
    from app.core.tools import AGENT_V1_TOOL_NAMES
    llm = get_llm()
    return {
        "status": "healthy",
        "llm_available": llm.is_available(),
        "llm_model": llm.model if hasattr(llm, "model") else "unknown",
        "agent_v1": {
            "route": "/api/agent/v1/chat",
            "stream_route": "/api/agent/v1/chat/stream",
            "registered": True,
            "contract_version": "1.0",
            "tools": sorted(AGENT_V1_TOOL_NAMES),
        },
    }


@router.post("/api/chat/cancel")
async def cancel_chat(request_id: str):
    """Cancel an ongoing chat request."""
    if request_id in active_requests:
        task = active_requests[request_id]
        if not task.done():
            task.cancel()
            del active_requests[request_id]
            return {"status": "cancelled", "request_id": request_id}
    return {"status": "not_found", "request_id": request_id}
