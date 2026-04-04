"""Shared FastAPI dependencies used across business routers.

Central place for cross-cutting guards such as the hard tenant boundary.  The
Python service is only reachable via the internal token; on top of that every
data-touching endpoint must also carry a valid, explicit tenant context — there
is deliberately NO default tenant.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from app.core.tenant.context import get_tenant_id


def require_tenant() -> int:
    """Return the current tenant id or reject the request fail-closed.

    A missing or absent tenant context means the request cannot be attributed
    to a tenant and must not read or write tenant-scoped data.  No fallback to
    a default tenant id is allowed.
    """
    tenant_id = get_tenant_id()
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required but missing",
        )
    return tenant_id