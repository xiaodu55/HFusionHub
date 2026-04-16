"""Safe runtime for low-code HTTP GET tools."""

from __future__ import annotations

import ipaddress
import socket
from typing import Any, Dict
from urllib.parse import urlparse

import httpx

from .base import BaseTool


class DeclarativeHttpTool(BaseTool):
    """Execute a public HTTPS GET endpoint with query parameters."""

    _MAX_RESPONSE_BYTES = 256 * 1024

    def __init__(self, endpoint_url: str, timeout_seconds: float = 10.0):
        self.endpoint_url = endpoint_url
        self.timeout_seconds = max(2.0, min(float(timeout_seconds), 30.0))

    @staticmethod
    def _validate_public_https(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("低代码工具只允许公开 HTTPS 地址")
        host = parsed.hostname.lower()
        if host == "localhost" or host.endswith(".local"):
            raise ValueError("低代码工具不允许访问本机或内网地址")
        try:
            addresses = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ValueError("接口域名无法解析") from exc
        for address in addresses:
            if not ipaddress.ip_address(address[4][0]).is_global:
                raise ValueError("低代码工具不允许访问本机、内网或保留地址")

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        self._validate_public_https(self.endpoint_url)
        params = {key: str(value) for key, value in kwargs.items() if value is not None}
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=False,
            headers={"Accept": "application/json, text/plain;q=0.9"},
        ) as client:
            response = await client.get(self.endpoint_url, params=params)
        response.raise_for_status()
        if len(response.content) > self._MAX_RESPONSE_BYTES:
            raise ValueError("接口响应超过 256 KB 限制")
        if "json" in response.headers.get("content-type", "").lower():
            return {"status_code": response.status_code, "data": response.json()}
        return {"status_code": response.status_code, "data": response.text}
