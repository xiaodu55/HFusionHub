"""
Chat API Routes - Chat with AI agent
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import json
import asyncio
import logging
from uuid import uuid4

from app.core.agent import get_agent, get_agent_run_store

router = APIRouter()
logger = logging.getLogger(__name__)

# 存储活跃的请求任务，用于取消操作
active_requests: Dict[str, asyncio.Task] = {}


def _track_active_request(request_id: str) -> Optional[asyncio.Task]:
    """Register the task serving an SSE stream so the cancel endpoint can stop it."""
    task = asyncio.current_task()
    if task is not None:
        active_requests[request_id] = task
    return task


class ChatMessage(BaseModel):
    """Chat message model"""
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    """Chat request model"""
    message: str = Field(..., description="User message")
    conversation_id: Optional[int] = Field(None, description="Conversation ID")
    knowledge_base_id: Optional[int] = Field(None, description="Knowledge base ID for RAG")
    history: Optional[List[ChatMessage]] = Field(default_factory=list, description="Chat history")
    model: Optional[str] = Field(None, description="LLM model name")
    stream: bool = Field(False, description="Enable streaming response")
    request_id: Optional[str] = Field(None, description="Request ID for cancellation tracking")


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
    Chat with AI agent

    Supports both regular and streaming responses
    """
    try:
        # Convert history to dict format
        history = [
            {"role": msg.role, "content": msg.content}
            for msg in request.history
        ]

        # Get agent instance
        agent = get_agent(
            knowledge_base_id=request.knowledge_base_id,
            model=request.model
        )

        if request.stream:
            # Streaming response with SSE format
            async def sse_generator():
                try:
                    async for chunk in agent.run_stream(
                        query=request.message,
                        history=history
                    ):
                        # 检查是否是 JSON 格式的 sources 信息
                        try:
                            parsed = json.loads(chunk)
                            if isinstance(parsed, dict) and "sources" in parsed:
                                # sources 信息，按原始格式发送
                                yield f"data: {chunk}\n\n"
                                continue
                        except (json.JSONDecodeError, ValueError):
                            pass
                        # 普通内容，包装为 SSE 格式
                        yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
                except Exception as e:
                    logger.error(f"Streaming error: {e}")
                    yield f"data: {json.dumps({'content': '', 'error': str(e)}, ensure_ascii=False)}\n\n"
                finally:
                    yield "data: [DONE]\n\n"

            return StreamingResponse(
                sse_generator(),
                media_type="text/event-stream"
            )
        else:
            # Regular response
            response = await agent.run(
                query=request.message,
                history=history
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
                        "observation": step.observation
                    }
                    for step in response.steps
                ],
                sources=response.sources,
                auto_detected_kb_id=response.auto_detected_kb_id,
                agent_run_id=response.agent_run_id,
                agent_status=response.agent_status,
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")


@router.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Chat with AI agent (streaming only)
    """
    try:
        # Convert history to dict format
        history = [
            {"role": msg.role, "content": msg.content}
            for msg in request.history
        ]

        # Get agent instance
        agent = get_agent(
            knowledge_base_id=request.knowledge_base_id,
            model=request.model
        )

        # Generate request ID if not provided
        request_id = request.request_id or str(uuid4())

        # 直接流式响应（真正的流式）
        async def event_generator():
            serving_task = _track_active_request(request_id)
            try:
                async for chunk in agent.run_stream(
                    query=request.message,
                    history=history
                ):
                    # 检查是否是 JSON 格式的 sources 信息
                    try:
                        parsed = json.loads(chunk)
                        # 处理包含 sources 的事件（必须是 dict 类型）
                        if isinstance(parsed, dict) and "sources" in parsed and parsed["sources"]:
                            # 发送 sources 事件
                            yield f"data: {json.dumps({'sources': parsed['sources']}, ensure_ascii=False)}\n\n"
                            continue
                    except (json.JSONDecodeError, ValueError):
                        pass

                    # 普通内容 chunk
                    yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"

            except asyncio.CancelledError:
                logger.info(f"Request {request_id} was cancelled")
                yield f"data: {json.dumps({'content': '', 'cancelled': True}, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.error(f"Streaming error for request {request_id}: {e}", exc_info=True)
                yield f"data: {json.dumps({'content': '', 'error': str(e)}, ensure_ascii=False)}\n\n"
            finally:
                # 确保 [DONE] 总是被发送
                try:
                    yield "data: [DONE]\n\n"
                except Exception:
                    pass
                # 清理活跃请求
                if active_requests.get(request_id) is serving_task:
                    active_requests.pop(request_id, None)

        # 直接返回流式响应，不预收集
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Request-ID": request_id
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat stream error: {str(e)}")


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
        "llm_model": llm.model if hasattr(llm, 'model') else "unknown"
    }


@router.post("/api/chat/cancel")
async def cancel_chat(request_id: str):
    """
    Cancel an ongoing chat request

    Args:
        request_id: The request ID to cancel
    """
    if request_id in active_requests:
        task = active_requests[request_id]
        if not task.done():
            task.cancel()
            del active_requests[request_id]
            return {"status": "cancelled", "request_id": request_id}
    return {"status": "not_found", "request_id": request_id}
