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
import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.utils.trace import (
    HEADER_NAME,
    clear_trace_id,
    create_trace_id,
    get_trace_id,
    set_trace_id,
)

logger = logging.getLogger("hfusionhub.trace")


class TraceMiddleware(BaseHTTPMiddleware):
    """Extract / generate ``X-Trace-ID`` and attach it to the request context."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        trace_id = request.headers.get(HEADER_NAME)
        if not trace_id or not trace_id.strip():
            trace_id = create_trace_id()
        else:
            set_trace_id(trace_id)

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
