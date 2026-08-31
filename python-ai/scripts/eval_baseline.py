"""Fixed-format evaluation report, gates and baseline-diff for Phase 1.

The report schema is shared by the two execution tracks:

- ``offline`` (hermetic, PR): deterministic retrieval / citation metrics from the
  synthetic index.  Refusal correctness and tool success are answer-layer
  properties that cannot be measured without a model, so they are reported as
  ``None`` (N/A) here.
- ``runtime`` (Nightly/Staging): real latency, token usage, cost and tool
  success measured against the live service.

Both tracks emit the *same* JSON + Markdown structure, so results are directly
comparable and can be diffed against a stored baseline.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

# ---------------------------------------------------------------------------
# Suite case model
# ---------------------------------------------------------------------------

METRIC_LABELS: dict[str, str] = {
    "recall_at_5": "Recall@5",
    "ndcg_at_10": "nDCG@10",
    "citation_accuracy": "引用准确率 (citation accuracy)",
    "citation_faithfulness": "引用忠实度 (citation faithfulness)",
    "citation_recall": "引用召回率 (citation recall)",
    "citation_f1": "引用 F1 (citation F1)",
    "refusal_correctness": "拒答正确率 (refusal correctness)",
    "tool_success_rate": "工具成功率 (tool success rate)",
    "p95_latency_ms": "P95 延迟 (ms)",
    "avg_latency_ms": "平均延迟 (ms)",
    "p50_latency_ms": "P50 延迟 (ms)",
    "tokens_per_task": "单任务 Token 数",
    "cost_usd_per_task": "单任务成本 (USD)",
    "error_rate": "错误率",
    "scope_violations": "越界检索数",
    # 招投标领域指标（B2 垂直化）
    "qualification_recall": "资质要求召回率 (qualification recall)",
    "disqualification_clause_recall": "废标条款召回率 (disqualification recall)",
    "scoring_point_accuracy": "评分点命中率 (scoring point accuracy)",
    "bid_terminology_accuracy": "招标术语命中率 (terminology accuracy)",
}


@dataclass(frozen=True)
class EvalCase:
    """One ground-truth case from the frozen suite."""

    case_id: str
    category: str
    query: str
    kb_id: int
    expected_chunk_ids: tuple[str, ...]
    expected_document_names: tuple[str, ...]
    key_facts: tuple[str, ...]
    refusal: str
    risk_labels: tuple[str, ...]
    tool: dict[str, Any] | None = None
    # 招投标领域事实（B2）：{metric_key: [期望事实子串, ...]}，用于确定性
    # 领域指标（在检索命中内容中做子串匹配，无需 LLM，保持离线轨密闭）。
    bid_facts: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> EvalCase:
        required = {"id", "category", "query", "kb_id",
                    "expected_chunk_ids", "expected_document_names"}
        missing = required - value.keys()
        if missing:
            raise ValueError(f"evaluation case missing fields: {sorted(missing)}")
        return cls(
            case_id=str(value["id"]),
            category=str(value["category"]),
            query=str(value["query"]),
            kb_id=int(value["kb_id"]),
            expected_chunk_ids=tuple(map(str, value["expected_chunk_ids"])),
            expected_document_names=tuple(map(str, value["expected_document_names"])),
            key_facts=tuple(map(str, value.get("key_facts", []))),
            refusal=str(value.get("refusal", "none")),
            risk_labels=tuple(map(str, value.get("risk_labels", []))),
            tool=value.get("tool"),
            bid_facts=value.get("bid_facts"),
        )


def load_cases(path: Any) -> list[EvalCase]:
    """Load the frozen JSONL suite, rejecting duplicates and malformed lines."""
    cases: list[EvalCase] = []
    seen_ids: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            case = EvalCase.from_dict(json.loads(line))
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            raise ValueError(f"invalid evaluation case at {path}:{line_number}: {error}") from error
        if case.case_id in seen_ids:
            raise ValueError(f"duplicate evaluation case id: {case.case_id}")
        seen_ids.add(case.case_id)
        cases.append(case)
    if not cases:
        raise ValueError("evaluation suite must contain at least one case")
    return cases


def verify_suite_integrity(cases_path: Any, suite_manifest_path: Any) -> dict:
    """Verify the frozen suite is byte-identical to what was pinned at freeze time.

    Computes the SHA-256 of ``cases.jsonl`` and compares it against
    ``suite_manifest.json.cases_sha256``.  Any modification of the cases after
    freezing (intentional or not) raises ``ValueError``, so both evaluation
    tracks refuse to run against a tampered or drifted suite.
    """
    manifest = json.loads(Path(suite_manifest_path).read_text(encoding="utf-8"))
    pinned = str(manifest.get("cases_sha256", ""))
    if not pinned:
        raise ValueError(
            f"{suite_manifest_path} is missing cases_sha256; freeze the suite first"
        )
    digest = hashlib.sha256(Path(cases_path).read_bytes()).hexdigest()
    if digest != pinned:
        raise ValueError(
            f"cases.jsonl SHA-256 mismatch: computed {digest} != pinned {pinned}; "
            "the suite was modified after freezing. Rebuild with build_suite.py "
            "and update the manifest if the change is intentional."
        )
    return manifest


# ---------------------------------------------------------------------------
# Outcome and metrics
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CaseOutcome:
    case_id: str
    category: str
    retrieved_chunk_ids: list[str]
    expected_chunk_ids: tuple[str, ...]
    expected_document_names: tuple[str, ...]
    scope_violations: int
    citation_faithfulness: float | None
    refusal_expected: bool
    refusal_correct: bool | None
    tool: dict[str, Any] | None
    cited_chunk_ids: list[str] = field(default_factory=list)
    latency_ms: float | None = None
    tokens: int | None = None
    cost_usd: float | None = None
    tool_success: bool | None = None
    error: str | None = None
    # 招投标领域指标：{metric_key: 命中率(0-1)}，按 case 聚合为套件指标。
    bid: dict[str, float] | None = None

    @property
    def has_expected(self) -> bool:
        return bool(self.expected_chunk_ids)

    @property
    def hit_at_5(self) -> bool:
        return bool(set(self.expected_chunk_ids) & set(self.retrieved_chunk_ids[:5]))


@dataclass(frozen=True)
class Metrics:
    recall_at_5: float | None = None
    ndcg_at_10: float | None = None
    citation_accuracy: float | None = None
    citation_faithfulness: float | None = None
    citation_recall: float | None = None
    citation_f1: float | None = None
    refusal_correctness: float | None = None
    tool_success_rate: float | None = None
    p95_latency_ms: float | None = None
    avg_latency_ms: float | None = None
    p50_latency_ms: float | None = None
    tokens_per_task: float | None = None
    cost_usd_per_task: float | None = None
    error_rate: float = 0.0
    scope_violations: int = 0
    # 招投标领域指标（B2 垂直化，离线轨确定性产出）
    qualification_recall: float | None = None
    disqualification_clause_recall: float | None = None
    scoring_point_accuracy: float | None = None
    bid_terminology_accuracy: float | None = None

    def to_dict(self) -> dict[str, float | None]:
        return asdict(self)


def _percentile(sorted_values: Sequence[float], percentile: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(int(len(sorted_values) * percentile), len(sorted_values) - 1)
    return float(sorted_values[index])


def aggregate_metrics(outcomes: Sequence[CaseOutcome], top_k: int = 10,
                      exclude_refusal_from_citation: bool = False) -> Metrics:
    """Aggregate the fixed-format metrics from per-case outcomes.

    ``exclude_refusal_from_citation`` excludes ``refusal == "required"`` cases
    from citation aggregates.  The runtime track enables it because a correctly
    refused answer carries no citations by design; the offline track keeps them
    to also measure retrieval of sensitive content.

    引用指标为精确率/召回率双报：``citation_faithfulness`` 是精确率口径
    （逐 case 的 |E∩C|/|C|，由调用方按各轨语义给出——离线轨为引用窗口
    精确率，runtime 轨为 key-facts 语义级支持度），``citation_recall``
    在本函数中从 cited/expected 直接计算（文档/chunk 级覆盖）。
    ``citation_f1`` 调和两者；runtime 轨的 F1 混合了语义级 P 与文档级 R，
    仅作跨轨参考，跨套件对比以离线轨为准。
    """
    if not outcomes:
        raise ValueError("at least one outcome is required")

    valid = [o for o in outcomes if o.error is None]
    total_expected = sum(len(o.expected_chunk_ids) for o in valid)

    recall_numerator = 0
    ndcg_values: list[float] = []
    for outcome in valid:
        expected = set(outcome.expected_chunk_ids)
        if not expected:
            continue
        retrieved = outcome.retrieved_chunk_ids
        recall_numerator += len(expected & set(retrieved[:5]))
        ndcg_values.append(
            _ndcg(retrieved[:top_k], expected, top_k=top_k)
        )

    # citation metrics over cases with expected chunks.  The citation set is the
    # chunks the answer actually used (``cited_chunk_ids``); it falls back to the
    # full retrieved set when the caller did not supply it.
    citation_outcomes = [
        o for o in valid
        if o.has_expected and not (exclude_refusal_from_citation and o.refusal_expected)
    ]
    citation_accuracy = None
    citation_faithfulness = None
    citation_recall = None
    citation_f1 = None
    if citation_outcomes:
        accurate = sum(
            1 for o in citation_outcomes
            if set(o.expected_chunk_ids) & set(o.cited_chunk_ids or o.retrieved_chunk_ids)
        )
        citation_accuracy = accurate / len(citation_outcomes)
        faithfulness_values = [o.citation_faithfulness for o in citation_outcomes
                               if o.citation_faithfulness is not None]
        if faithfulness_values:
            citation_faithfulness = sum(faithfulness_values) / len(faithfulness_values)
        # 引用召回率/F1：与精确率（忠实度）互补的双报口径。忠实度只惩罚
        # 引用集里的无关块，对"漏引期望证据"不敏感；recall = |E∩C|/|E|
        # 补上这个盲区，F1 两者兼顾作为跨套件可比的主指标。
        recall_values: list[float] = []
        f1_values: list[float] = []
        for o in citation_outcomes:
            cited = o.cited_chunk_ids or o.retrieved_chunk_ids
            recall = compute_citation_recall(cited, o.expected_chunk_ids)
            if recall is None:
                continue
            recall_values.append(recall)
            f1 = compute_citation_f1(o.citation_faithfulness, recall)
            if f1 is not None:
                f1_values.append(f1)
        if recall_values:
            citation_recall = sum(recall_values) / len(recall_values)
        if f1_values:
            citation_f1 = sum(f1_values) / len(f1_values)

    # refusal correctness is an answer-layer property; computed only when the
    # caller (runtime track) supplies per-case signals.
    refusal_values = [o.refusal_correct for o in valid
                      if o.refusal_expected and o.refusal_correct is not None]
    refusal_correctness = None
    if refusal_values:
        refusal_correctness = sum(1 for value in refusal_values if value) / len(refusal_values)

    tool_values = [o.tool_success for o in valid
                   if o.tool is not None and o.tool_success is not None]
    tool_success_rate = None
    if tool_values:
        tool_success_rate = sum(1 for value in tool_values if value) / len(tool_values)

    latencies = sorted(o.latency_ms for o in valid if o.latency_ms is not None)
    token_values = [o.tokens for o in valid if o.tokens is not None]
    cost_values = [o.cost_usd for o in valid if o.cost_usd is not None]

    # 招投标领域指标：按 case 的 bid 命中率取均值（无该指标的 case 跳过）
    def _bid_average(metric_key: str) -> float | None:
        values = [o.bid[metric_key] for o in valid
                  if o.bid is not None and o.bid.get(metric_key) is not None]
        return (sum(values) / len(values)) if values else None

    return Metrics(
        recall_at_5=(recall_numerator / total_expected) if total_expected else None,
        ndcg_at_10=(sum(ndcg_values) / len(ndcg_values)) if ndcg_values else None,
        citation_accuracy=citation_accuracy,
        citation_faithfulness=citation_faithfulness,
        citation_recall=citation_recall,
        citation_f1=citation_f1,
        refusal_correctness=refusal_correctness,
        tool_success_rate=tool_success_rate,
        p95_latency_ms=_percentile(latencies, 0.95) if latencies else None,
        avg_latency_ms=(sum(latencies) / len(latencies)) if latencies else None,
        p50_latency_ms=_percentile(latencies, 0.5) if latencies else None,
        tokens_per_task=(sum(token_values) / len(token_values)) if token_values else None,
        cost_usd_per_task=(sum(cost_values) / len(cost_values)) if cost_values else None,
        error_rate=sum(1 for o in outcomes if o.error is not None) / len(outcomes),
        scope_violations=sum(o.scope_violations for o in valid),
        qualification_recall=_bid_average("qualification_recall"),
        disqualification_clause_recall=_bid_average("disqualification_clause_recall"),
        scoring_point_accuracy=_bid_average("scoring_point_accuracy"),
        bid_terminology_accuracy=_bid_average("bid_terminology_accuracy"),
    )


def _ndcg(retrieved: Sequence[str], expected: Iterable[str], top_k: int) -> float:
    expected_set = set(expected)
    relevant_count = len(expected_set)
    if not relevant_count:
        return 0.0
    dcg = sum(
        1 / math.log2(rank + 1)
        for rank, chunk_id in enumerate(retrieved, start=1)
        if chunk_id in expected_set
    )
    ideal_dcg = sum(1 / math.log2(rank + 1)
                    for rank in range(1, min(relevant_count, top_k) + 1))
    return dcg / ideal_dcg if ideal_dcg else 0.0


def compute_citation_faithfulness(
    cited_chunk_ids: Sequence[str], expected_chunk_ids: Sequence[str]
) -> float | None:
    cited = list(cited_chunk_ids)
    if not cited:
        return None
    expected = set(expected_chunk_ids)
    if not expected:
        return None
    return len(expected & set(cited)) / len(cited)


def compute_citation_recall(
    cited_chunk_ids: Sequence[str], expected_chunk_ids: Sequence[str]
) -> float | None:
    """引用召回率 |E∩C|/|E|：期望证据块被引用集覆盖的比例。

    与忠实度（精确率口径）互补：忠实度对"引用集混入无关块"敏感，
    对"漏引期望证据"完全不敏感（|E|=1、|C|=3 时即使漏掉唯一证据块，
    只要剩余两个块也算引用，分数仍不为零的盲区由 recall 补上）。
    """
    expected = set(expected_chunk_ids)
    if not expected:
        return None
    cited = list(cited_chunk_ids)
    if not cited:
        return 0.0
    return len(expected & set(cited)) / len(expected)


def compute_citation_f1(
    precision: float | None, recall: float | None
) -> float | None:
    """引用 F1：精确率与召回率的调和平均，作为跨套件可比的主指标。"""
    if precision is None or recall is None:
        return None
    if precision + recall <= 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def select_cited_chunks(
    ranked: Sequence[tuple[str, float]], top_k: int, score_ratio: float
) -> list[str]:
    """模拟抽取式答案的引用行为：引用与最相关块"相关性足够接近"的块。

    固定 top-k 引用窗口与期望证据集规模脱钩（本套件期望块最多 2 块，
    而窗口固定 3 块），无关的高排名块必然进入引用集，使忠实度存在
    结构性上限（完美检索也只有 ~0.39）。自适应窗口以
    ``score >= score_ratio * 首块分数`` 划界：检索歧义小（首块显著占优）
    时窗口收缩到 1~2 块，分数扁平（无法区分相关块）时窗口扩张到
    ``top_k`` 封顶——窗口大小本身成为检索质量的信号。

    ``ranked`` 为按相关性降序的 ``(chunk_id, score)`` 序列；首块分数
    非>0（检索完全无命中）时引用空集，对应"无证据可引"。
    """
    if not ranked:
        return []
    top_score = ranked[0][1]
    if top_score <= 0:
        return []
    threshold = top_score * score_ratio
    return [chunk_id for chunk_id, score in ranked if score >= threshold][:top_k]


async def compression_surviving_chunks(
    ranked: Sequence[tuple[str, float]],
    content_by_chunk: dict[str, str | None],
    query: str,
    target_ratio: float = 0.6,
) -> list[tuple[str, float]]:
    """压缩感知的引用模拟：返回合并上下文经抽取式压缩后仍"可见"的 chunk。

    生产管线在生成前用 ``react._safe_compress`` → ``compress_numbered_blocks``
    压缩**合并后的**编号上下文（target_ratio=0.6）——被压掉全部句子的块对
    生成器不可见，也就不可能被引用。本函数把检索结果格式化成与生产一致的
    ``[n]`` 编号块文本，直接复用 ``compress_numbered_blocks`` 重放该过程，
    存活块号映射回 ``(chunk_id, score)``：生产与评测共用同一份压缩实现，
    口径不会漂移。

    ``query`` 传入用户问题（压缩评分的 query 重叠信号，空串回退无 query
    的历史权重）；``target_ratio`` 与生产 ``_safe_compress`` 默认一致，
    1.0 等价关闭压缩模拟（保留全部句子）。
    """
    from app.core.rag.context_compressor import (
        CompressionConfig,
        ExtractiveCompressionStrategy,
    )

    if not ranked:
        return []
    contents = [(cid, score, content_by_chunk.get(cid) or "")
                for cid, score in ranked]
    if not any(content for _, _, content in contents):
        return []
    numbered = "\n\n".join(
        f"[{i}] (语义匹配, 相似度: {score:.2f})\n{content}"
        for i, (_cid, score, content) in enumerate(contents, 1)
    )
    strategy = ExtractiveCompressionStrategy()
    _text, kept, _did = await strategy.compress_numbered_blocks(
        numbered,
        CompressionConfig(target_ratio=target_ratio),
        query=query,
    )
    if not kept:
        return list(ranked)
    return [contents[number - 1][:2] for number in kept]


def runtime_citation_faithfulness(
    answer: str,
    cited_docs: Sequence[str],
    key_facts: Sequence[str],
    doc_text_by_title: dict[str, str],
    support_threshold: float = 0.5,
    answer_threshold: float = 0.5,
) -> float | None:
    """Runtime citation faithfulness: fraction of key facts that the *answer*
    actually states **and** that are lexically supported by the cited documents.

    The metric name means *the answer's claims are backed by the citations*.
    ``key_facts`` are the ground-truth claims the answer should make.  A fact is
    deemed faithful only when BOTH conditions hold:

    * **answer support** — at least ``answer_threshold`` of its distinct tokens
      appear in the answer text (the answer must actually make the claim), and
    * **citation support** — at least ``support_threshold`` of its distinct
      tokens appear in a cited document's content (the citation must back it).

    This prevents an answer that is entirely wrong or fabricated — but happens to
    cite the right documents — from scoring full marks: it fails the answer
    support check.  Deterministic (no LLM), using the same CJK-bigram tokenizer
    as the synthetic index.

    Returns ``None`` when the case has no key facts, and ``0.0`` when nothing
    was cited.
    """
    from app.core.rag.synthetic_index import tokenize

    facts = [fact for fact in key_facts if fact and tokenize(fact)]
    if not facts:
        return None
    if not cited_docs:
        return 0.0
    cited_text = "\n".join(doc_text_by_title.get(title, "") for title in cited_docs)
    cited_tokens = set(tokenize(cited_text))
    answer_tokens = set(tokenize(answer))
    faithful = 0
    for fact in facts:
        distinct = set(tokenize(fact))
        if not distinct:
            continue
        answer_overlap = len(distinct & answer_tokens) / len(distinct)
        citation_overlap = len(distinct & cited_tokens) / len(distinct)
        if answer_overlap >= answer_threshold and citation_overlap >= support_threshold:
            faithful += 1
    return faithful / len(facts)


# ---------------------------------------------------------------------------
# Evaluation report
# ---------------------------------------------------------------------------

@dataclass
class EvaluationReport:
    track: str
    suite_version: str
    kb_id: int
    kb_version: str
    suite_sha256: str
    generated_at: str
    case_count: int
    category_counts: dict[str, int]
    metrics: Metrics
    baseline_metrics: dict[str, float | None] = field(default_factory=dict)
    diffs: dict[str, float | None] = field(default_factory=dict)
    regressions: list[str] = field(default_factory=list)
    gate_failures: list[str] = field(default_factory=list)
    outcomes: list[CaseOutcome] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "track": self.track,
            "suite_version": self.suite_version,
            "kb_id": self.kb_id,
            "kb_version": self.kb_version,
            "suite_sha256": self.suite_sha256,
            "generated_at": self.generated_at,
            "case_count": self.case_count,
            "category_counts": self.category_counts,
            "metrics": self.metrics.to_dict(),
            "baseline_metrics": self.baseline_metrics,
            "diffs": self.diffs,
            "regressions": self.regressions,
            "gate_failures": self.gate_failures,
        }


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

GATE_ORDER = [
    "recall_at_5",
    "ndcg_at_10",
    "citation_accuracy",
    "citation_faithfulness",
    "citation_recall",
    "citation_f1",
    "refusal_correctness",
    "tool_success_rate",
    "qualification_recall",
    "disqualification_clause_recall",
    "scoring_point_accuracy",
    "bid_terminology_accuracy",
    "p95_latency_ms",
    "tokens_per_task",
    "error_rate",
    "scope_violations",
]


def check_gates(
    metrics: Metrics,
    thresholds: dict[str, float],
) -> list[str]:
    """Return human-readable failures for quality gates.

    ``thresholds`` maps a metric key to a minimum (for higher-is-better metrics)
    or a maximum (for ``p95_latency_ms``, ``error_rate``,
    ``scope_violations`` and ``tokens_per_task``, which are lower-is-better;
    token 上限用于模型侧行为漂移告警——R17-2，token 1582→774 式漂移本可
    自动发现而非人工对比基线).
    """
    failures: list[str] = []
    for key in GATE_ORDER:
        if key not in thresholds:
            continue
        threshold = thresholds[key]
        value = getattr(metrics, key)
        if value is None:
            # A gate for a metric this track cannot produce is skipped, not failed.
            continue
        label = METRIC_LABELS.get(key, key)
        if key in ("p95_latency_ms", "error_rate", "scope_violations", "tokens_per_task"):
            if value > threshold:
                failures.append(f"{label}={value:.3f} exceeds maximum {threshold:.3f}")
        elif value < threshold:
            failures.append(f"{label}={value:.3f} is below minimum {threshold:.3f}")
    return failures


# ---------------------------------------------------------------------------
# Baseline + diff
# ---------------------------------------------------------------------------

# per-metric regression tolerances:
# quality metrics: absolute drop allowed; latency/token/cost: relative increase allowed
QUALITY_ABS_TOLERANCE = 0.03
RELATIVE_TOLERANCE = 0.15  # latency / tokens / cost
RELATIVE_LATENCY_TOLERANCE = 0.20


def _is_higher_is_better(key: str) -> bool:
    return key not in ("p95_latency_ms", "avg_latency_ms", "p50_latency_ms",
                       "tokens_per_task", "cost_usd_per_task",
                       "error_rate", "scope_violations")


def diff_against_baseline(
    current: Metrics,
    baseline: dict[str, float | None],
) -> tuple[dict[str, float | None], list[str]]:
    """Return ``(deltas, regressions)``.  A metric is only compared when both
    sides have a non-null value."""
    current_dict = current.to_dict()
    deltas: dict[str, float | None] = {}
    regressions: list[str] = []

    for key, baseline_value in baseline.items():
        current_value = current_dict.get(key)
        if baseline_value is None or current_value is None:
            deltas[key] = None
            continue
        delta = float(current_value) - float(baseline_value)
        deltas[key] = delta
        label = METRIC_LABELS.get(key, key)
        if _is_higher_is_better(key):
            tolerance = QUALITY_ABS_TOLERANCE
            if delta < -tolerance:
                regressions.append(f"{label} dropped {abs(delta):.3f} vs baseline {baseline_value:.3f}")
        else:
            if baseline_value == 0:
                tolerance = QUALITY_ABS_TOLERANCE
            elif key in ("p95_latency_ms", "avg_latency_ms", "p50_latency_ms"):
                tolerance = baseline_value * RELATIVE_LATENCY_TOLERANCE
            else:
                tolerance = abs(baseline_value) * RELATIVE_TOLERANCE
            if delta > tolerance:
                regressions.append(f"{label} increased {delta:.3f} vs baseline {baseline_value:.3f}")
    return deltas, regressions


def load_baseline(
    path: Any,
    required_suite_sha256: str | None = None,
) -> dict[str, float | None] | None:
    """Load a stored baseline ``metrics`` mapping, or ``None`` if absent.

    When ``required_suite_sha256`` is given, the baseline is only valid if it
    was recorded for the same frozen suite.  A baseline that is missing the pin
    or was recorded for a different ``cases_sha256`` raises ``ValueError``, so
    a stale baseline can never silently feed a comparison — the operator must
    re-freeze with ``--update-baseline``.
    """
    path = Path(path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    metrics = data.get("metrics")
    if not isinstance(metrics, dict):
        return None
    if required_suite_sha256 is not None:
        recorded = str(data.get("suite_sha256") or "")
        if recorded != required_suite_sha256:
            raise ValueError(
                f"baseline {path} was recorded for suite {recorded or '(unpinned)'}, "
                f"current suite is {required_suite_sha256}; re-run with --update-baseline "
                "to re-freeze the baseline before comparing."
            )
    return {key: (float(value) if value is not None else None)
            for key, value in metrics.items()}


def save_baseline(
    metrics: Metrics,
    path: Any,
    *,
    track: str,
    suite_version: str,
    kb_version: str,
    suite_sha256: str,
    generated_at: str,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "track": track,
        "suite_version": suite_version,
        "kb_version": kb_version,
        "suite_sha256": suite_sha256,
        "generated_at": generated_at,
        "metrics": metrics.to_dict(),
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _fmt(value: float | None, digits: int = 3) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{digits}f}"


def render_markdown(report: EvaluationReport) -> str:
    lines: list[str] = [
        f"# HFusionHub 评测报告 ({report.track})",
        "",
        f"- **suite_version**: {report.suite_version}",
        f"- **kb_version**: {report.kb_version}  (kb_id={report.kb_id})",
        f"- **cases_sha256**: {report.suite_sha256[:16]}…",
        f"- **case_count**: {report.case_count}",
        f"- **generated_at**: {report.generated_at}",
        "",
        "## 指标 (fixed-format)",
        "",
        "| 指标 | 本次 | 基线 | 差异 |",
        "|------|------|------|------|",
    ]
    metric_keys = [
        "recall_at_5", "ndcg_at_10", "citation_accuracy", "citation_faithfulness",
        "citation_recall", "citation_f1",
        "refusal_correctness", "tool_success_rate", "p95_latency_ms",
        "tokens_per_task", "cost_usd_per_task", "error_rate", "scope_violations",
    ]
    for key in metric_keys:
        label = METRIC_LABELS.get(key, key)
        current = getattr(report.metrics, key)
        baseline = report.baseline_metrics.get(key)
        delta = report.diffs.get(key)
        delta_text = "N/A"
        if delta is not None:
            delta_text = f"{delta:+.3f}"
        lines.append(
            f"| {label} | {_fmt(current)} | {_fmt(baseline)} | {delta_text} |"
        )

    lines += [
        "",
        "## 分类明细",
        "",
        "| 类别 | 用例数 |",
        "|------|--------|",
    ]
    for category, count in sorted(report.category_counts.items()):
        lines.append(f"| {category} | {count} |")

    lines += ["", "## 基线对比与回归"]
    if report.regressions:
        lines.append("")
        lines.append("⚠️ 回归项：")
        for regression in report.regressions:
            lines.append(f"- {regression}")
    elif report.baseline_metrics:
        lines.append("")
        lines.append("无回归。")
    else:
        lines.append("")
        lines.append("无基线可对比（首次运行可用 --update-baseline 写入基线）。")

    lines += ["", "## 门禁", ""]
    if report.gate_failures:
        for failure in report.gate_failures:
            lines.append(f"- ❌ {failure}")
    else:
        lines.append("- 全部通过 ✅")
    return "\n".join(lines)
