"""Internal memory API — 供 Java 后端回调的长期记忆端点（X-Internal-Token 保护）。

- ``POST /api/internal/memory/consolidate``：会话删除前由 Java 异步回调，
  携带该会话的消息快照；Python 跑 LLM 记忆抽取并把结果回写 Java
  （POST /api/internal/memory/entries，由 InternalMemoryController 落
  memory_entry 表）。会话记录本身已随删除流程清除，记忆条目按用户维度
  存续，供后续对话注入。

对话进行中的"每 N 轮"触发在 app/api/chat.py 流式收尾处完成，不走本端点。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.rag.long_term_memory import get_long_term_memory

router = APIRouter()
logger = logging.getLogger(__name__)

_CONSOLIDATE_MAX_MESSAGES = 100
_MESSAGE_MAX_CHARS = 4000


class ConsolidateMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=_MESSAGE_MAX_CHARS)


class MemoryConsolidateRequest(BaseModel):
    """Java ConversationServiceImpl.delete 前快照的会话消息。"""

    conversation_id: int = Field(..., ge=1)
    user_id: int = Field(..., ge=1, description="Java 会话态解析出的用户 ID")
    knowledge_base_id: int | None = Field(None, ge=1)
    tenant_id: int | None = Field(None, ge=1)
    messages: list[ConsolidateMessage] = Field(..., max_length=_CONSOLIDATE_MAX_MESSAGES)


@router.post("/api/internal/memory/consolidate")
async def consolidate_memory(request: MemoryConsolidateRequest) -> dict[str, Any]:
    """对被删除会话的消息快照执行记忆抽取并回写 Java（调用方 fire-and-forget）。"""
    service = get_long_term_memory()
    if not service.is_enabled(user_id=request.user_id, tenant_id=request.tenant_id):
        return {"enabled": False, "saved": 0}
    result = await service.consolidate_conversation(
        conversation_id=request.conversation_id,
        user_id=request.user_id,
        messages=[m.model_dump() for m in request.messages],
        knowledge_base_id=request.knowledge_base_id,
        tenant_id=request.tenant_id,
    )
    if result is None:
        return {"enabled": True, "saved": 0, "skipped": "no_entries_or_too_short"}
    return {"enabled": True, **result}
