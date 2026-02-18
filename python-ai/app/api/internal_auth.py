"""Authentication for requests made by the Java application service.

The Python service exposes parsing and retrieval internals and must not be
published as a browser-facing API.  A shared token is deliberately required
even on private networks so an accidental port exposure fails closed.
"""

import hmac

from fastapi import Header, HTTPException, status

from app.utils.config import config


def require_internal_token(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> None:
    expected = config.INTERNAL_API_TOKEN
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal API authentication is not configured",
        )
    if not x_internal_token or not hmac.compare_digest(x_internal_token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
