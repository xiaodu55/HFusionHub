"""Retrieval tracing primitives for debugging and RAG evaluation."""

from __future__ import annotations

import csv
import io
import json
from collections import Counter, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
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
    debug: Dict[str, Any] = field(default_factory=dict)
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

    def _snapshot(self) -> List[RetrievalTrace]:
        with self._lock:
            return list(self._traces)

    @staticmethod
    def _matches(
        trace: RetrievalTrace,
        *,
        query: Optional[str] = None,
        knowledge_base_id: Optional[int] = None,
        error_only: bool = False,
        source: Optional[str] = None,
    ) -> bool:
        if knowledge_base_id is not None and trace.knowledge_base_id != knowledge_base_id:
            return False
        if error_only and trace.error is None:
            return False
        if query and query.strip().lower() not in trace.query.lower():
            return False
        if source and not any(str(result.get("source")) == source for result in trace.results):
            return False
        return True

    def _filtered(
        self,
        *,
        query: Optional[str] = None,
        knowledge_base_id: Optional[int] = None,
        error_only: bool = False,
        source: Optional[str] = None,
    ) -> List[RetrievalTrace]:
        traces = self._snapshot()
        return [
            trace for trace in traces
            if self._matches(
                trace,
                query=query,
                knowledge_base_id=knowledge_base_id,
                error_only=error_only,
                source=source,
            )
        ]

    def list(
        self,
        limit: int = 50,
        offset: int = 0,
        query: Optional[str] = None,
        knowledge_base_id: Optional[int] = None,
        error_only: bool = False,
        source: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(limit, 200))
        safe_offset = max(0, offset)
        traces = self._filtered(
            query=query,
            knowledge_base_id=knowledge_base_id,
            error_only=error_only,
            source=source,
        )
        return [trace.to_dict() for trace in traces[safe_offset:safe_offset + safe_limit]]

    def count(
        self,
        *,
        query: Optional[str] = None,
        knowledge_base_id: Optional[int] = None,
        error_only: bool = False,
        source: Optional[str] = None,
    ) -> int:
        """Return the number of traces matching the same list filters."""
        return len(self._filtered(
            query=query,
            knowledge_base_id=knowledge_base_id,
            error_only=error_only,
            source=source,
        ))

    def get(self, trace_id: str) -> Optional[Dict[str, Any]]:
        for trace in self._snapshot():
            if trace.trace_id == trace_id:
                return trace.to_dict()
        return None

    def stats(
        self,
        window_days: int = 7,
        knowledge_base_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        traces = self._filtered(knowledge_base_id=knowledge_base_id)

        total = len(traces)
        source_counts = Counter(
            result.get("source", "unknown")
            for trace in traces
            for result in trace.results
        )
        hit_count = sum(bool(trace.results) for trace in traces)
        failure_traces = [trace for trace in traces if trace.error is not None]
        recent_failures = [
            {
                "trace_id": trace.trace_id,
                "created_at": trace.created_at.isoformat(),
                "query": trace.query,
                "knowledge_base_id": trace.knowledge_base_id,
                "latency_ms": trace.latency_ms,
                "error": trace.error,
                "top_k": trace.top_k,
            }
            for trace in failure_traces[:5]
        ]

        now = datetime.now(timezone.utc)
        start_day = (now - timedelta(days=max(window_days, 1) - 1)).date()
        daily_metrics: Dict[str, Dict[str, Any]] = {}
        for day_index in range(max(window_days, 1)):
            day = (start_day + timedelta(days=day_index)).isoformat()
            daily_metrics[day] = {
                "date": day,
                "total_traces": 0,
                "failed_traces": 0,
                "hit_traces": 0,
                "hit_rate": 0.0,
                "average_latency_ms": 0.0,
            }

        for trace in traces:
            day = trace.created_at.astimezone(timezone.utc).date().isoformat()
            if day not in daily_metrics:
                continue
            metric = daily_metrics[day]
            metric["total_traces"] += 1
            metric["failed_traces"] += 1 if trace.error is not None else 0
            metric["hit_traces"] += 1 if trace.results else 0
            metric["average_latency_ms"] += trace.latency_ms

        for metric in daily_metrics.values():
            total_traces = metric["total_traces"]
            if total_traces:
                metric["hit_rate"] = round(metric["hit_traces"] / total_traces, 4)
                metric["average_latency_ms"] = round(metric["average_latency_ms"] / total_traces, 2)
            else:
                metric["hit_rate"] = 0.0
                metric["average_latency_ms"] = 0.0

        return {
            "knowledge_base_id": knowledge_base_id,
            "total_traces": total,
            "failed_traces": len(failure_traces),
            "hit_traces": hit_count,
            "hit_rate": round(hit_count / total, 4) if total else 0.0,
            "average_latency_ms": round(
                sum(trace.latency_ms for trace in traces) / total, 2
            ) if total else 0.0,
            "result_source_counts": dict(source_counts),
            "recent_failures": recent_failures,
            "daily_metrics": list(daily_metrics.values()),
            "window_days": max(window_days, 1),
        }

    def clear(self) -> None:
        with self._lock:
            self._traces.clear()

    def export(
        self,
        format: str = "json",
        *,
        query: Optional[str] = None,
        knowledge_base_id: Optional[int] = None,
        error_only: bool = False,
        source: Optional[str] = None,
    ) -> Dict[str, str]:
        traces = self._filtered(
            query=query,
            knowledge_base_id=knowledge_base_id,
            error_only=error_only,
            source=source,
        )
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        normalized = format.lower()

        if normalized == "csv":
            buffer = io.StringIO()
            writer = csv.DictWriter(
                buffer,
                fieldnames=[
                    "trace_id",
                    "created_at",
                    "query",
                    "knowledge_base_id",
                    "top_k",
                    "rewrite_count",
                    "latency_ms",
                    "error",
                    "route_count",
                    "result_count",
                    "route_channels",
                    "result_sources",
                ],
            )
            writer.writeheader()
            for trace in traces:
                writer.writerow({
                    "trace_id": trace.trace_id,
                    "created_at": trace.created_at.isoformat(),
                    "query": trace.query,
                    "knowledge_base_id": trace.knowledge_base_id,
                    "top_k": trace.top_k,
                    "rewrite_count": trace.rewrite_count,
                    "latency_ms": trace.latency_ms,
                    "error": trace.error or "",
                    "route_count": len(trace.routes),
                    "result_count": len(trace.results),
                    "route_channels": ";".join(
                        "/".join(route.get("selected_channels", []))
                        for route in trace.routes
                        if route.get("selected_channels")
                    ),
                    "result_sources": ";".join(
                        str(result.get("source", "unknown"))
                        for result in trace.results
                    ),
                })
            return {
                "filename": f"rag-traces-{timestamp}.csv",
                "mime_type": "text/csv",
                "content": buffer.getvalue(),
            }

        if normalized == "json":
            payload = {
                "traces": [trace.to_dict() for trace in traces],
            }
            return {
                "filename": f"rag-traces-{timestamp}.json",
                "mime_type": "application/json",
                "content": json.dumps(payload, ensure_ascii=False, indent=2),
            }

        raise ValueError("format must be json or csv")


_trace_store: Optional[RetrievalTraceStore] = None


def get_trace_store() -> RetrievalTraceStore:
    global _trace_store
    if _trace_store is None:
        _trace_store = RetrievalTraceStore()
    return _trace_store


def reset_trace_store() -> None:
    global _trace_store
    _trace_store = None
