"""招投标垂直化 API —— 招标文件智能解读。

``POST /api/bid/interpret``
    Java ``AiClient.bidInterpret`` 调用入口。返回结构化解读结果：
    ``{status, elements, scoring_methods, requirements, warning?}``，
    由 Java ``BidProjectServiceImpl.interpret()`` 落库为
    ``tender_element`` / ``bid_scoring_method`` / ``bid_requirement``。

契约约定：
    - status == "ok"      解读成功（即使 corpus 为空也返回 ok + warning）
    - status == "error"   解读服务不可用，Java 侧抛出 BusinessException
    - 每条要素携带 evidence_chunk_ids（真实 chunk_id），供前端追溯
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.bid.workflow import BidInterpretWorkflow

router = APIRouter()
logger = logging.getLogger(__name__)


class BidInterpretRequest(BaseModel):
    project_id: int = Field(..., description="投标项目 ID")
    knowledge_base_id: int = Field(..., description="招标文件知识库 ID（须已完成向量化）")
    title: str = Field(..., description="招标项目名称")
    tender_number: Optional[str] = Field(None, description="招标编号（可选）")


@router.post("/api/bid/interpret")
async def bid_interpret(request: BidInterpretRequest):
    """解读招标文件知识库，产出结构化要素 / 评分办法 / 需求清单。"""
    workflow = BidInterpretWorkflow()
    try:
        payload = await workflow.run(
            project_id=request.project_id,
            knowledge_base_id=request.knowledge_base_id,
            title=request.title,
            tender_number=request.tender_number,
        )
    except Exception as exc:  # 工作流整体失败 → 服务不可用
        logger.exception("bid interpret failed for project=%s", request.project_id)
        return {"status": "error", "message": f"解读服务不可用: {exc}"}
    payload["project_id"] = request.project_id
    return payload
