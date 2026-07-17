"""Tests for the in-process MetricsRegistry bounds.

TraceMiddleware observes EVERY request into the registry, so histogram
storage must be bounded — an unbounded list would grow with process
lifetime and every /metrics scrape would re-sort the full history.
"""

from app.api.metrics import HISTOGRAM_MAX_SAMPLES, MetricsRegistry


class TestMetricsRegistryBounds:
    def test_histogram_is_bounded(self):
        registry = MetricsRegistry()
        for i in range(HISTOGRAM_MAX_SAMPLES + 1000):
            registry.observe("http_latency", float(i))
        snapshot = registry.snapshot()
        assert len(snapshot["histograms"]["http_latency"]) == HISTOGRAM_MAX_SAMPLES

    def test_lifetime_count_and_sum_are_monotonic(self):
        registry = MetricsRegistry()
        for i in range(HISTOGRAM_MAX_SAMPLES + 1000):
            registry.observe("http_latency", 1.0)
        text = registry.to_prometheus()
        count_line = next(
            line for line in text.splitlines()
            if line.startswith("hfusionhub_http_latency_seconds_count ")
        )
        assert count_line.endswith(str(HISTOGRAM_MAX_SAMPLES + 1000))

    def test_prometheus_output_contains_quantiles(self):
        registry = MetricsRegistry()
        registry.observe("http_latency", 0.5)
        text = registry.to_prometheus()
        assert 'quantile="0.5"' in text
        assert 'quantile="0.95"' in text
        assert "hfusionhub_http_latency_seconds_sum" in text
