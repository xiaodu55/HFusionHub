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
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.agent import get_agent, get_agent_run_store

router = APIRouter()
logger = logging.getLogger(__name__)

active_requests: Dict[str, asyncio.Task] = {}

CHAT_MESSAGE_MAX_LENGTH = 4000
CHAT_HISTORY_MAX_ITEMS = 50
CHAT_REQUEST_ID_MAX_LENGTH = 80
CHAT_MODEL_MAX_LENGTH = 100

_VALID_STYLES = {"concise", "detailed", "report"}


def _agent_chunk_to_sse(chunk: str) -> Optional[str]:
    """Convert one agent chunk into a browser-facing SSE event."""
    try:
        parsed = json.loads(chunk)
        if isinstance(parsed, dict):
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
    history: List[ChatMessage] = Field(default_factory=list, max_length=CHAT_HISTORY_MAX_ITEMS)
    model: Optional[str] = Field(None, max_length=CHAT_MODEL_MAX_LENGTH)
    stream: bool = Field(False)
    request_id: Optional[str] = Field(None, max_length=CHAT_REQUEST_ID_MAX_LENGTH)
    style: Optional[str] = Field("detailed")
    max_tool_steps: Optional[int] = Field(5, ge=1, le=10)
    temperature: Optional[float] = Field(0.3, ge=0.0, le=2.0)


class AgentV1Request(BaseModel):
    """Agent V1 request — knowledge_base_id is REQUIRED."""
    message: str = Field(..., min_length=1, max_length=CHAT_MESSAGE_MAX_LENGTH)
    knowledge_base_id: int = Field(..., ge=1, description="REQUIRED — target knowledge base ID")
    conversation_id: Optional[int] = Field(None, ge=1)
    history: List[ChatMessage] = Field(default_factory=list, max_length=CHAT_HISTORY_MAX_ITEMS)
    model: Optional[str] = Field(None, max_length=CHAT_MODEL_MAX_LENGTH)
    stream: bool = Field(False)
    request_id: Optional[str] = Field(None, max_length=CHAT_REQUEST_ID_MAX_LENGTH)
    style: Optional[str] = Field("detailed")
    max_tool_steps: Optional[int] = Field(5, ge=1, le=10)
    temperature: Optional[float] = Field(0.3, ge=0.0, le=2.0)


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


# ── Helper ──────────────────────────────────────────────────────────────

def _build_chat_response(response, style: str) -> ChatResponse:
    """Build a ChatResponse from AgentResponse, syncing Java and V1 fields."""
    return ChatResponse(
        # Java-compat
        content=response.content or response.answer or "",
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
        answer=response.answer or response.content or "",
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
    )


# ── Routes ──────────────────────────────────────────────────────────────

@router.post("/api/chat")
async def chat(request: ChatRequest):
    """
    General chat — knowledge_base_id is optional.

    For Agent V1 (KB-required, V1 tools only), use ``POST /api/agent/v1/chat``.
    """
    try:
        style = request.style if request.style in _VALID_STYLES else "detailed"

        history = [
            {"role": msg.role, "content": msg.content}
            for msg in request.history
        ]

        agent = get_agent(
            knowledge_base_id=request.knowledge_base_id,
            model=request.model,
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
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}") from e


@router.post("/api/agent/v1/chat")
async def agent_v1_chat(request: AgentV1Request):
    """
    Agent V1 — knowledge-base research agent.

    ``knowledge_base_id`` is REQUIRED.  Returns 422 without it.
    Only V1-whitelisted tools (search_knowledge_base, read_chunk,
    list_document_chunks) are available.
    """
    try:
        style = request.style if request.style in _VALID_STYLES else "detailed"

        history = [
            {"role": msg.role, "content": msg.content}
            for msg in request.history
        ]

        # Agent V1: knowledge_base_id is always present (enforced by Pydantic).
        agent = get_agent(
            knowledge_base_id=request.knowledge_base_id,
            model=request.model,
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
        raise HTTPException(status_code=500, detail=f"Agent V1 error: {str(e)}") from e


@router.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """Chat with AI agent (streaming only)."""
    try:
        style = request.style if request.style in _VALID_STYLES else "detailed"

        history = [
            {"role": msg.role, "content": msg.content}
            for msg in request.history
        ]

        agent = get_agent(
            knowledge_base_id=request.knowledge_base_id,
            model=request.model,
        )

        request_id = request.request_id or str(uuid4())

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
