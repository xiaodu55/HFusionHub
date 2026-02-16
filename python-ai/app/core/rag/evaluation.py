"""Repeatable retrieval metrics for a project-owned RAG evaluation set."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Protocol


class RetrieverProtocol(Protocol):
    async def retrieve(self, query: str, **kwargs: Any) -> Any:
        ...


@dataclass
class EvaluationCase:
    query: str
    expected_document_ids: List[str]
    case_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationCaseResult:
    case_id: Optional[str]
    query: str
    retrieved_document_ids: List[str]
    expected_document_ids: List[str]
    precision_at_k: float
    recall_at_k: float
    reciprocal_rank: float
    graph_hit: bool = False
    multimodal_hit: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RetrievalEvaluator:
    """Evaluate retrieval without coupling metrics to a vector-store vendor."""

    def __init__(self, retriever: RetrieverProtocol):
        self.retriever = retriever

    async def evaluate(
        self,
        cases: List[EvaluationCase],
        knowledge_base_id: Optional[int],
        top_k: int = 5,
    ) -> Dict[str, Any]:
        if not cases:
            raise ValueError("at least one evaluation case is required")

        results: List[EvaluationCaseResult] = []
        for case in cases:
            retrieval = await self.retriever.retrieve(
                query=case.query,
                knowledge_base_id=knowledge_base_id,
                top_k=top_k,
                enable_rewrite=False,
            )
            retrieved_ids = [str(item.document_id) for item in retrieval.results]
            expected_ids = {str(item) for item in case.expected_document_ids}
            matched_ids = [item for item in retrieved_ids if item in expected_ids]
            graph_hit = any(
                str(item.document_id) in expected_ids
                and (
                    item.source == "graph"
                    or "graph" in (item.metadata.get("channels") or [])
                )
                for item in retrieval.results
            )
            multimodal_hit = any(
                str(item.document_id) in expected_ids
                and bool((item.metadata.get("multimodal") or {}).get("kind"))
                for item in retrieval.results
            )
            first_rank = next(
                (index + 1 for index, item in enumerate(retrieved_ids) if item in expected_ids),
                None,
            )
            results.append(EvaluationCaseResult(
                case_id=case.case_id,
                query=case.query,
                retrieved_document_ids=retrieved_ids,
                expected_document_ids=sorted(expected_ids),
                precision_at_k=round(len(matched_ids) / max(len(retrieved_ids), 1), 4),
                recall_at_k=round(len(set(matched_ids)) / max(len(expected_ids), 1), 4),
                reciprocal_rank=round(1 / first_rank, 4) if first_rank else 0.0,
                graph_hit=graph_hit,
                multimodal_hit=multimodal_hit,
            ))

        count = len(results)
        return {
            "summary": {
                "case_count": count,
                "top_k": top_k,
                "precision_at_k": round(sum(item.precision_at_k for item in results) / count, 4),
                "recall_at_k": round(sum(item.recall_at_k for item in results) / count, 4),
                "mean_reciprocal_rank": round(sum(item.reciprocal_rank for item in results) / count, 4),
                "graph_hit_rate": round(sum(item.graph_hit for item in results) / count, 4),
                "multimodal_hit_rate": round(sum(item.multimodal_hit for item in results) / count, 4),
            },
            "cases": [item.to_dict() for item in results],
        }
