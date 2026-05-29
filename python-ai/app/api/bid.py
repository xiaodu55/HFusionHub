"""招投标垂直化 API —— 招标解读 / 标书撰写 / 废标自检。

``POST /api/bid/interpret``
    Java ``AiClient.bidInterpret`` 调用入口。返回结构化解读结果：
    ``{status, elements, scoring_methods, requirements, warning?}``，
    由 Java ``BidProjectServiceImpl.interpret()`` 落库为
    ``tender_element`` / ``bid_scoring_method`` / ``bid_requirement``。

``POST /api/bid/write``
    Java ``AiClient.bidWrite`` 调用入口。按分节撰写标书草稿：
    ``{status, sections:[{section_key, section_title, content, evidence_chunk_ids}]}``，
    由 Java 落库为 ``bid_draft``（按 project+section 幂等覆盖、版本递增）。

``POST /api/bid/write/stream``
    长文 SSE 流式撰写（P1-2 核心）。事件契约：
    - run_started → (bid_section_started / bid_section_completed)×N → run_completed
    - run_completed 携带全量 sections（Java 一并落库）
    - 失败时 run_error + 终帧 [DONE]

``POST /api/bid/check``
    Java ``AiClient.bidCheck`` 调用入口。废标风险自检：
    ``{status, findings:[{severity, category, section_key, finding, evidence_chunk_ids, suggested_fix}], summary}``，
    由 Java 落库为 ``bid_check_report``。

契约约定：
    - status == "ok"      成功（即使 corpus 为空也返回 ok + warning/空结果）
    - status == "error"   服务不可用，Java 侧抛出 BusinessException
    - 每节/每条 finding 携带 evidence_chunk_ids（真实 chunk_id），供前端追溯
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.bid.check_workflow import BidCheckWorkflow
from app.core.bid.workflow import BidInterpretWorkflow
from app.core.bid.write_workflow import BidWriteWorkflow

router = APIRouter()
logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sse(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ── 请求模型 ────────────────────────────────────────────────────────


class BidInterpretRequest(BaseModel):
    project_id: int = Field(..., description="投标项目 ID")
    knowledge_base_id: int = Field(..., description="招标文件知识库 ID（须已完成向量化）")
    title: str = Field(..., description="招标项目名称")
    tender_number: Optional[str] = Field(None, description="招标编号（可选）")


class BidRequirementItem(BaseModel):
    category: str = Field(..., description="需求类别")
    requirement: str = Field(..., description="需求描述")
    source_clause: Optional[str] = Field(None, description="来源条款原文")


class BidSectionDef(BaseModel):
    key: str = Field(..., description="分节键")
    title: str = Field(..., description="分节标题")


class BidWriteRequest(BaseModel):
    project_id: int = Field(..., description="投标项目 ID")
    title: str = Field(..., description="招标项目名称")
    tender_number: Optional[str] = Field(None, description="招标编号（可选）")
    knowledge_base_ids: List[int] = Field(default_factory=list, description="招标库+资质库+历史库 ID")
    requirements: List[BidRequirementItem] = Field(default_factory=list, description="已确认需求清单")
    section_defs: Optional[List[BidSectionDef]] = Field(None, description="分节定义（可空=默认四节）")


class BidSectionItem(BaseModel):
    section_key: str = Field(..., description="分节键")
    section_title: Optional[str] = Field(None, description="分节标题")
    content: str = Field(default="", description="分节正文")


class BidCheckRequest(BaseModel):
    project_id: int = Field(..., description="投标项目 ID")
    title: str = Field(..., description="招标项目名称")
    tender_number: Optional[str] = Field(None, description="招标编号（可选）")
    knowledge_base_ids: List[int] = Field(default_factory=list, description="招标文件知识库 ID")
    sections: List[BidSectionItem] = Field(default_factory=list, description="待自检标书分节")
    requirements: Optional[List[BidRequirementItem]] = Field(None, description="需求清单（可选）")


# ── 解读 ────────────────────────────────────────────────────────────


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


# ── 撰写 ────────────────────────────────────────────────────────────


@router.post("/api/bid/write")
async def bid_write(request: BidWriteRequest):
    """按分节撰写标书草稿（同步），返回全部分节。"""
    workflow = BidWriteWorkflow()
    try:
        payload = await workflow.run(
            project_id=request.project_id,
            title=request.title,
            tender_number=request.tender_number,
            requirements=[r.model_dump() for r in request.requirements],
            knowledge_base_ids=request.knowledge_base_ids,
            section_defs=[s.model_dump() for s in request.section_defs] if request.section_defs else None,
        )
    except Exception as exc:  # 工作流整体失败 → 服务不可用
        logger.exception("bid write failed for project=%s", request.project_id)
        return {"status": "error", "message": f"撰写服务不可用: {exc}"}
    payload["project_id"] = request.project_id
    return payload


@router.post("/api/bid/write/stream")
async def bid_write_stream(request: BidWriteRequest):
    """长文 SSE 流式撰写标书：逐节推送 start/completed 事件，收尾 run_completed。"""
    workflow = BidWriteWorkflow()

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()

        async def on_section_start(section: Dict[str, Any]) -> None:
            await queue.put({"event": "bid_section_started", **section, "timestamp": _now_iso()})

        async def on_section(payload: Dict[str, Any]) -> None:
            await queue.put({"event": "bid_section_completed", **payload, "timestamp": _now_iso()})

        async def consume() -> None:
            try:
                payload = await workflow.run(
                    project_id=request.project_id,
                    title=request.title,
                    tender_number=request.tender_number,
                    requirements=[r.model_dump() for r in request.requirements],
                    knowledge_base_ids=request.knowledge_base_ids,
                    section_defs=[s.model_dump() for s in request.section_defs]
                    if request.section_defs
                    else None,
                    on_section_start=on_section_start,
                    on_section=on_section,
                )
                await queue.put({"event": "run_completed", "status": "ok", "sections": payload["sections"],
                                 "timestamp": _now_iso()})
            except Exception as exc:
                logger.exception("bid write stream failed for project=%s", request.project_id)
                await queue.put({"event": "run_error", "error_code": "bid_write_error",
                                 "error_detail": str(exc), "timestamp": _now_iso()})
            finally:
                await queue.put({"__done__": True})

        task = asyncio.create_task(consume())
        try:
            yield _sse({"event": "run_started", "project_id": request.project_id,
                        "timestamp": _now_iso()})
            while True:
                item = await queue.get()
                if item.get("__done__"):
                    break
                yield _sse(item)
            yield "data: [DONE]\n\n"
        finally:
            task.cancel()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── 废标自检 ────────────────────────────────────────────────────────


@router.post("/api/bid/check")
async def bid_check(request: BidCheckRequest):
    """废标风险自检：确定性规则 + LLM 语义检查，产出 findings + summary。"""
    workflow = BidCheckWorkflow()
    try:
        payload = await workflow.run(
            project_id=request.project_id,
            title=request.title,
            tender_number=request.tender_number,
            sections=[s.model_dump() for s in request.sections],
            knowledge_base_ids=request.knowledge_base_ids,
            requirements=[r.model_dump() for r in request.requirements]
            if request.requirements
            else None,
        )
    except Exception as exc:  # 工作流整体失败 → 服务不可用
        logger.exception("bid check failed for project=%s", request.project_id)
        return {"status": "error", "message": f"自检服务不可用: {exc}"}
    payload["project_id"] = request.project_id
    return payload
