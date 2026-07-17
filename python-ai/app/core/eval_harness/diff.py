"""A/B 回归门禁：对两次评分结果做阈值化对比，逐指标标记改善/回归/持平。

方向约定：
- 比率/评分类（0~1）越高越好（HIGHER_IS_BETTER）；
- 延迟类（ms）越低越好（LOWER_IS_BETTER）。
"""

from __future__ import annotations

# 指标 → (方向, 回归阈值)；未登记的指标默认 HIGHER_IS_BETTER + 0.02
RULES: dict[str, tuple] = {
    "retrieval_hit@5": ("higher", 0.03),
    "retrieval_recall@5": ("higher", 0.03),
    "retrieval_mrr@5": ("higher", 0.03),
    "refusal_when_required_rate": ("lower", 0.02),
    "fallback_when_required_rate": ("lower", 0.02),
    "over_retrieval_rate": ("lower", 0.05),
    "ttft_p50_ms": ("lower", 500.0),
    "ttft_mean_ms": ("lower", 500.0),
    "latency_mean_ms": ("lower", 3000.0),
    "judge_faithfulness_mean": ("higher", 0.03),
    "judge_answer_correctness_mean": ("higher", 0.03),
    "judge_answer_relevancy_mean": ("higher", 0.03),
}

NEUTRAL = "neutral"
IMPROVED = "improved"
REGRESSED = "regressed"


def diff_metrics(base: dict[str, float], candidate: dict[str, float]) -> list[dict]:
    rows: list[dict] = []
    for key, candidate_value in candidate.items():
        if key not in base:
            continue
        base_value = base[key]
        delta = candidate_value - base_value
        direction, threshold = RULES.get(key, ("higher", 0.02))
        if direction == "lower":
            verdict = REGRESSED if delta > threshold else (IMPROVED if delta < -threshold else NEUTRAL)
        else:
            verdict = REGRESSED if delta < -threshold else (IMPROVED if delta > threshold else NEUTRAL)
        rows.append({
            "metric": key,
            "base": base_value,
            "candidate": candidate_value,
            "delta": round(delta, 4),
            "direction": direction,
            "threshold": threshold,
            "verdict": verdict,
        })
    # base 有而 candidate 没有的指标也列出（无法比较）
    for key, base_value in base.items():
        if key not in candidate:
            rows.append({"metric": key, "base": base_value, "candidate": None,
                         "delta": None, "direction": RULES.get(key, ("higher",))[0],
                         "threshold": None, "verdict": "missing_in_candidate"})
    rows.sort(key=lambda r: (r["verdict"] != REGRESSED, r["metric"]))
    return rows


def has_regression(rows: list[dict]) -> bool:
    return any(r["verdict"] == REGRESSED for r in rows)
