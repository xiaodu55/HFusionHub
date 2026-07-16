"""
Tests for the shared SSRF guard (app.utils.ssrf_guard).

Focus on the defenses beyond the URL-level check already covered by
test_url_ingest.py: connect-time IP validation (anti DNS-rebinding),
manual redirect handling, and the guarded transport/client wiring.
No real network calls — DNS is stubbed and transports are mocked.
"""

import socket

import httpcore
import httpx
import pytest

from app.utils.ssrf_guard import (
    MAX_REDIRECTS,
    GuardedAsyncTransport,
    PublicNetworkBackend,
    SSRFBlockedError,
    fetch_public_html,
    get_guarded_client,
)


@pytest.fixture(autouse=True)
def _stub_dns(monkeypatch):
    """Map any hostname to a public address; keep IP literals as-is so
    private ranges are still rejected without touching real DNS."""

    import ipaddress

    def fake_getaddrinfo(host, port, *args, **kwargs):
        try:
            ipaddress.ip_address(host)
            resolved = host
        except ValueError:
            resolved = "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (resolved, port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


def _html_response(body: bytes = b"<html><title>t</title>hello</html>") -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "text/html"}, content=body)


# ── Manual redirect handling ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_redirect_to_link_local_ip_is_rejected():
    """A public URL that 302s to the cloud-metadata address must not be
    followed — the hop is re-validated and rejected."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://169.254.169.254/latest/meta-data/"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError):
        await fetch_public_html("https://example.com/start", client=client)


@pytest.mark.asyncio
async def test_redirect_to_http_downgrade_is_rejected():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://example.com/page"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError):
        await fetch_public_html("https://example.com/start", client=client)


@pytest.mark.asyncio
async def test_redirect_to_private_host_is_rejected():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://127.0.0.1:9000/docs"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError):
        await fetch_public_html("https://example.com/start", client=client)


@pytest.mark.asyncio
async def test_initial_private_url_rejected_before_any_request():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _html_response()

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError):
        await fetch_public_html("https://10.0.0.5/secret", client=client)
    assert calls == []


@pytest.mark.asyncio
async def test_public_redirect_chain_is_followed():
    hops: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hops.append(str(request.url))
        if len(hops) == 1:
            return httpx.Response(302, headers={"location": "https://b.example/final"})
        return _html_response()

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    response = await fetch_public_html("https://a.example/start", client=client)
    assert response.status_code == 200
    assert hops == ["https://a.example/start", "https://b.example/final"]


@pytest.mark.asyncio
async def test_relative_redirect_location_is_resolved():
    hops: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hops.append(str(request.url))
        if len(hops) == 1:
            return httpx.Response(302, headers={"location": "/next"})
        return _html_response()

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    response = await fetch_public_html("https://a.example/start", client=client)
    assert response.status_code == 200
    assert hops[1] == "https://a.example/next"


@pytest.mark.asyncio
async def test_redirect_loop_is_bounded():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://a.example/loop"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="重定向次数"):
        await fetch_public_html("https://a.example/loop", client=client)


# ── Connect-time validation (anti DNS-rebinding) ─────────────────────────

class _RecordingBackend(httpcore.AsyncNetworkBackend):
    """Stands in for the platform backend; records dialed addresses."""

    def __init__(self, fail_hosts: set[str] | None = None):
        self.dialed: list[tuple[str, int]] = []
        self._fail_hosts = fail_hosts or set()
        self.stream = object()  # sentinel stream, never used for I/O here

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if host in self._fail_hosts:
            raise httpcore.ConnectError(f"refused: {host}")
        self.dialed.append((host, port))
        return self.stream


@pytest.mark.asyncio
async def test_backend_rejects_private_resolution():
    async def resolver(host, port):
        return ["10.0.0.5"]

    backend = _RecordingBackend()
    guarded = PublicNetworkBackend(default=backend, resolver=resolver)
    with pytest.raises(SSRFBlockedError):
        await guarded.connect_tcp("rebind.example", 443)
    assert backend.dialed == []


@pytest.mark.asyncio
async def test_backend_rejects_when_any_answer_is_private():
    async def resolver(host, port):
        return ["93.184.216.34", "10.0.0.5"]

    backend = _RecordingBackend()
    guarded = PublicNetworkBackend(default=backend, resolver=resolver)
    with pytest.raises(SSRFBlockedError):
        await guarded.connect_tcp("mixed.example", 443)
    assert backend.dialed == []


@pytest.mark.asyncio
async def test_backend_dials_validated_address_not_hostname():
    async def resolver(host, port):
        return ["93.184.216.34"]

    backend = _RecordingBackend()
    guarded = PublicNetworkBackend(default=backend, resolver=resolver)
    stream = await guarded.connect_tcp("example.com", 443)
    assert stream is backend.stream
    assert backend.dialed == [("93.184.216.34", 443)]


@pytest.mark.asyncio
async def test_backend_falls_back_to_next_validated_address():
    async def resolver(host, port):
        return ["1.2.3.4", "5.6.7.8"]

    backend = _RecordingBackend(fail_hosts={"1.2.3.4"})
    guarded = PublicNetworkBackend(default=backend, resolver=resolver)
    stream = await guarded.connect_tcp("example.com", 443)
    assert stream is backend.stream
    assert backend.dialed == [("5.6.7.8", 443)]


@pytest.mark.asyncio
async def test_backend_maps_resolution_failure_to_connect_error():
    async def resolver(host, port):
        raise socket.gaierror("nxdomain")

    guarded = PublicNetworkBackend(default=_RecordingBackend(), resolver=resolver)
    with pytest.raises(httpcore.ConnectError):
        await guarded.connect_tcp("missing.example", 443)


@pytest.mark.asyncio
async def test_backend_empty_resolution_is_connect_error():
    async def resolver(host, port):
        return []

    guarded = PublicNetworkBackend(default=_RecordingBackend(), resolver=resolver)
    with pytest.raises(httpcore.ConnectError):
        await guarded.connect_tcp("empty.example", 443)


# ── Transport / client wiring ─────────────────────────────────────────────

def test_guarded_transport_wraps_pool_backend():
    transport = GuardedAsyncTransport()
    assert isinstance(transport._pool._network_backend, PublicNetworkBackend)


def test_guarded_client_is_singleton_and_safe():
    client = get_guarded_client()
    assert get_guarded_client() is client
    assert client.follow_redirects is False
    assert isinstance(client._transport, GuardedAsyncTransport)


def test_max_redirects_is_reasonable():
    assert 1 <= MAX_REDIRECTS <= 10
