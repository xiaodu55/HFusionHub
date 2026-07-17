"""Shared SSRF guard for outbound fetches of user-supplied URLs.

Three defense lines, applied together:

1. ``validate_public_https`` — pre-flight URL checks: HTTPS-only, no
   embedded credentials, no local/internal hostnames, and every DNS
   answer must be a global address.
2. ``PublicNetworkBackend`` — connection-level check: every address the
   HTTP client is about to dial is re-validated at connect time. This
   closes the DNS-rebinding TOCTOU window left by line 1 (validation
   resolves DNS once; the fetch would re-resolve and could get a
   different, private answer).
3. ``fetch_public_html`` — manual redirect handling: the client never
   auto-follows redirects; every hop's Location is re-validated, which
   also blocks HTTPS→HTTP downgrades and redirect-based bypasses.

Only stdlib + httpx/httpcore (already core dependencies). TLS is
unaffected by dial-by-IP: httpcore negotiates SNI/certificate against
the original hostname after the TCP connect.
"""

from __future__ import annotations

import ipaddress
import socket
import threading
from typing import Awaitable, Callable, Sequence
from urllib.parse import urljoin, urlparse

import anyio
import httpcore
import httpx

__all__ = [
    "SSRFBlockedError",
    "validate_public_https",
    "PublicNetworkBackend",
    "GuardedAsyncTransport",
    "get_guarded_client",
    "fetch_public_html",
]

MAX_REDIRECTS = 5
DEFAULT_TIMEOUT = 20.0


class SSRFBlockedError(ValueError):
    """Raised when a URL or a resolved address fails the SSRF guard."""


def validate_public_https(url: str) -> str:
    """Reject anything that is not a public HTTPS URL (SSRF guard).

    Returns the normalized URL on success; raises ValueError otherwise.
    """
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("仅支持公开的 HTTPS 网页地址")
    if parsed.username or parsed.password:
        raise ValueError("URL 不能包含用户名或密码")
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith(".local") or host.endswith(".internal"):
        raise ValueError("不允许访问本机或内网地址")
    try:
        addresses = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("网页域名无法解析") from exc
    for address in addresses:
        if not ipaddress.ip_address(address[4][0]).is_global:
            raise ValueError("不允许访问本机、内网或保留地址")
    return url


# ── Connection-level defense (anti DNS-rebinding) ────────────────────────

Resolver = Callable[[str, int], Awaitable[Sequence[str]]]


async def _default_resolver(host: str, port: int) -> Sequence[str]:
    """Resolve ``host`` on the event loop (anyio runs getaddrinfo in a
    worker thread) and return every resolved IP address."""
    infos = await anyio.getaddrinfo(host, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


def _default_network_backend() -> httpcore.AsyncNetworkBackend:
    # httpcore 1.x keeps its default backend in a private module.
    from httpcore._backends.auto import AutoBackend

    return AutoBackend()


class PublicNetworkBackend(httpcore.AsyncNetworkBackend):
    """Validates every resolved address before dialing it.

    DNS is resolved through ``resolver`` and each answer must be a global
    address; the connection is then made to a validated address only —
    never to the raw hostname, so a rebinding answer that appears between
    validation and connect can never be dialed.
    """

    def __init__(
        self,
        default: httpcore.AsyncNetworkBackend | None = None,
        resolver: Resolver | None = None,
    ):
        self._default = default if default is not None else _default_network_backend()
        self._resolver: Resolver = resolver if resolver is not None else _default_resolver

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Sequence[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            addresses = await self._resolver(host, port)
        except socket.gaierror as exc:
            raise httpcore.ConnectError(f"域名解析失败: {host}") from exc
        if not addresses:
            raise httpcore.ConnectError(f"域名解析失败: {host}")
        # Fail closed if ANY answer is non-global: an attacker controlling
        # DNS must not get a pass by mixing a public record into the set.
        for address in addresses:
            if not ipaddress.ip_address(address).is_global:
                raise SSRFBlockedError(f"拒绝连接到非公网地址 {address}（host={host}）")
        last_error: BaseException | None = None
        for address in addresses:
            try:
                return await self._default.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last_error = exc
        assert last_error is not None  # addresses is non-empty
        raise last_error

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Sequence[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        return await self._default.connect_unix_socket(
            path, timeout=timeout, socket_options=socket_options
        )

    async def sleep(self, seconds: float) -> None:
        await self._default.sleep(seconds)


class GuardedAsyncTransport(httpx.AsyncHTTPTransport):
    """AsyncHTTPTransport whose connection pool dials only public addresses.

    httpx does not expose httpcore's ``network_backend`` argument, so the
    pool's backend is swapped right after construction (no connections
    exist at that point, so the swap is safe).
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._pool._network_backend = PublicNetworkBackend(self._pool._network_backend)  # type: ignore[attr-defined]


_guarded_client: httpx.AsyncClient | None = None
_guarded_client_lock = threading.Lock()


def get_guarded_client() -> httpx.AsyncClient:
    """Process-wide SSRF-guarded client (never auto-follows redirects)."""
    global _guarded_client
    if _guarded_client is None:
        with _guarded_client_lock:
            if _guarded_client is None:
                _guarded_client = httpx.AsyncClient(
                    transport=GuardedAsyncTransport(),
                    timeout=DEFAULT_TIMEOUT,
                    follow_redirects=False,
                )
    return _guarded_client


# ── Redirect-level defense ───────────────────────────────────────────────

async def fetch_public_html(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    headers: dict[str, str] | None = None,
    client: httpx.AsyncClient | None = None,
) -> httpx.Response:
    """GET a public HTTPS URL, following redirects manually.

    Every hop (including the initial URL) passes ``validate_public_https``
    and is dialed through the SSRF-guarded transport. Returns the final
    non-redirect ``httpx.Response``; raises ``ValueError`` for guard
    violations and ``httpx.HTTPError`` for transport failures. Pass
    ``client`` to inject a test transport.
    """
    http_client = client if client is not None else get_guarded_client()
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        validate_public_https(current)
        response = await http_client.get(current, timeout=timeout, headers=headers)
        if response.is_redirect:
            location = response.headers.get("location")
            if not location:
                raise ValueError("重定向缺少 Location 头")
            current = urljoin(current, location)
            continue
        return response
    raise ValueError(f"重定向次数超过 {MAX_REDIRECTS} 次")
