"""流式延迟指标：TTFT（首字延迟）P50/均值 与 总延迟均值。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..schemas import EvalRecord


def _percentile(values: list[float], pct: float) -> float | None:
    """线性插值百分位（p50 对偶数样本取中间两数均值）。"""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct / 100
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return ordered[low] + (ordered[high] - ordered[low]) * frac


def aggregate(records: list[EvalRecord]) -> dict[str, float]:
    ttfts = [r.ttft_ms for r in records if r.ttft_ms is not None]
    latencies = [r.latency_ms for r in records if r.latency_ms]
    out: dict[str, float] = {}
    if ttfts:
        out["ttft_p50_ms"] = round(_percentile(ttfts, 50) or 0.0, 1)
        out["ttft_mean_ms"] = round(sum(ttfts) / len(ttfts), 1)
    if latencies:
        out["latency_mean_ms"] = round(sum(latencies) / len(latencies), 1)
    return out
