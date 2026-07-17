#!/usr/bin/env python
"""Alert simulation script for HFusionHub SLO monitoring.

Demonstrates that SLO alert rules would fire by recording metrics that breach
the defined thresholds. This script:
1. Records metrics that would trigger each alert category
2. Shows trace_id correlation in log output
3. Outputs a summary of which alerts would fire

Usage:
    python scripts/alert_simulation.py
"""

from __future__ import annotations

import json
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.api.metrics import (
    get_metrics,
    record_chat_request,
    record_embedding_request,
    record_eval_gate_failure,
    record_rag_retrieval,
    set_citation_faithfulness,
)
from app.utils.trace import clear_trace_id, create_trace_id


def simulate_chat_errors(n_errors: int = 50, n_total: int = 100):
    """Simulate a burst of chat errors to trigger ChatAvailabilityBelowSLO."""
    print(f"\n--- Simulating chat errors ({n_errors}/{n_total}) ---")
    for i in range(n_total):
        is_error = i < n_errors
        latency = random.uniform(0.5, 5.0) if not is_error else random.uniform(10.0, 60.0)
        record_chat_request(latency, is_error=is_error)


def simulate_high_latency(n_requests: int = 20):
    """Simulate high P95 latency to trigger ChatP95LatencyHigh."""
    print(f"\n--- Simulating high latency requests ({n_requests}) ---")
    for _ in range(n_requests):
        # Most requests are fast, but some hit 25-45s (above the 20s SLO)
        latency = random.choice([
            random.uniform(0.5, 2.0),    # 70% fast
            random.uniform(2.0, 10.0),   # 20% medium
            random.uniform(25.0, 45.0),  # 10% very slow (triggers alert)
        ])
        record_chat_request(latency)


def simulate_tool_failure():
    """Simulate tool failures to trigger ToolFailureRateHigh."""
    print("\n--- Simulating tool failures ---")
    for i in range(100):
        is_error = i < 5  # 5% error rate (above 1% threshold)
        record_chat_request(random.uniform(1.0, 3.0), is_error=is_error)


def simulate_eval_regression():
    """Simulate eval gate failure to trigger EvalQualityRegression."""
    print("\n--- Simulating eval gate failure ---")
    record_eval_gate_failure()


def simulate_low_citation_faithfulness():
    """Simulate low citation faithfulness."""
    print("\n--- Simulating low citation faithfulness (0.45) ---")
    set_citation_faithfulness(0.45)


def demonstrate_trace_correlation():
    """Show how trace_id correlates across simulated requests."""
    print("\n--- Trace ID correlation demo ---")
    for i in range(5):
        trace_id = create_trace_id()
        record_chat_request(random.uniform(1.0, 3.0))
        print(f"  Request {i+1}: trace_id={trace_id} latency={random.uniform(1.0, 3.0):.2f}s")
        clear_trace_id()


def print_alert_summary():
    """Print a summary of which alerts would fire based on recorded metrics."""
    metrics = get_metrics().snapshot()
    counters = metrics["counters"]
    histograms = metrics["histograms"]

    total_requests = counters.get("chat_requests_total", 0)
    total_errors = counters.get("chat_errors_total", 0)
    error_rate = total_errors / total_requests if total_requests > 0 else 0

    chat_latencies = histograms.get("chat_latency", [])
    p95_latency = sorted(chat_latencies)[int(len(chat_latencies) * 0.95)] if chat_latencies else 0

    eval_failures = counters.get("eval_gate_failures_total", 0)
    citation_faith = histograms.get("citation_faithfulness_current", [None])[0]

    print("\n" + "=" * 60)
    print("ALERT SIMULATION SUMMARY")
    print("=" * 60)
    print(f"Total chat requests: {total_requests}")
    print(f"Total chat errors: {total_errors}")
    print(f"Error rate: {error_rate:.2%}")
    print(f"P95 chat latency: {p95_latency:.2f}s")
    print(f"Eval gate failures: {eval_failures}")
    print(f"Citation faithfulness: {citation_faith}")
    print()

    alerts = []

    # Check each alert condition
    if total_requests > 0 and (1 - error_rate) < 0.999:
        alerts.append(("CRITICAL", "ChatAvailabilityBelowSLO",
                       f"Availability {1-error_rate:.2%} < 99.9% SLO"))

    if error_rate > 0.05:
        alerts.append(("WARNING", "ChatErrorRateHigh",
                       f"Error rate {error_rate:.2%} > 5%"))

    if p95_latency > 20:
        alerts.append(("WARNING", "ChatP95LatencyHigh",
                       f"P95 latency {p95_latency:.1f}s > 20s SLO"))

    if error_rate > 0.01:
        alerts.append(("CRITICAL", "ToolFailureRateHigh",
                       f"Tool failure rate {error_rate:.2%} > 1%"))

    if eval_failures > 0:
        alerts.append(("CRITICAL", "EvalQualityRegression",
                       f"{eval_failures} eval gate failures in 24h"))

    if citation_faith is not None and citation_faith < 0.60:
        alerts.append(("WARNING", "CitationFaithfulnessLow",
                       f"Citation faithfulness {citation_faith:.2%} < 60%"))

    if alerts:
        print("ALERTS THAT WOULD FIRE:")
        print("-" * 60)
        for severity, name, reason in alerts:
            print(f"  [{severity}] {name}: {reason}")
    else:
        print("No alerts would fire with current metrics.")

    print("=" * 60)
    return len(alerts)


def main():
    print("HFusionHub SLO Alert Simulation")
    print(f"Time: {datetime.now(UTC).isoformat()}")

    # Record baseline metrics
    for _ in range(100):
        record_chat_request(random.uniform(0.5, 2.0))
        record_rag_retrieval(random.uniform(0.1, 0.5))
        record_embedding_request(random.uniform(0.05, 0.2))

    # Simulate alert-triggering conditions
    simulate_chat_errors(50, 100)
    simulate_high_latency(20)
    simulate_tool_failure()
    simulate_eval_regression()
    simulate_low_citation_faithfulness()
    demonstrate_trace_correlation()

    # Print summary
    n_alerts = print_alert_summary()

    # Save simulation report
    report_path = PROJECT_ROOT.parent / "deploy" / "monitoring" / "alert_simulation_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "metrics_snapshot": get_metrics().snapshot(),
        "alerts_triggered": n_alerts,
        "description": "Simulated metrics that would trigger SLO alerts in Prometheus/Grafana",
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nSimulation report saved to: {report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
