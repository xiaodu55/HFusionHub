"""Retrieval tracing primitives for debugging and RAG evaluation."""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Deque, Dict, List, Optional
from uuid import uuid4


@dataclass
class RetrievalTrace:
    """A privacy-conscious record of one retrieval operation."""

    query: str
    knowledge_base_id: Optional[int]
    top_k: int
    routes: List[Dict[str, Any]] = field(default_factory=list)
    results: List[Dict[str, Any]] = field(default_factory=list)
    rewrite_count: int = 1
    latency_ms: float = 0.0
    error: Optional[str] = None
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return data


class RetrievalTraceStore:
    """Bounded in-memory trace store.

    A future persistent implementation can use the same public interface to
    write traces to MySQL, ClickHouse, or an observability service.
    """

    def __init__(self, max_traces: int = 500):
        if max_traces < 1:
            raise ValueError("max_traces must be at least 1")
        self._traces: Deque[RetrievalTrace] = deque(maxlen=max_traces)
        self._lock = Lock()

    def record(self, trace: RetrievalTrace) -> RetrievalTrace:
        with self._lock:
            self._traces.appendleft(trace)
        return trace

    def list(self, limit: int = 50) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(limit, 200))
        with self._lock:
            return [trace.to_dict() for trace in list(self._traces)[:safe_limit]]

    def get(self, trace_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for trace in self._traces:
                if trace.trace_id == trace_id:
                    return trace.to_dict()
        return None

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            traces = list(self._traces)

        total = len(traces)
        source_counts = Counter(
            result.get("source", "unknown")
            for trace in traces
            for result in trace.results
        )
        return {
            "total_traces": total,
            "failed_traces": sum(trace.error is not None for trace in traces),
            "average_latency_ms": round(
                sum(trace.latency_ms for trace in traces) / total, 2
            ) if total else 0.0,
            "result_source_counts": dict(source_counts),
        }

    def clear(self) -> None:
        with self._lock:
            self._traces.clear()


_trace_store: Optional[RetrievalTraceStore] = None


def get_trace_store() -> RetrievalTraceStore:
    global _trace_store
    if _trace_store is None:
        _trace_store = RetrievalTraceStore()
    return _trace_store


def reset_trace_store() -> None:
    global _trace_store
    _trace_store = None
