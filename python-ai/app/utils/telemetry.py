"""
Unified Observability — OpenTelemetry integration for distributed tracing.

Provides:
- ``init_telemetry()`` — configure OTel exporter (OTLP or console)
- ``get_tracer()`` — get a named tracer instance
- ``get_meter()`` — get a named meter for custom metrics
- ``traced()`` — decorator / context manager for span creation
- ``record_llm_call()`` — record LLM invocation metrics
- ``record_tool_call()`` — record tool execution metrics

Configuration via env:
- ``OTEL_ENABLED`` — enable/disable (default: false)
- ``OTEL_EXPORTER_OTLP_ENDPOINT`` — OTLP collector endpoint
- ``OTEL_SERVICE_NAME`` — service name (default: hfusionhub-python-ai)

Gracefully degrades to no-op when disabled — no code changes required.
"""

from __future__ import annotations

import functools
import logging
from contextlib import contextmanager
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# ── Module state ────────────────────────────────────────────────────────
_enabled = False
_tracer_provider = None
_meter_provider = None


def init_telemetry(
    service_name: str = "hfusionhub-python-ai",
    otlp_endpoint: str | None = None,
    enabled: bool = False,
) -> None:
    """Initialise OpenTelemetry exporters.

    When *enabled* is False (default), all functions are no-ops.
    When enabled but no OTLP endpoint is provided, traces are logged to console.
    """
    global _enabled, _tracer_provider, _meter_provider

    if not enabled:
        logger.info("OpenTelemetry disabled — using no-op tracer")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.semconv.resource import ResourceAttributes

        resource = Resource.create({
            ResourceAttributes.SERVICE_NAME: service_name,
        })

        provider = TracerProvider(resource=resource)

        if otlp_endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        else:
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter
            exporter = ConsoleSpanExporter()

        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _tracer_provider = provider
        _enabled = True
        logger.info("OpenTelemetry initialised: service=%s endpoint=%s", service_name, otlp_endpoint or "console")
    except ImportError:
        logger.info("OpenTelemetry SDK not installed; install 'opentelemetry-api opentelemetry-sdk' for tracing")
    except Exception as e:
        logger.warning("OpenTelemetry initialisation failed: %s", e)


def get_tracer(name: str = "hfusionhub.ai"):
    """Return a tracer (no-op when telemetry is disabled)."""
    if _enabled:
        from opentelemetry import trace
        return trace.get_tracer(name)
    from opentelemetry.trace import NoOpTracer
    return NoOpTracer()


def traced(span_name: str, attrs: dict[str, Any] | None = None):
    """Decorator: wrap an async function in a span."""
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            from opentelemetry import trace  # 函数级导入：模块不可用时不影响正常路径
            tracer = get_tracer()
            with tracer.start_as_current_span(span_name, attributes=attrs or {}) as span:
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(trace.Status(trace.StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise
        return wrapper  # type: ignore[return-value]
    return decorator


@contextmanager
def trace_span(name: str, attrs: dict[str, Any] | None = None):
    """Context manager for a span."""
    from opentelemetry import trace  # 函数级导入：模块不可用时不影响正常路径
    tracer = get_tracer()
    with tracer.start_as_current_span(name, attributes=attrs or {}) as span:
        try:
            yield span
        except Exception as e:
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise


# ── Metric helpers ──────────────────────────────────────────────────────


LLM_CALL_COUNTER = "llm_calls_total"
LLM_LATENCY_HISTOGRAM = "llm_latency_seconds"
LLM_TOKEN_COUNTER = "llm_tokens_total"
TOOL_CALL_COUNTER = "tool_calls_total"
TOOL_LATENCY_HISTOGRAM = "tool_latency_seconds"


def record_llm_call(
    model: str,
    provider: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_s: float,
    *,
    is_error: bool = False,
    request_type: str = "chat",
) -> None:
    """Record an LLM invocation metric.  No-op when telemetry is disabled."""
    if not _enabled:
        return

    try:
        from opentelemetry import metrics
        meter = metrics.get_meter("hfusionhub.ai")

        counter = meter.create_counter(
            LLM_CALL_COUNTER, description="Total LLM invocations")
        counter.add(1, {
            "model": model,
            "provider": provider,
            "status": "error" if is_error else "success",
            "request_type": request_type,
        })

        hist = meter.create_histogram(
            LLM_LATENCY_HISTOGRAM, description="LLM call latency in seconds")
        hist.record(latency_s, {"model": model, "provider": provider})

        token_counter = meter.create_counter(
            LLM_TOKEN_COUNTER, description="Total tokens consumed")
        token_counter.add(prompt_tokens, {"model": model, "type": "prompt"})
        token_counter.add(completion_tokens, {"model": model, "type": "completion"})
    except Exception:
        pass  # metrics should never crash the app


def record_tool_call(
    tool_name: str,
    latency_s: float,
    *,
    is_error: bool = False,
) -> None:
    """Record a tool execution metric."""
    if not _enabled:
        return
    try:
        from opentelemetry import metrics
        meter = metrics.get_meter("hfusionhub.ai")

        counter = meter.create_counter(
            TOOL_CALL_COUNTER, description="Total tool invocations")
        counter.add(1, {"tool": tool_name, "status": "error" if is_error else "success"})

        hist = meter.create_histogram(
            TOOL_LATENCY_HISTOGRAM, description="Tool execution latency in seconds")
        hist.record(latency_s, {"tool": tool_name})
    except Exception:
        pass


# ── Convenience ─────────────────────────────────────────────────────────


def is_enabled() -> bool:
    return _enabled


__all__ = [
    "init_telemetry",
    "get_tracer",
    "traced",
    "trace_span",
    "record_llm_call",
    "record_tool_call",
    "is_enabled",
]
