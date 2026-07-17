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

        start = time.perf_counter()
        try:
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
