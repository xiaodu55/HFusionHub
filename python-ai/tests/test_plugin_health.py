"""Tests for plugin health probing and circuit breaker."""

import time
import pytest

from app.core.plugin.health import (
    PluginHealthProbe,
    PluginHealthConfig,
    HealthCheckResult,
    get_health_probe,
)


class TestHealthCheckResult:
    def test_creation(self):
        result = HealthCheckResult(
            plugin_id="p1",
            check_type="liveness",
            status="healthy",
        )
        assert result.plugin_id == "p1"
        assert result.check_type == "liveness"
        assert result.status == "healthy"
        assert result.duration_ms == 0.0
        assert result.checked_at > 0


class TestPluginHealthProbe:
    def setup_method(self):
        self.probe = PluginHealthProbe()

    def test_register_and_unregister(self):
        self.probe.register_plugin("p1")
        assert "p1" in self.probe._configs
        self.probe.unregister_plugin("p1")
        assert "p1" not in self.probe._configs

    def test_liveness_healthy(self):
        self.probe.register_plugin("p1")
        result = self.probe.check_liveness("p1")
        assert result.status == "healthy"
        assert result.check_type == "liveness"

    def test_liveness_with_check_fn(self):
        self.probe.register_plugin("p1")
        result = self.probe.check_liveness("p1", check_fn=lambda pid: True)
        assert result.status == "healthy"

    def test_liveness_unhealthy(self):
        self.probe.register_plugin("p1")
        result = self.probe.check_liveness("p1", check_fn=lambda pid: False)
        assert result.status == "unhealthy"

    def test_liveness_exception(self):
        self.probe.register_plugin("p1")
        def failing_check(pid):
            raise RuntimeError("check failed")
        result = self.probe.check_liveness("p1", check_fn=failing_check)
        assert result.status == "unhealthy"
        assert "check failed" in result.details["error"]

    def test_readiness_healthy(self):
        self.probe.register_plugin("p1")
        result = self.probe.check_readiness("p1")
        assert result.status == "healthy"

    def test_readiness_unhealthy(self):
        self.probe.register_plugin("p1")
        result = self.probe.check_readiness("p1", check_fn=lambda pid: False)
        assert result.status == "unhealthy"

    def test_health_history(self):
        self.probe.register_plugin("p1")
        self.probe.check_liveness("p1")
        self.probe.check_liveness("p1")
        history = self.probe.get_health_history("p1")
        assert len(history) == 2

    def test_health_history_limit(self):
        self.probe.register_plugin("p1")
        for _ in range(10):
            self.probe.check_liveness("p1")
        history = self.probe.get_health_history("p1", limit=3)
        assert len(history) == 3

    def test_circuit_breaker_no_failures(self):
        self.probe.register_plugin("p1")
        assert not self.probe.should_circuit_break("p1")

    def test_circuit_breaker_after_failures(self):
        config = PluginHealthConfig(unhealthy_threshold=3)
        self.probe.register_plugin("p1", config)
        self.probe.record_failure("p1")
        self.probe.record_failure("p1")
        assert not self.probe.should_circuit_break("p1")
        self.probe.record_failure("p1")
        assert self.probe.should_circuit_break("p1")

    def test_circuit_breaker_resets_on_success(self):
        config = PluginHealthConfig(unhealthy_threshold=3)
        self.probe.register_plugin("p1", config)
        self.probe.record_failure("p1")
        self.probe.record_failure("p1")
        self.probe.record_success("p1")
        assert not self.probe.should_circuit_break("p1")

    def test_record_success_resets_count(self):
        self.probe.register_plugin("p1")
        self.probe.record_failure("p1")
        self.probe.record_failure("p1")
        self.probe.record_success("p1")
        assert self.probe._failure_counts["p1"] == 0

    def test_record_failure_increments(self):
        self.probe.register_plugin("p1")
        self.probe.record_failure("p1")
        self.probe.record_failure("p1")
        assert self.probe._failure_counts["p1"] == 2

    def test_history_capped_at_100(self):
        self.probe.register_plugin("p1")
        for _ in range(150):
            self.probe.check_liveness("p1")
        history = self.probe.get_health_history("p1", limit=200)
        assert len(history) <= 100


class TestGlobalProbe:
    def test_singleton(self):
        probe1 = get_health_probe()
        probe2 = get_health_probe()
        assert probe1 is probe2
