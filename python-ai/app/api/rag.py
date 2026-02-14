"""RAG observability and evaluation endpoints."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.rag.evaluation import EvaluationCase, RetrievalEvaluator
from app.core.rag.observability import get_trace_store
from app.core.rag.retriever import get_retriever

router = APIRouter(prefix="/api/rag", tags=["RAG Observability"])


class EvaluationCaseRequest(BaseModel):
    case_id: Optional[str] = None
    query: str = Field(min_length=1, max_length=4000)
    expected_document_ids: List[str] = Field(min_length=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EvaluationRequest(BaseModel):
    knowledge_base_id: Optional[int] = None
    top_k: int = Field(default=5, ge=1, le=20)
    cases: List[EvaluationCaseRequest] = Field(min_length=1, max_length=200)


class RetrievalDebugRequest(BaseModel):
    """Execute one scoped retrieval and return its full diagnostic trace."""

    query: str = Field(min_length=1, max_length=4000)
    knowledge_base_id: int = Field(ge=1)
    top_k: int = Field(default=5, ge=1, le=20)
    conversation_history: Optional[List[Dict[str, Any]]] = Field(default=None, max_length=50)
    enable_rewrite: bool = True


@router.get("/traces")
async def list_traces(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=1000),
    knowledge_base_id: Optional[int] = Query(default=None, ge=1),
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
async def trace_stats(days: int = Query(default=7, ge=1, le=30)):
    return get_trace_store().stats(window_days=days)


@router.get("/traces/export")
async def export_traces(
    format: str = Query(default="json", pattern="^(json|csv)$"),
    knowledge_base_id: Optional[int] = Query(default=None, ge=1),
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
async def get_trace(trace_id: str):
    trace = get_trace_store().get(trace_id)
    if trace is None:
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
        return await evaluator.evaluate(
            cases=cases,
            knowledge_base_id=request.knowledge_base_id,
            top_k=request.top_k,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
