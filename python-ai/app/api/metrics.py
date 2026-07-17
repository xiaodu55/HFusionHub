"""
Prometheus-compatible metrics endpoint for the Python AI service.

Exposes request counts, latencies, and error rates in Prometheus text format.
No external dependencies — uses a lightweight thread-safe counter/registry.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter

router = APIRouter(tags=["metrics"])

# Bounded sample window per histogram. TraceMiddleware observes EVERY request,
# so an unbounded per-name list grows with process lifetime and every
# /metrics scrape re-sorts the whole history (slow scrape + memory leak).
# Quantiles are computed over the most recent window; lifetime count/sum are
# tracked separately so Prometheus _count/_sum stay monotonic.
HISTOGRAM_MAX_SAMPLES = 4096

# ---------------------------------------------------------------------------
# Lightweight metrics registry
# ---------------------------------------------------------------------------

class MetricsRegistry:
    """Thread-safe simple metrics registry (Prometheus-compatible output)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._counters: dict[str, int] = defaultdict(int)
        self._histograms: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=HISTOGRAM_MAX_SAMPLES)
        )
        self._histogram_counts: dict[str, int] = defaultdict(int)
        self._histogram_sums: dict[str, float] = defaultdict(float)
        self._start_time = time.time()

    def inc(self, name: str, value: int = 1):
        with self._lock:
            self._counters[name] += value

    def observe(self, name: str, value: float):
        with self._lock:
            self._histograms[name].append(value)
            self._histogram_counts[name] += 1
            self._histogram_sums[name] += value

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "histograms": dict(self._histograms),
                "histogram_counts": dict(self._histogram_counts),
                "histogram_sums": dict(self._histogram_sums),
                "uptime_seconds": time.time() - self._start_time,
            }

    def to_prometheus(self) -> str:
        """Render metrics in Prometheus text exposition format."""
        snapshot = self.snapshot()
        lines = []

        # Uptime
        lines.append("# HELP hfusionhub_uptime_seconds Service uptime in seconds")
        lines.append("# TYPE hfusionhub_uptime_seconds gauge")
        lines.append(f"hfusionhub_uptime_seconds {snapshot['uptime_seconds']:.1f}")

        # Counters
        for name, value in snapshot["counters"].items():
            safe_name = name.replace("-", "_").replace(" ", "_")
            lines.append(f"# HELP hfusionhub_{safe_name}_total Counter")
            lines.append(f"# TYPE hfusionhub_{safe_name}_total counter")
            lines.append(f"hfusionhub_{safe_name}_total {value}")

        # Histogram summaries (avg, p50, p95, max) over the recent window;
        # _count/_sum use lifetime totals so they stay monotonic.
        for name, values in snapshot["histograms"].items():
            safe_name = name.replace("-", "_").replace(" ", "_")
            if not values:
                continue
            lifetime_count = snapshot["histogram_counts"].get(name, len(values))
            lifetime_sum = snapshot["histogram_sums"].get(name, sum(values))
            sorted_vals = sorted(values)
            p50 = sorted_vals[len(sorted_vals) // 2]
            p95 = sorted_vals[min(int(len(sorted_vals) * 0.95), len(sorted_vals) - 1)]
            p99 = sorted_vals[min(int(len(sorted_vals) * 0.99), len(sorted_vals) - 1)]

            lines.append(f"# HELP hfusionhub_{safe_name}_seconds Request latency")
            lines.append(f"# TYPE hfusionhub_{safe_name}_seconds summary")
            lines.append(f"hfusionhub_{safe_name}_seconds{{quantile=\"0.5\"}} {p50:.4f}")
            lines.append(f"hfusionhub_{safe_name}_seconds{{quantile=\"0.95\"}} {p95:.4f}")
            lines.append(f"hfusionhub_{safe_name}_seconds{{quantile=\"0.99\"}} {p99:.4f}")
            lines.append(f"hfusionhub_{safe_name}_seconds_count {lifetime_count}")
            lines.append(f"hfusionhub_{safe_name}_seconds_sum {lifetime_sum:.4f}")

        lines.append("")
        return "\n".join(lines)


# Global registry
_metrics = MetricsRegistry()


def get_metrics() -> MetricsRegistry:
    return _metrics


# ---------------------------------------------------------------------------
# Middleware helpers (call from chat/vectorization routes)
# ---------------------------------------------------------------------------

def record_chat_request(latency_seconds: float, is_error: bool = False):
    """Record a chat API request."""
    _metrics.inc("chat_requests_total")
    _metrics.observe("chat_latency", latency_seconds)
    if is_error:
        _metrics.inc("chat_errors_total")


def record_rag_retrieval(latency_seconds: float, result_count: int = 0):
    """Record a RAG retrieval operation."""
    _metrics.inc("rag_retrievals_total")
    _metrics.observe("rag_retrieval_latency", latency_seconds)


def record_embedding_request(latency_seconds: float, is_error: bool = False):
    """Record an embedding generation request."""
    _metrics.inc("embedding_requests_total")
    _metrics.observe("embedding_latency", latency_seconds)
    if is_error:
        _metrics.inc("embedding_errors_total")


def record_eval_gate_failure():
    """Record an eval gate failure (called when runtime eval fails a gate)."""
    _metrics.inc("eval_gate_failures")


def set_citation_faithfulness(value: float):
    """Set the current citation faithfulness gauge."""
    with _metrics._lock:
        _metrics._histograms["citation_faithfulness_current"] = [value]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/metrics")
async def metrics_endpoint():
    """Prometheus metrics endpoint."""
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(content=_metrics.to_prometheus(), media_type="text/plain; charset=utf-8")


@router.get("/metrics/json")
async def metrics_json():
    """Human-readable metrics snapshot (JSON)."""
    return _metrics.snapshot()
