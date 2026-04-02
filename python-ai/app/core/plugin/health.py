"""Plugin health probing — liveness and readiness checks.

Runs periodic health checks on installed plugins to detect failures
and trigger circuit breaker logic.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class HealthCheckResult:
    """Result of a single health check."""
    plugin_id: str
    check_type: str  # "liveness" | "readiness"
    status: str      # "healthy" | "unhealthy"
    details: Optional[Dict[str, Any]] = None
    duration_ms: float = 0.0
    checked_at: float = field(default_factory=time.time)


@dataclass
class PluginHealthConfig:
    """Health check configuration for a plugin."""
    liveness_enabled: bool = True
    readiness_enabled: bool = True
    check_interval_seconds: float = 60.0
    timeout_seconds: float = 10.0
    unhealthy_threshold: int = 3  # consecutive failures before circuit open


class PluginHealthProbe:
    """Periodic health checks for installed plugins."""

    def __init__(self):
        self._history: Dict[str, List[HealthCheckResult]] = {}
        self._failure_counts: Dict[str, int] = {}
        self._configs: Dict[str, PluginHealthConfig] = {}
        self._running = False

    def register_plugin(self, plugin_id: str, config: Optional[PluginHealthConfig] = None):
        """Register a plugin for health monitoring."""
        self._configs[plugin_id] = config or PluginHealthConfig()
        self._history.setdefault(plugin_id, [])
        self._failure_counts.setdefault(plugin_id, 0)

    def unregister_plugin(self, plugin_id: str):
        """Remove a plugin from health monitoring."""
        self._configs.pop(plugin_id, None)
        self._history.pop(plugin_id, None)
        self._failure_counts.pop(plugin_id, None)

    def check_liveness(self, plugin_id: str, check_fn: Optional[Callable] = None) -> HealthCheckResult:
        """Check if a plugin is alive (can be imported and basic functions work)."""
        start = time.monotonic()
        try:
            if check_fn:
                result = check_fn(plugin_id)
                status = "healthy" if result else "unhealthy"
                details = {"check_result": result}
            else:
                status = "healthy"
                details = {"message": "basic liveness check passed"}

            elapsed_ms = round((time.monotonic() - start) * 1000, 2)
            check_result = HealthCheckResult(
                plugin_id=plugin_id,
                check_type="liveness",
                status=status,
                details=details,
                duration_ms=elapsed_ms,
            )
        except Exception as e:
            elapsed_ms = round((time.monotonic() - start) * 1000, 2)
            check_result = HealthCheckResult(
                plugin_id=plugin_id,
                check_type="liveness",
                status="unhealthy",
                details={"error": str(e)},
                duration_ms=elapsed_ms,
            )

        self._record_result(check_result)
        return check_result

    def check_readiness(self, plugin_id: str, check_fn: Optional[Callable] = None) -> HealthCheckResult:
        """Check if a plugin is ready to serve requests."""
        start = time.monotonic()
        try:
            if check_fn:
                result = check_fn(plugin_id)
                status = "healthy" if result else "unhealthy"
                details = {"check_result": result}
            else:
                status = "healthy"
                details = {"message": "readiness check passed"}

            elapsed_ms = round((time.monotonic() - start) * 1000, 2)
            check_result = HealthCheckResult(
                plugin_id=plugin_id,
                check_type="readiness",
                status=status,
                details=details,
                duration_ms=elapsed_ms,
            )
        except Exception as e:
            elapsed_ms = round((time.monotonic() - start) * 1000, 2)
            check_result = HealthCheckResult(
                plugin_id=plugin_id,
                check_type="readiness",
                status="unhealthy",
                details={"error": str(e)},
                duration_ms=elapsed_ms,
            )

        self._record_result(check_result)
        return check_result

    def get_health_history(self, plugin_id: str, limit: int = 20) -> List[HealthCheckResult]:
        """Get recent health check history for a plugin."""
        return self._history.get(plugin_id, [])[-limit:]

    def should_circuit_break(self, plugin_id: str) -> bool:
        """Check if the circuit breaker should trip for a plugin."""
        config = self._configs.get(plugin_id, PluginHealthConfig())
        failures = self._failure_counts.get(plugin_id, 0)
        return failures >= config.unhealthy_threshold

    def record_success(self, plugin_id: str):
        """Record a successful execution (resets failure count)."""
        self._failure_counts[plugin_id] = 0

    def record_failure(self, plugin_id: str):
        """Record a failed execution (increments failure count)."""
        self._failure_counts[plugin_id] = self._failure_counts.get(plugin_id, 0) + 1

    def _record_result(self, result: HealthCheckResult):
        history = self._history.setdefault(result.plugin_id, [])
        history.append(result)
        if len(history) > 100:
            self._history[result.plugin_id] = history[-100:]

        if result.status == "unhealthy":
            self._failure_counts[result.plugin_id] = self._failure_counts.get(result.plugin_id, 0) + 1
        else:
            self._failure_counts[result.plugin_id] = 0


_global_probe: Optional[PluginHealthProbe] = None


def get_health_probe() -> PluginHealthProbe:
    global _global_probe
    if _global_probe is None:
        _global_probe = PluginHealthProbe()
    return _global_probe
