"""Tenant context propagation — mirrors app/utils/trace.py pattern.

Uses contextvars for async-safe tenant_id threading through the Agent
execution pipeline.  Set by TenantMiddleware from X-Tenant-Id header.
"""

from __future__ import annotations

import contextvars
from typing import Optional

_tenant_id: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar(
    "tenant_id", default=None
)


def set_tenant_id(tenant_id: int) -> None:
    """Set the current tenant ID for this async context."""
    _tenant_id.set(tenant_id)


def get_tenant_id() -> Optional[int]:
    """Get the current tenant ID, or None if not set."""
    return _tenant_id.get()


def require_tenant_id() -> int:
    """Get the current tenant ID, raising if absent."""
    tid = _tenant_id.get()
    if tid is None:
        raise RuntimeError(
            "No tenant context set. Ensure TenantMiddleware is installed."
        )
    return tid


def clear_tenant_id() -> None:
    """Clear the tenant context."""
    _tenant_id.set(None)
