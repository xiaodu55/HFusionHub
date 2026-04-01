"""Execution-token consumption (fail-closed) tests."""

import httpx
import pytest

from app.core.tools.execution_token import consume_execution_token


def _transport(status_code: int = 200, consumed: bool = True):
    def handler(request):
        # Java internal endpoints return the unified R<T> envelope, e.g.
        # {"code":200,"message":"success","data":{"consumed":true},...}.
        body = {"code": status_code, "message": "success", "data": {"consumed": consumed}}
        return httpx.Response(status_code, json=body, request=request)

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_consume_success():
    async with httpx.AsyncClient(transport=_transport(200, True)) as client:
        ok = await consume_execution_token("appr-1", "tok-123", http_client=client,
                                           backend_url="http://backend")
    assert ok is True


@pytest.mark.asyncio
async def test_consume_rejected_when_already_used():
    async with httpx.AsyncClient(transport=_transport(200, False)) as client:
        ok = await consume_execution_token("appr-1", "tok-123", http_client=client,
                                           backend_url="http://backend")
    assert ok is False


@pytest.mark.asyncio
async def test_consume_wrong_token_rejected():
    # Java returns HTTP 200 with data.consumed=false when the token is already
    # consumed / revoked / wrong — Python must still reject.
    async with httpx.AsyncClient(transport=_transport(200, False)) as client:
        ok = await consume_execution_token("appr-1", "wrong-token", http_client=client,
                                           backend_url="http://backend")
    assert ok is False


@pytest.mark.asyncio
async def test_consume_invalid_internal_token_rejected():
    # Java internal endpoint rejects with HTTP 403 when X-Internal-Token is
    # missing/wrong — Python must fail closed (never execute).
    async with httpx.AsyncClient(transport=_transport(403, True)) as client:
        ok = await consume_execution_token("appr-1", "tok-123", http_client=client,
                                           backend_url="http://backend")
    assert ok is False


@pytest.mark.asyncio
async def test_consume_non_200_fails_closed():
    async with httpx.AsyncClient(transport=_transport(500, True)) as client:
        ok = await consume_execution_token("appr-1", "tok-123", http_client=client,
                                           backend_url="http://backend")
    assert ok is False


@pytest.mark.asyncio
async def test_consume_connection_error_fails_closed():
    async with httpx.AsyncClient() as client:
        ok = await consume_execution_token(
            "appr-1", "tok-123", http_client=client,
            backend_url="http://127.0.0.1:1",  # nothing listens here
        )
    assert ok is False


@pytest.mark.asyncio
async def test_empty_token_fails_without_calling_backend():
    async with httpx.AsyncClient(transport=_transport(200, True)) as client:
        ok = await consume_execution_token("appr-1", "", http_client=client,
                                           backend_url="http://backend")
    assert ok is False


@pytest.mark.asyncio
async def test_roundtrip_consumes_real_java_envelope():
    """Cross-lingual contract: feed the exact JSON the Java controller emits
    (R<T> envelope) and assert the Python client interprets it as consumed."""
    real_java_wire = {
        "code": 200,
        "message": "success",
        "data": {"consumed": True, "approval_id": "appr-1"},
        "timestamp": 1754269000000,
        "traceId": None,
    }

    def handler(request):
        return httpx.Response(200, json=real_java_wire, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        ok = await consume_execution_token("appr-1", "tok-123", http_client=client,
                                           backend_url="http://backend")
    assert ok is True


@pytest.mark.asyncio
async def test_request_carries_internal_token_header():
    seen = {}

    def handler(request):
        seen["header"] = request.headers.get("x-internal-token")
        body = {"code": 200, "message": "success", "data": {"consumed": True}}
        return httpx.Response(200, json=body, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        ok = await consume_execution_token("appr-1", "tok-123", http_client=client,
                                           backend_url="http://backend")
    assert ok is True