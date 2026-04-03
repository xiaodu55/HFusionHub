"""FastAPI middleware that reads X-Tenant-Id header and sets tenant context.

Mirrors the pattern of app/api/trace_middleware.py.
"""

from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.tenant.context import set_tenant_id, clear_tenant_id

logger = logging.getLogger(__name__)

DEFAULT_TENANT_ID = 1  # Fallback for backward compatibility


class TenantMiddleware(BaseHTTPMiddleware):
    """Extracts X-Tenant-Id from request headers and stores in contextvars."""

    async def dispatch(self, request: Request, call_next) -> Response:
        header_value = request.headers.get("X-Tenant-Id")
        if header_value and header_value.strip():
            try:
                set_tenant_id(int(header_value))
            except (ValueError, TypeError):
                logger.warning("Invalid X-Tenant-Id header: %s", header_value)
                set_tenant_id(DEFAULT_TENANT_ID)
        else:
            # Backward compatibility: default to tenant 1
            set_tenant_id(DEFAULT_TENANT_ID)

        try:
            response = await call_next(request)
            return response
        finally:
            clear_tenant_id()
