"""
Chat API Routes - Chat with AI agent
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import json

from app.core.agent import get_agent

router = APIRouter()


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


class ChatResponse(BaseModel):
    """Chat response model"""
    content: str = Field(..., description="AI response content")
    model: str = Field("", description="Model used")
    token_count: int = Field(0, description="Token count")
    steps: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Agent steps")


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
            # Streaming response
            return StreamingResponse(
                agent.run_stream(
                    query=request.message,
                    history=history
                ),
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
                ]
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

        # Streaming response
        async def event_generator():
            async for chunk in agent.run_stream(
                query=request.message,
                history=history
            ):
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat stream error: {str(e)}")


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
