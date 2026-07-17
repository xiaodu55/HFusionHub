"""
Distributed trace context for the Python AI service.

Provides a request-scoped ``trace_id`` stored in ``contextvars`` so that every
log line and downstream call within a single request can be correlated with the
upstream Java caller (or any other caller that sets the ``X-Trace-ID`` header).
"""

from __future__ import annotations

import contextvars
import uuid

# Request-scoped trace ID, set by TraceMiddleware and readable anywhere in the
# same async task / thread.
_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trace_id", default=None
)

# Header name sent by Java and expected by this service
HEADER_NAME = "X-Trace-ID"


def get_trace_id() -> str | None:
    """Return the current trace ID, or ``None`` if no request is active."""
    return _trace_id_var.get()


def set_trace_id(trace_id: str) -> None:
    """Install a trace ID into the current context."""
    _trace_id_var.set(trace_id)


def create_trace_id() -> str:
    """Generate a fresh UUID-based trace ID and install it."""
    tid = uuid.uuid4().hex
    set_trace_id(tid)
    return tid


def clear_trace_id() -> None:
    """Remove the trace ID from the current context (cleanup)."""
    _trace_id_var.set(None)
