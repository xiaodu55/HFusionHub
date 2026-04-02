"""Tests for plugin execution metrics — Prometheus-compatible metrics."""

import pytest

from app.core.plugin.metrics import PluginMetrics, get_plugin_metrics


class TestPluginMetrics:
    def setup_method(self):
        self.metrics = PluginMetrics()

    def test_inc_counter(self):
        self.metrics.inc_counter("test_counter", labels={"a": "1"})
        self.metrics.inc_counter("test_counter", labels={"a": "1"})
        assert self.metrics._counters["test_counter|a=\"1\""] == 2.0

    def test_inc_counter_default(self):
        self.metrics.inc_counter("test_counter")
        assert self.metrics._counters["test_counter"] == 1.0

    def test_set_gauge(self):
        self.metrics.set_gauge("test_gauge", 42.0, labels={"b": "2"})
        assert self.metrics._gauges["test_gauge|b=\"2\""] == 42.0

    def test_observe_histogram(self):
        self.metrics.observe_histogram("test_hist", 1.0)
        self.metrics.observe_histogram("test_hist", 2.0)
        assert self.metrics._histograms["test_hist"] == [1.0, 2.0]

    def test_observe_histogram_cap(self):
        for i in range(1100):
            self.metrics.observe_histogram("test_hist", float(i))
        assert len(self.metrics._histograms["test_hist"]) <= 1000

    def test_record_execution(self):
        self.metrics.record_execution("p1", "tool1", success=True, duration_ms=100.0)
        key = 'plugin_tool_executions_total|plugin_id="p1",status="success",tool_name="tool1"'
        assert self.metrics._counters[key] == 1.0

    def test_record_execution_failure(self):
        self.metrics.record_execution("p1", "tool1", success=False, duration_ms=50.0)
        key = 'plugin_tool_executions_total|plugin_id="p1",status="error",tool_name="tool1"'
        assert self.metrics._counters[key] == 1.0

    def test_record_sandbox_violation(self):
        self.metrics.record_sandbox_violation("p1", "network")
        key = 'plugin_sandbox_violations_total|plugin_id="p1",violation_type="network"'
        assert self.metrics._counters[key] == 1.0

    def test_record_circuit_breaker_trip(self):
        self.metrics.record_circuit_breaker_trip("p1")
        key = 'plugin_circuit_breaker_trips_total|plugin_id="p1"'
        assert self.metrics._counters[key] == 1.0

    def test_record_container_resource(self):
        self.metrics.record_container_resource("p1", cpu_seconds=1.5, memory_bytes=1024000)
        cpu_key = 'plugin_container_cpu_seconds_total|plugin_id="p1"'
        mem_key = 'plugin_container_memory_bytes|plugin_id="p1"'
        assert self.metrics._counters[cpu_key] == 1.5
        assert self.metrics._gauges[mem_key] == 1024000.0

    def test_render_prometheus(self):
        self.metrics.inc_counter("my_counter", labels={"env": "test"})
        self.metrics.set_gauge("my_gauge", 99.0)
        output = self.metrics.render_prometheus()
        assert "# TYPE my_counter counter" in output
        assert "my_counter" in output
        assert "# TYPE my_gauge gauge" in output
        assert "my_gauge 99.0" in output

    def test_render_prometheus_empty(self):
        output = self.metrics.render_prometheus()
        assert output.strip() == ""

    def test_get_recent(self):
        self.metrics.inc_counter("c1")
        self.metrics.inc_counter("c1")
        recent = self.metrics.get_recent(limit=10)
        assert len(recent) == 2

    def test_get_recent_empty(self):
        recent = self.metrics.get_recent()
        assert recent == []


class TestGlobalMetrics:
    def test_singleton(self):
        m1 = get_plugin_metrics()
        m2 = get_plugin_metrics()
        assert m1 is m2
