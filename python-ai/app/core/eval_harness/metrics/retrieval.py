"""检索指标：Hit@K / Recall / MRR（仅对 requires_rag=true 的样本聚合）。"""

from __future__ import annotations

from typing import Dict, List, Sequence

from ..schemas import CaseMetric, EvalRecord


def _norm(ids: Sequence[str]) -> List[str]:
    return [str(x).strip() for x in ids if str(x).strip()]


def hit_at_k(retrieved: Sequence[str], expected: Sequence[str], k: int) -> bool:
    got = set(_norm(retrieved)[:k])
    return any(x in got for x in _norm(expected))


def recall_at_k(retrieved: Sequence[str], expected: Sequence[str], k: int) -> float:
    exp = _norm(expected)
    if not exp:
        return 0.0
    got = set(_norm(retrieved)[:k])
    return sum(1 for x in exp if x in got) / len(exp)


def reciprocal_rank(retrieved: Sequence[str], expected: Sequence[str]) -> float:
    exp = set(_norm(expected))
    for rank, doc in enumerate(_norm(retrieved), start=1):
        if doc in exp:
            return 1.0 / rank
    return 0.0


def evaluate_case(record: EvalRecord, k: int = 5) -> CaseMetric:
    expected = _norm(record.expected_document_ids)
    retrieved = _norm(record.retrieved_document_ids)
    return CaseMetric(
        query_id=record.query_id,
        metrics={
            f"hit@{k}": 1.0 if hit_at_k(retrieved, expected, k) else 0.0,
            f"recall@{k}": recall_at_k(retrieved, expected, k),
            f"mrr@{k}": reciprocal_rank(retrieved, expected),
        },
    )


def aggregate(records: List[EvalRecord], k: int = 5) -> Dict[str, float]:
    """仅聚合 requires_rag=true 的样本（与 ragenteval 口径一致）。"""
    rag_records = [r for r in records if r.requires_rag]
    if not rag_records:
        return {}
    cases = [evaluate_case(r, k) for r in rag_records]
    n = len(cases)
    out: Dict[str, float] = {}
    for key in (f"hit@{k}", f"recall@{k}", f"mrr@{k}"):
        out[key] = sum(c.metrics[key] for c in cases) / n
    return out
