"""Offline, deterministic evaluation for scoped RAG retrieval.

This module deliberately evaluates the router output rather than a particular
vector-store implementation.  A small JSONL suite can therefore catch a
retrieval-quality regression before it reaches a knowledge-base chat.
"""

import asyncio
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol, Sequence


class Router(Protocol):
    """The narrow interface needed by the offline evaluator."""

    async def search(self, query: str, knowledge_base_id: int, top_k: int):
        ...


@dataclass(frozen=True)
class RetrievalCase:
    """One query and its ground-truth chunks within one knowledge base."""

    case_id: str
    query: str
    knowledge_base_id: int
    relevant_chunk_ids: set[str]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RetrievalCase":
        required = {"id", "query", "knowledge_base_id", "relevant_chunk_ids"}
        missing = required - value.keys()
        if missing:
            raise ValueError(f"evaluation case missing required fields: {sorted(missing)}")
        if not isinstance(value["relevant_chunk_ids"], list) or not value["relevant_chunk_ids"]:
            raise ValueError("relevant_chunk_ids must be a non-empty list")
        return cls(
            case_id=str(value["id"]),
            query=str(value["query"]),
            knowledge_base_id=int(value["knowledge_base_id"]),
            relevant_chunk_ids={str(chunk_id) for chunk_id in value["relevant_chunk_ids"]},
        )


@dataclass(frozen=True)
class CaseEvaluation:
    case_id: str
    retrieved_chunk_ids: list[str]
    relevant_retrieved: int
    first_relevant_rank: int | None
    scope_violations: int


@dataclass(frozen=True)
class RetrievalReport:
    case_count: int
    recall_at_k: float
    hit_rate_at_k: float
    mrr_at_k: float
    ndcg_at_k: float
    scope_violation_count: int
    cases: list[CaseEvaluation]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_cases(path: Path) -> list[RetrievalCase]:
    """Load a version-controlled JSONL ground-truth suite."""
    cases: list[RetrievalCase] = []
    seen_ids: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            case = RetrievalCase.from_dict(json.loads(line))
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            raise ValueError(f"invalid evaluation case at {path}:{line_number}: {error}") from error
        if case.case_id in seen_ids:
            raise ValueError(f"duplicate evaluation case id: {case.case_id}")
        seen_ids.add(case.case_id)
        cases.append(case)
    if not cases:
        raise ValueError("evaluation suite must contain at least one case")
    return cases


class RetrievalEvaluator:
    """Calculate ranking quality and detect knowledge-base scope regressions."""

    def __init__(self, router: Router, top_k: int = 5, metadata_filter: dict | None = None):
        if top_k < 1:
            raise ValueError("top_k must be positive")
        self.router = router
        self.top_k = top_k
        # 可选元数据过滤（如主体级 ACL 的 {"visibility": [...]}）：离线评测默认
        # 不过滤以保持既有基线可比；需要按主体视角评测时由调用方显式传入。
        self.metadata_filter = metadata_filter

    async def evaluate(self, cases: Sequence[RetrievalCase]) -> RetrievalReport:
        if not cases:
            raise ValueError("at least one evaluation case is required")

        case_reports = [await self._evaluate_case(case) for case in cases]
        retrieved_relevant = sum(case.relevant_retrieved for case in case_reports)
        total_relevant = sum(len(case.relevant_chunk_ids) for case in cases)
        return RetrievalReport(
            case_count=len(cases),
            recall_at_k=retrieved_relevant / total_relevant,
            hit_rate_at_k=sum(case.first_relevant_rank is not None for case in case_reports) / len(cases),
            mrr_at_k=sum(
                1 / case.first_relevant_rank if case.first_relevant_rank is not None else 0
                for case in case_reports
            ) / len(cases),
            ndcg_at_k=sum(
                self._ndcg(case, expected.relevant_chunk_ids)
                for case, expected in zip(case_reports, cases)
            ) / len(cases),
            scope_violation_count=sum(case.scope_violations for case in case_reports),
            cases=case_reports,
        )

    async def _evaluate_case(self, case: RetrievalCase) -> CaseEvaluation:
        # 仅在显式配置过滤时下发 metadata_filter，保持与既有 Router/评测
        # 契约的兼容（无过滤时调用面与历史完全一致）。
        search_kwargs: dict = {
            "query": case.query,
            "knowledge_base_id": case.knowledge_base_id,
            "top_k": self.top_k,
        }
        if self.metadata_filter is not None:
            search_kwargs["metadata_filter"] = self.metadata_filter
        merged = await self.router.search(**search_kwargs)
        retrieved_chunk_ids: list[str] = []
        scope_violations = 0
        seen_chunk_ids: set[str] = set()
        for result in merged.results:
            metadata = result.metadata or {}
            if metadata.get("knowledge_base_id") != case.knowledge_base_id:
                scope_violations += 1
            chunk_id = metadata.get("chunk_id")
            if chunk_id is None:
                continue
            chunk_id = str(chunk_id)
            if chunk_id not in seen_chunk_ids:
                seen_chunk_ids.add(chunk_id)
                retrieved_chunk_ids.append(chunk_id)

        relevant_positions = [
            rank for rank, chunk_id in enumerate(retrieved_chunk_ids, start=1)
            if chunk_id in case.relevant_chunk_ids
        ]
        return CaseEvaluation(
            case_id=case.case_id,
            retrieved_chunk_ids=retrieved_chunk_ids,
            relevant_retrieved=len(relevant_positions),
            first_relevant_rank=min(relevant_positions, default=None),
            scope_violations=scope_violations,
        )

    def _ndcg(self, case: CaseEvaluation, relevant_chunk_ids: Iterable[str]) -> float:
        relevant_count = len(set(relevant_chunk_ids))
        if not relevant_count:
            return 0.0
        dcg = sum(
            1 / math.log2(rank + 1)
            for rank, chunk_id in enumerate(case.retrieved_chunk_ids, start=1)
            if chunk_id in relevant_chunk_ids
        )
        ideal_dcg = sum(
            1 / math.log2(rank + 1)
            for rank in range(1, min(relevant_count, self.top_k) + 1)
        )
        return dcg / ideal_dcg if ideal_dcg else 0.0


def evaluate_sync(router: Router, cases: Sequence[RetrievalCase], top_k: int = 5) -> RetrievalReport:
    """Convenience entry point for the command-line evaluator."""
    return asyncio.run(RetrievalEvaluator(router, top_k=top_k).evaluate(cases))
