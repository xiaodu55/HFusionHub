"""行为红线指标：业务上「必须做对」的行为，而非检索排序质量。

- refusal_when_required: 要求 RAG 的样本实际 0 召回且给出拒答/兜底回答；
- fallback_when_required: 回答命中回退话术标记（证据不足/服务不可用模板）；
- over_retrieval_rate: 不要求 RAG 的样本却触发了检索。

指标为「违规率」—— 越低越好，0 为理想。
"""

from __future__ import annotations

from typing import Dict, List

from ..schemas import CaseMetric, EvalRecord

# 回退话术标记：与 python-ai 侧模板文案保持同步（react.py / workflow_runtime.py）
FALLBACK_MARKERS = (
    "未检索到足够依据",
    "无法基于资料回答",
    "AI 服务暂时不可用",
    "不会编造",
)


def _is_fallback_answer(answer: str) -> bool:
    return any(marker in (answer or "") for marker in FALLBACK_MARKERS)


def evaluate_case(record: EvalRecord) -> CaseMetric:
    flags: List[str] = []
    answered = bool((record.answer or "").strip()) and not _is_fallback_answer(record.answer)
    retrieved = len(record.retrieved_document_ids) > 0

    if record.requires_rag and not retrieved and not answered:
        flags.append("refusal_when_required")
    if record.requires_rag and _is_fallback_answer(record.answer):
        flags.append("fallback_when_required")
    if not record.requires_rag and retrieved:
        flags.append("over_retrieval")

    return CaseMetric(query_id=record.query_id, metrics={}, flags=flags)


def aggregate(records: List[EvalRecord]) -> Dict[str, float]:
    total = len(records)
    if total == 0:
        return {}
    cases = [evaluate_case(r) for r in records]

    def rate(flag: str) -> float:
        return sum(1 for c in cases if flag in c.flags) / total

    return {
        "refusal_when_required_rate": rate("refusal_when_required"),
        "fallback_when_required_rate": rate("fallback_when_required"),
        "over_retrieval_rate": rate("over_retrieval"),
    }
