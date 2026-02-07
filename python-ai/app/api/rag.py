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


@router.get("/traces")
async def list_traces(limit: int = Query(default=50, ge=1, le=200)):
    return {"traces": get_trace_store().list(limit)}


@router.get("/traces/stats")
async def trace_stats():
    return get_trace_store().stats()


@router.get("/traces/{trace_id}")
async def get_trace(trace_id: str):
    trace = get_trace_store().get(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Retrieval trace not found")
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
