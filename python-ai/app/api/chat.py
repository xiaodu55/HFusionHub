"""
Chat API Routes - Chat with AI agent
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
    """Register the task serving an SSE stream so the cancel endpoint can stop it."""
    task = asyncio.current_task()
    if task is not None:
        active_requests[request_id] = task
    return task


class ChatMessage(BaseModel):
    """Chat message model"""

    role: Literal["user", "assistant", "system"] = Field(..., description="Message role")
    content: str = Field(..., min_length=1, max_length=CHAT_MESSAGE_MAX_LENGTH, description="Message content")


class ChatRequest(BaseModel):
    """Chat request model"""

    message: str = Field(..., min_length=1, max_length=CHAT_MESSAGE_MAX_LENGTH, description="User message")
    conversation_id: Optional[int] = Field(None, ge=1, description="Conversation ID")
    knowledge_base_id: Optional[int] = Field(None, ge=1, description="Knowledge base ID for RAG")
    history: List[ChatMessage] = Field(default_factory=list, max_length=CHAT_HISTORY_MAX_ITEMS, description="Chat history")
    model: Optional[str] = Field(None, max_length=CHAT_MODEL_MAX_LENGTH, description="LLM model name")
    stream: bool = Field(False, description="Enable streaming response")
    request_id: Optional[str] = Field(None, max_length=CHAT_REQUEST_ID_MAX_LENGTH, description="Request ID for cancellation tracking")


class ChatResponse(BaseModel):
    """Chat response model"""

    content: str = Field(..., description="AI response content")
    model: str = Field("", description="Model used")
    token_count: int = Field(0, description="Token count")
    steps: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Agent steps")
    sources: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Knowledge sources used in response")
    auto_detected_kb_id: Optional[int] = Field(None, description="Auto-detected knowledge base ID if none was selected")
    agent_run_id: Optional[str] = Field(None, description="P9 bounded agent workflow run ID")
    agent_status: Optional[str] = Field(None, description="P9 bounded agent workflow status")


@router.post("/api/chat")
async def chat(request: ChatRequest):
    """
    Chat with AI agent.

    Supports both regular and streaming responses.
    """
    try:
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
                    ):
                        event = _agent_chunk_to_sse(chunk)
                        if event is not None:
                            yield event
                except Exception as e:
                    logger.error("Streaming error: %s", e)
                    yield f"data: {json.dumps({'content': '', 'error': str(e)}, ensure_ascii=False)}\n\n"
                finally:
                    yield "data: [DONE]\n\n"

            return StreamingResponse(
                sse_generator(),
                media_type="text/event-stream",
            )

        response = await agent.run(
            query=request.message,
            history=history,
        )

        return ChatResponse(
            content=response.content,
            model=response.model,
            token_count=response.token_count,
            steps=[
                {
                    "thought": step.thought,
                    "action": step.action,
                    "action_input": step.action_input,
                    "observation": step.observation,
                }
                for step in response.steps
            ],
            sources=response.sources,
            auto_detected_kb_id=response.auto_detected_kb_id,
            agent_run_id=response.agent_run_id,
            agent_status=response.agent_status,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}") from e


@router.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """Chat with AI agent (streaming only)."""
    try:
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
    """Health check for chat service"""
    from app.core.llm import get_llm

    llm = get_llm()
    return {
        "status": "healthy",
        "llm_available": llm.is_available(),
        "llm_model": llm.model if hasattr(llm, "model") else "unknown",
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
