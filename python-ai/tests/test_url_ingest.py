"""
Tests for URL ingestion (A3): SSRF guard + HTML text extraction.

These tests exercise the pure functions only — no real network calls.
DNS lookups are stubbed so tests do not depend on network availability.
"""

import ipaddress
import socket

import pytest

from app.core.ingest.url_fetcher import (
    _TextExtractor,
    validate_public_https,
)


@pytest.fixture(autouse=True)
def _stub_dns(monkeypatch):
    """Return a public IPv4 for every hostname, so the SSRF guard's DNS
    check passes/fails purely on the address class, not on resolution."""

    def fake_getaddrinfo(host, port, *args, **kwargs):
        # Keep literal IPs so private/loopback ranges are rejected; map any
        # hostname to a public address so scheme/port checks still apply.
        try:
            ipaddress.ip_address(host)
            resolved = host
        except ValueError:
            resolved = "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (resolved, port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


# ── SSRF guard ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "http://example.com/page",          # http, not https
    "ftp://example.com/page",           # wrong scheme
    "https://localhost/page",           # localhost
    "https://127.0.0.1/page",           # loopback IP
    "https://10.0.0.5/page",            # private range
    "https://192.168.1.1/page",         # private range
    "https://172.16.0.1/page",          # private range
    "https://169.254.169.254/latest/meta-data/",  # link-local
    "https://user:pass@example.com/",   # credentials
    "https://intranet.local/page",      # .local TLD
])
def test_validate_public_https_rejects(url):
    with pytest.raises(ValueError):
        validate_public_https(url)


@pytest.mark.parametrize("url", [
    "https://example.com/page",
    "https://sub.example.org/a/b?q=1#frag",
    "https://example.com:8443/page",
])
def test_validate_public_https_accepts(url):
    assert validate_public_https(url) == url


# ── HTML text extraction ───────────────────────────────────────────────

def test_extractor_keeps_title_and_body():
    html = (
        "<html><head><title>  我的网页标题  </title>"
        "<style>.x{color:red}</style></head>"
        "<body><h1>一级标题</h1><p>第一段正文内容。</p>"
        "<p>第二段正文内容。</p><script>alert(1)</script>"
        "<nav>导航链接</nav><footer>页脚</footer></body></html>"
    )
    parser = _TextExtractor()
    parser.feed(html)

    assert parser.title == "我的网页标题"
    text = parser.text()
    assert "一级标题" in text
    assert "第一段正文内容" in text
    assert "第二段正文内容" in text
    # Script / style / nav / footer content must be stripped
    assert "alert" not in text
    assert "导航链接" not in text
    assert "页脚" not in text
    assert "color" not in text


def test_extractor_handles_plain_text():
    parser = _TextExtractor()
    parser.feed("纯文本内容，没有标签")
    assert "纯文本内容" in parser.text()


def test_extractor_empty_page():
    parser = _TextExtractor()
    parser.feed("<html><body></body></html>")
    assert parser.text() == ""
