"""FastAPI middleware that reads X-Tenant-Id header and sets tenant context.

Isolation boundary: the Python service is only reachable by the Java backend
(via X-Internal-Token), and Java is the only authority that decides the active
tenant (resolved from the authenticated user + tenant_member membership).  This
middleware therefore trusts X-Tenant-Id only as an opaque propagation header and
NEVER falls back to a default tenant.

- Missing header  -> context is left unset (None). Data endpoints MUST call
  require_tenant() which rejects with 400/403. Health/liveness stay lenient.
- Invalid header  -> rejected with 400 immediately (no defaulting).
- Valid header    -> stored in contextvars for the request.
"""

from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.tenant.context import set_tenant_id, clear_tenant_id

logger = logging.getLogger(__name__)


class TenantMiddleware(BaseHTTPMiddleware):
    """Propagates X-Tenant-Id into contextvars; never defaults the tenant."""

    async def dispatch(self, request: Request, call_next) -> Response:
        header_value = request.headers.get("X-Tenant-Id")
        if header_value is not None and header_value.strip():
            try:
                tenant_id = int(header_value.strip())
                if tenant_id < 1:
                    raise ValueError("tenant id must be a positive integer")
            except (ValueError, TypeError):
                logger.warning("Invalid X-Tenant-Id header rejected: %s", header_value)
                return JSONResponse(
                    status_code=400,
                    content={"code": 400, "message": "Invalid X-Tenant-Id header"},
                )
            set_tenant_id(tenant_id)
        else:
            # No header: leave context unset. require_tenant() on data endpoints
            # will reject. This is fail-closed — no fallback to a default tenant.
            clear_tenant_id()

        try:
            response = await call_next(request)
            return response
        finally:
            clear_tenant_id()