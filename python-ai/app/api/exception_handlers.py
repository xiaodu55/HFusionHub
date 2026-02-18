"""
Global exception handlers for FastAPI
"""

import logging
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from app.core.exceptions import HFusionHubException

logger = logging.getLogger(__name__)


async def hfusionhub_exception_handler(
    request: Request,
    exc: HFusionHubException
) -> JSONResponse:
    """
    Handle HFusionHub custom exceptions
    """
    logger.warning("Handled %s: %s", exc.__class__.__name__, exc.message)

    return JSONResponse(
        status_code=exc.code,
        content=exc.to_dict()
    )


async def http_exception_handler(
    request: Request,
    exc: HTTPException
) -> JSONResponse:
    """
    Handle FastAPI HTTP exceptions
    """
    logger.warning("HTTP %s: %s", exc.status_code, exc.detail)

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.status_code,
            "message": str(exc.detail)
        }
    )


async def general_exception_handler(
    request: Request,
    exc: Exception
) -> JSONResponse:
    """
    Handle all other exceptions
    """
    # Keep traceback details in server logs; never return implementation
    # details, filesystem paths, or dependency errors to clients.
    logger.exception("Unexpected server error")

    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": "服务器内部错误，请稍后重试"
        }
    )
