"""RAG observability and evaluation endpoints."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.rag.evaluation import EvaluationCase, RetrievalEvaluator
from app.core.rag.evaluation_runs import get_evaluation_run_store
from app.core.rag.observability import get_trace_store
from app.core.rag.retriever import get_retriever
from app.core.rag.scoped_graph import get_scoped_graph_store
from app.core.rag.intent_tree_router import resolve_intent_route
from app.utils.config import config

router = APIRouter(prefix="/api/rag", tags=["RAG Observability"])


class EvaluationCaseRequest(BaseModel):
    case_id: Optional[str] = None
    query: str = Field(min_length=1, max_length=4000)
    expected_document_ids: List[str] = Field(min_length=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EvaluationRequest(BaseModel):
    knowledge_base_id: int = Field(ge=1)
    top_k: int = Field(default=5, ge=1, le=20)
    label: Optional[str] = Field(default=None, max_length=120)
    cases: List[EvaluationCaseRequest] = Field(min_length=1, max_length=200)


class RetrievalDebugRequest(BaseModel):
    """Execute one scoped retrieval and return its full diagnostic trace."""

    query: str = Field(min_length=1, max_length=4000)
    knowledge_base_id: int = Field(ge=1)
    top_k: int = Field(default=5, ge=1, le=20)
    conversation_history: Optional[List[Dict[str, Any]]] = Field(default=None, max_length=50)
    enable_rewrite: bool = True


class ProductionEvaluationRequest(BaseModel):
    """One production-equivalent retrieval run with all intermediate output."""

    query: str = Field(min_length=1, max_length=4000)
    knowledge_base_id: Optional[int] = Field(default=None, ge=1)
    top_k: Optional[int] = Field(default=None, ge=1, le=20)
    conversation_history: Optional[List[Dict[str, Any]]] = Field(default=None, max_length=50)
    intent_context: List[Dict[str, Any]] = Field(default_factory=list, max_length=500)
    enable_rewrite: bool = True


@router.get("/traces")
async def list_traces(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=1000),
    knowledge_base_id: int = Query(ge=1),
    error_only: bool = Query(default=False),
    query: Optional[str] = Query(default=None, max_length=4000),
    source: Optional[str] = Query(default=None, max_length=64),
):
    trace_store = get_trace_store()
    return {
        "traces": trace_store.list(
            limit=limit,
            offset=offset,
            query=query,
            knowledge_base_id=knowledge_base_id,
            error_only=error_only,
            source=source,
        ),
        "total": trace_store.count(
            query=query,
            knowledge_base_id=knowledge_base_id,
            error_only=error_only,
            source=source,
        ),
    }


@router.get("/traces/stats")
async def trace_stats(
    days: int = Query(default=7, ge=1, le=30),
    knowledge_base_id: int = Query(ge=1),
):
    # Aggregate only the selected KB.  The gateway authenticates ownership.
    return get_trace_store().stats(
        window_days=days,
        knowledge_base_id=knowledge_base_id,
    )


@router.get("/traces/export")
async def export_traces(
    format: str = Query(default="json", pattern="^(json|csv)$"),
    knowledge_base_id: int = Query(ge=1),
    error_only: bool = Query(default=False),
    query: Optional[str] = Query(default=None, max_length=4000),
    source: Optional[str] = Query(default=None, max_length=64),
):
    try:
        return get_trace_store().export(
            format=format,
            query=query,
            knowledge_base_id=knowledge_base_id,
            error_only=error_only,
            source=source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/traces/{trace_id}")
async def get_trace(trace_id: str, knowledge_base_id: int = Query(ge=1)):
    trace = get_trace_store().get(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Retrieval trace not found")
    if trace.get("knowledge_base_id") != knowledge_base_id:
        raise HTTPException(status_code=404, detail="Retrieval trace not found")
    return trace


@router.post("/debug/search")
async def debug_search(request: RetrievalDebugRequest):
    """Run an explicitly scoped retrieval and expose why each result survived."""
    retrieval = await get_retriever().retrieve(
        query=request.query,
        knowledge_base_id=request.knowledge_base_id,
        conversation_history=request.conversation_history,
        top_k=request.top_k,
        enable_rewrite=request.enable_rewrite,
    )
    trace_id = retrieval.metadata.get("trace_id")
    trace = get_trace_store().get(trace_id) if trace_id else None
    if trace is None:
        raise HTTPException(status_code=500, detail="Retrieval debug trace was not recorded")
    return trace


@router.post("/eval")
async def evaluate_production_path(request: ProductionEvaluationRequest):
    """Run the exact production router/retriever chain without answer generation."""
    route = resolve_intent_route(
        request.query,
        request.intent_context,
        explicit_knowledge_base_id=request.knowledge_base_id,
    )
    if route.get("status") == "ambiguous":
        return {
            "status": "clarification_required",
            "route": route,
            "retrieval": None,
        }
    knowledge_base_id = request.knowledge_base_id or route.get("knowledge_base_id")
    if not knowledge_base_id:
        return {
            "status": "no_knowledge_route",
            "route": route,
            "retrieval": None,
        }
    top_k = request.top_k or route.get("top_k") or 5
    retrieval = await get_retriever().retrieve(
        query=request.query,
        knowledge_base_id=knowledge_base_id,
        conversation_history=request.conversation_history,
        top_k=top_k,
        enable_rewrite=request.enable_rewrite,
    )
    trace_id = retrieval.metadata.get("trace_id")
    trace = get_trace_store().get(trace_id) if trace_id else None
    return {
        "status": "completed",
        "route": route,
        "knowledge_base_id": knowledge_base_id,
        "top_k": top_k,
        "query_rewrite": retrieval.metadata.get("rewritten_queries", [request.query]),
        "retrieval": {
            "trace_id": trace_id,
            "results": [
                {
                    "document_id": item.document_id,
                    "content": item.content,
                    "score": item.score,
                    "source": item.source,
                    "outline_path": item.outline_path,
                }
                for item in retrieval.results
            ],
            "reranker": retrieval.metadata.get("reranker"),
            "trace": trace,
        },
    }


@router.get("/graph/status")
async def graph_status(knowledge_base_id: int = Query(ge=1)):
    """Expose only aggregate graph counts for one explicitly selected KB."""
    return {
        **get_scoped_graph_store(config.RAG_GRAPH_INDEX_PATH).stats(knowledge_base_id),
        "enabled": config.RAG_GRAPH_ENABLED,
        "source_backed_only": True,
    }


@router.post("/evaluate")
async def evaluate_retrieval(request: EvaluationRequest):
    evaluator = RetrievalEvaluator(get_retriever())
    cases = [
        EvaluationCase(
            case_id=item.case_id,
            query=item.query,
            expected_document_ids=item.expected_document_ids,
            metadata=item.metadata,
        )
        for item in request.cases
    ]
    try:
        report = await evaluator.evaluate(
            cases=cases,
            knowledge_base_id=request.knowledge_base_id,
            top_k=request.top_k,
        )
        run = get_evaluation_run_store().record(
            report,
            knowledge_base_id=request.knowledge_base_id,
            label=request.label,
        )
        return {**report, "run": run.to_dict()}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/evaluation-runs")
async def list_evaluation_runs(
    limit: int = Query(default=50, ge=1, le=200),
    knowledge_base_id: int = Query(ge=1),
):
    """Return durable metric history and sanitized failed-case identifiers."""
    return {
        "runs": get_evaluation_run_store().list(
            limit=limit,
            knowledge_base_id=knowledge_base_id,
        )
    }


class AnswerJudgeRequest(BaseModel):
    """在线答案评测（LLM-as-judge，无需标准答案）。"""
    query: str = Field(..., min_length=1, max_length=4000)
    answer: str = Field(..., min_length=1, max_length=8000)
    context: str = Field("", max_length=20000, description="检索到的参考上下文（可空）")
    model: Optional[str] = Field(None, max_length=160, description="评测模型（空=系统默认）")


@router.post("/evaluate/answer-judge")
async def judge_answer(request: AnswerJudgeRequest):
    """在线评测回答质量：使用 LLM 作为裁判对回答打分（C3）。

    返回各维度得分（completeness/accuracy/clarity）与综合分，以及
    是否建议改进（verdict）。上下文与答案中不含密钥等敏感信息。
    """
    from app.core.rag.answer_quality_evaluator import (
        EvaluationSample,
        EvaluationStatus,
        EvaluationStrategyType,
        get_evaluator,
    )

    evaluator = get_evaluator(strategy_type=EvaluationStrategyType.LLM_BASED, model=request.model)
    sample = EvaluationSample(
        query_id="online-judge",
        query=request.query,
        response=request.answer,
        context=request.context,
        ground_truth=None,  # 无标准答案模式
    )
    result = await evaluator.evaluate(sample)
    if result.status != EvaluationStatus.COMPLETED:
        raise HTTPException(status_code=502, detail=result.error_message or "评测失败")
    overall = result.overall_score
    verdict = "good" if overall >= 0.7 else ("medium" if overall >= 0.4 else "poor")
    return {
        "status": "completed",
        "overall_score": round(overall, 3),
        "scores": {k: round(v, 3) for k, v in result.scores.items()},
        "verdict": verdict,
        "strategy": result.strategy_used,
    }
