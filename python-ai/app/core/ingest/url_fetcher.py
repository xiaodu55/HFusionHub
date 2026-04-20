"""
URL webpage ingestion — SSRF-guarded fetch + lightweight HTML-to-text.

Deliberately uses only the standard library: fetching with ``httpx``
(already a core dependency) and text extraction with ``html.parser``.
The SSRF guard mirrors ``app.core.tools.declarative_http_tool``:
HTTPS-only, no localhost / private / reserved addresses, bounded size and
timeout.
"""

import html as html_lib
import ipaddress
import re
import socket
from html.parser import HTMLParser
from typing import Optional, Tuple
from urllib.parse import urlparse

import httpx

# Page cap — a webpage larger than this is not worth indexing.
MAX_PAGE_BYTES = 2 * 1024 * 1024
FETCH_TIMEOUT_SECONDS = 20.0

# Block-level tags that separate text blocks; content inside these is skipped.
# Note: <head> is intentionally NOT skipped so <title> text is captured.
_SKIP_TAGS = {
    "script", "style", "noscript", "iframe", "svg",
    "nav", "footer", "header", "aside", "form", "button",
}
_BLOCK_TAGS = {
    "p", "div", "section", "article", "li", "tr", "br",
    "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "table",
}


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


class _TextExtractor(HTMLParser):
    """Strip tags and keep readable text (title + body)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str = ""
        self.parts: list = []
        self._skip_depth = 0
        self._in_title = False
        self._last_was_block = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
            return
        if tag in _BLOCK_TAGS and not self._skip_depth:
            self._push_block()

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag == "title":
            self._in_title = False
            return
        if tag in _BLOCK_TAGS and not self._skip_depth:
            self._push_block()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = " ".join(data.split())
        if not text:
            return
        if self._in_title:
            self.title = (self.title + " " + text).strip()
            return
        if self.parts and not self._last_was_block:
            self.parts.append(" ")
        self.parts.append(text)
        self._last_was_block = False

    def _push_block(self) -> None:
        if self.parts and not self._last_was_block:
            self.parts.append("\n")
            self._last_was_block = True

    def text(self) -> str:
        return "".join(self.parts).strip()


def extract_title_from_html(raw: bytes) -> Optional[str]:
    """Quick title extraction without a full parse (for the fetch response)."""
    match = re.search(rb"<title[^>]*>(.*?)</title>", raw, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    title = html_lib.unescape(match.group(1).decode("utf-8", errors="ignore"))
    return " ".join(title.split())[:200] or None


async def fetch_and_extract(url: str) -> Tuple[str, str]:
    """Fetch a public HTTPS URL and return ``(title, extracted_text)``.

    Raises ``ValueError`` for SSRF/validation failures and ``httpx.HTTPError``
    for transport failures.
    """
    validate_public_https(url)
    async with httpx.AsyncClient(
        timeout=FETCH_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; HFusionHub-UrlIngest/1.0)",
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        },
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        if len(response.content) > MAX_PAGE_BYTES:
            raise ValueError("网页内容超过 2MB 限制")

    content_type = response.headers.get("content-type", "").lower()
    if "html" not in content_type and not url.endswith((".html", ".htm")):
        # Non-HTML content (pdf, images, …) is out of scope for URL ingestion.
        raise ValueError("该地址返回的不是 HTML 网页内容")

    parser = _TextExtractor()
    parser.feed(response.text)
    title = parser.title or extract_title_from_html(response.content) or ""
    return title, parser.text()
