"""Safe runtime for low-code HTTP GET tools."""

from __future__ import annotations

from typing import Any, Dict

from app.utils.ssrf_guard import get_guarded_client, validate_public_https

from .base import BaseTool


class DeclarativeHttpTool(BaseTool):
    """Execute a public HTTPS GET endpoint with query parameters."""

    _MAX_RESPONSE_BYTES = 256 * 1024

    def __init__(self, endpoint_url: str, timeout_seconds: float = 10.0):
        self.endpoint_url = endpoint_url
        self.timeout_seconds = max(2.0, min(float(timeout_seconds), 30.0))

    @staticmethod
    def _validate_public_https(url: str) -> None:
        # Shared SSRF guard (kept as a staticmethod for callers/tests that
        # reference it directly).
        validate_public_https(url)

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        self._validate_public_https(self.endpoint_url)
        params = {key: str(value) for key, value in kwargs.items() if value is not None}
        # R15-14 moved this tool onto a shared connection pool; the LLM pool
        # has no connect-time IP validation, so tools get a dedicated guarded
        # pool instead (validates every resolved address at dial time against
        # DNS rebinding).  Redirects are never followed.
        client = get_guarded_client()
        response = await client.get(
            self.endpoint_url,
            params=params,
            timeout=self.timeout_seconds,
            headers={"Accept": "application/json, text/plain;q=0.9"},
        )
        response.raise_for_status()
        if len(response.content) > self._MAX_RESPONSE_BYTES:
            raise ValueError("接口响应超过 256 KB 限制")
        if "json" in response.headers.get("content-type", "").lower():
            return {"status_code": response.status_code, "data": response.json()}
        return {"status_code": response.status_code, "data": response.text}
