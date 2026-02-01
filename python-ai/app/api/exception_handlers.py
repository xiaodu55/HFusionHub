"""
Global exception handlers for FastAPI
"""

import traceback
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from app.core.exceptions import HFusionHubException


async def hfusionhub_exception_handler(
    request: Request,
    exc: HFusionHubException
) -> JSONResponse:
    """
    Handle HFusionHub custom exceptions
    """
    print(f"[Exception] {exc.__class__.__name__}: {exc.message}")
    if exc.details:
        print(f"[Exception] Details: {exc.details}")

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
    print(f"[HTTPException] {exc.status_code}: {exc.detail}")

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
    # Log the full traceback
    print(f"[Exception] Unexpected error: {exc}")
    print(f"[Exception] Traceback:\n{traceback.format_exc()}")

    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": f"服务器内部错误: {str(exc)}"
        }
    )
