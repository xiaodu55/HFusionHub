"""
URL webpage ingestion — SSRF-guarded fetch + lightweight HTML-to-text.

Text extraction uses ``html.parser``; fetching goes through
``app.utils.ssrf_guard`` (https-only, per-hop redirect re-validation,
connect-time IP validation against DNS rebinding), with a bounded size
and timeout. ``validate_public_https`` is re-exported for callers that
only need the URL-level check.
"""

import html as html_lib
import re
from html.parser import HTMLParser

from app.utils.ssrf_guard import (
    fetch_public_html,
    validate_public_https,  # noqa: F401 — re-exported
)

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


def extract_title_from_html(raw: bytes) -> str | None:
    """Quick title extraction without a full parse (for the fetch response)."""
    match = re.search(rb"<title[^>]*>(.*?)</title>", raw, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    title = html_lib.unescape(match.group(1).decode("utf-8", errors="ignore"))
    return " ".join(title.split())[:200] or None


async def fetch_and_extract(url: str) -> tuple[str, str]:
    """Fetch a public HTTPS URL and return ``(title, extracted_text)``.

    Raises ``ValueError`` for SSRF/validation failures (including a
    redirect hop to a non-public URL) and ``httpx.HTTPError`` for
    transport failures. Redirects are followed manually with per-hop
    re-validation; the connection itself is guarded against DNS
    rebinding by ``ssrf_guard.PublicNetworkBackend``.
    """
    response = await fetch_public_html(
        url,
        timeout=FETCH_TIMEOUT_SECONDS,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; HFusionHub-UrlIngest/1.0)",
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        },
    )
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
