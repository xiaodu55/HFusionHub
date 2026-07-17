"""Plugin execution metrics — Prometheus-compatible counters and gauges.

Tracks execution counts, durations, resource usage, sandbox violations,
and circuit breaker events per plugin.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class MetricEntry:
    name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class PluginMetrics:
    """In-memory metrics collector for plugin execution.

    Exposes Prometheus-compatible metrics via /metrics endpoint.
    """

    def __init__(self):
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._recent_entries: list[MetricEntry] = []
        self._max_recent = 1000

    def inc_counter(self, name: str, value: float = 1.0, labels: dict[str, str] | None = None):
        key = self._make_key(name, labels)
        self._counters[key] += value
        self._record(MetricEntry(name=name, value=self._counters[key], labels=labels or {}))

    def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None):
        key = self._make_key(name, labels)
        self._gauges[key] = value
        self._record(MetricEntry(name=name, value=value, labels=labels or {}))

    def observe_histogram(self, name: str, value: float, labels: dict[str, str] | None = None):
        key = self._make_key(name, labels)
        self._histograms[key].append(value)
        if len(self._histograms[key]) > 1000:
            self._histograms[key] = self._histograms[key][-1000:]
        self._record(MetricEntry(name=name, value=value, labels=labels or {}))

    def record_execution(self, plugin_id: str, tool_name: str, success: bool, duration_ms: float):
        status = "success" if success else "error"
        labels = {"plugin_id": plugin_id, "tool_name": tool_name, "status": status}
        self.inc_counter("plugin_tool_executions_total", labels=labels)
        self.observe_histogram("plugin_tool_execution_duration_seconds", duration_ms / 1000.0, labels=labels)

    def record_sandbox_violation(self, plugin_id: str, violation_type: str):
        labels = {"plugin_id": plugin_id, "violation_type": violation_type}
        self.inc_counter("plugin_sandbox_violations_total", labels=labels)

    def record_circuit_breaker_trip(self, plugin_id: str):
        labels = {"plugin_id": plugin_id}
        self.inc_counter("plugin_circuit_breaker_trips_total", labels=labels)

    def record_container_resource(self, plugin_id: str, cpu_seconds: float, memory_bytes: int):
        labels = {"plugin_id": plugin_id}
        self.inc_counter("plugin_container_cpu_seconds_total", cpu_seconds, labels=labels)
        self.set_gauge("plugin_container_memory_bytes", float(memory_bytes), labels=labels)

    def render_prometheus(self) -> str:
        lines = []
        for key, value in sorted(self._counters.items()):
            name, labels_str = self._parse_key(key)
            lines.append(f'# TYPE {name} counter')
            lines.append(f'{name}{labels_str} {value}')

        for key, value in sorted(self._gauges.items()):
            name, labels_str = self._parse_key(key)
            lines.append(f'# TYPE {name} gauge')
            lines.append(f'{name}{labels_str} {value}')

        for key, values in sorted(self._histograms.items()):
            name, labels_str = self._parse_key(key)
            lines.append(f'# TYPE {name} histogram')
            if values:
                lines.append(f'{name}_sum{labels_str} {sum(values)}')
                lines.append(f'{name}_count{labels_str} {len(values)}')

        return "\n".join(lines) + "\n"

    def get_recent(self, limit: int = 50) -> list[MetricEntry]:
        return self._recent_entries[-limit:]

    def _record(self, entry: MetricEntry):
        self._recent_entries.append(entry)
        if len(self._recent_entries) > self._max_recent:
            self._recent_entries = self._recent_entries[-self._max_recent:]

    @staticmethod
    def _make_key(name: str, labels: dict[str, str] | None = None) -> str:
        if not labels:
            return name
        parts = sorted(labels.items())
        label_str = ",".join(f'{k}="{v}"' for k, v in parts)
        return f"{name}|{label_str}"

    @staticmethod
    def _parse_key(key: str) -> tuple:
        if "|" not in key:
            return key, ""
        name, label_str = key.split("|", 1)
        return name, "{" + label_str + "}"


_global_metrics: PluginMetrics | None = None


def get_plugin_metrics() -> PluginMetrics:
    global _global_metrics
    if _global_metrics is None:
        _global_metrics = PluginMetrics()
    return _global_metrics
