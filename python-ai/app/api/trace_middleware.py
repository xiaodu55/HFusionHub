"""
FastAPI middleware that propagates distributed trace IDs.

Extracts ``X-Trace-ID`` from the incoming request header (set by the Java
backend's ``TraceFilter``).  If absent, a fresh UUID is generated.  The trace
ID is stored in ``contextvars`` (see :mod:`app.utils.trace`) so that any code
running within the same request can access it via ``get_trace_id()``.

The middleware also:

* Adds ``X-Trace-ID`` to every response header so clients can correlate logs.
* Adds ``trace_id`` to Python's ``logging.LoggerAdapter`` context for
  structured log output.
* Records basic request metrics (latency, status) into the in-process
  :class:`MetricsRegistry`.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.utils.trace import (
    HEADER_NAME,
    clear_trace_id,
    create_trace_id,
    set_trace_id,
)

logger = logging.getLogger("hfusionhub.trace")

# Client-supplied trace IDs flow into log lines AND response headers, so a
# crafted header must not inject newlines/control characters (log forgery)
# or unbounded junk.  Accept only short alnum/underscore/dash IDs (covers the
# 32-hex IDs generated here and UUID-style IDs from other services); anything
# else is discarded and a fresh ID is generated.
_TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _extract_w3c_context(request: Request):
    """提取 W3C traceparent（Java micrometer-tracing 自动注入），供 OTel
    服务端 span 作为其子 span——同一条调用链在 Tempo 中连贯可见。

    仅在 OTEL_ENABLED 且包可用时返回非 None；其余情况返回 None（零开销）。
    """
    traceparent = request.headers.get("traceparent")
    if not traceparent:
        return None
    try:
        from opentelemetry.trace.propagation.tracecontext import (
            TraceContextTextMapPropagator,
        )

        return TraceContextTextMapPropagator().extract(
            {"traceparent": traceparent})
    except Exception:
        return None


class TraceMiddleware(BaseHTTPMiddleware):
    """Extract / generate ``X-Trace-ID`` and attach it to the request context."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        raw = request.headers.get(HEADER_NAME)
        if raw and raw.strip() and _TRACE_ID_PATTERN.fullmatch(raw.strip()):
            trace_id = raw.strip()
            set_trace_id(trace_id)
        else:
            # 缺失或格式非法（日志注入风险）——生成新 ID（create_trace_id
            # 内部会安装 contextvar）。
            trace_id = create_trace_id()

        # Make trace_id available in logging via LoggerAdapter or directly
        request.state.trace_id = trace_id

        # OTel 分布式追踪：traceparent 存在且 OTel 已启用时，开一个服务端
        # span 包住整个请求（父级 = Java 侧 span，同一 trace id）。
        server_span_ctx = None
        try:
            from app.utils import telemetry as _telemetry
            if _telemetry.is_enabled():
                server_span_ctx = _extract_w3c_context(request)
        except Exception:
            server_span_ctx = None

        start = time.perf_counter()
        try:
            if server_span_ctx is not None:
                tracer = _telemetry.get_tracer("hfusionhub.http")
                span_cm = tracer.start_as_current_span(
                    f"{request.method} {request.url.path}",
                    context=server_span_ctx,
                    attributes={"http.request.method": request.method,
                                "url.path": request.url.path},
                )
                span_cm.__enter__()
                try:
                    response = await call_next(request)
                except Exception as exc:
                    span_cm.__exit__(type(exc), exc, exc.__traceback__)
                    raise
                span_cm.__exit__(None, None, None)
            else:
                response = await call_next(request)
        except Exception:
            # Re-raise; the global exception handler will deal with it
            raise
        finally:
            elapsed = time.perf_counter() - start
            status = getattr(response, "status_code", 0) if "response" in locals() else 0
            # Record metrics (best-effort; import cycles avoided by lazy import)
            try:
                from app.api.metrics import get_metrics
                get_metrics().inc("http_requests_total")
                get_metrics().observe("http_latency", elapsed)
                # Status-class counter so alerts can distinguish security events
                # (4xx: unauthorised access attempts) from server faults (5xx).
                # The registry only supports name-keyed counters, so encode the
                # status class into the metric name rather than adding labels.
                if status >= 400:
                    get_metrics().inc(f"http_status_{status // 100}xx_total")
            except Exception:
                pass

            # Log with trace_id
            logger.info(
                "%s %s -> %s (%.1fms) trace=%s",
                request.method,
                request.url.path,
                status,
                elapsed * 1000,
                trace_id,
            )
            clear_trace_id()

        response.headers[HEADER_NAME] = trace_id
        return response
