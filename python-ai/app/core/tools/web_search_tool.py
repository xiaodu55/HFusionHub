"""
Web Search Tool — search the web for information outside the knowledge base.

Backends (B4):
  - duckduckgo (default, no API key required)
  - tavily / serper (API-key based, configurable via env)

Exposure to agents is flag-gated (``agent.web_search.enabled``); execution is
further gated by the policy engine (production lockout, mode, approval).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from .base import BaseTool

logger = logging.getLogger(__name__)


class WebSearchTool(BaseTool):
    """Search the web for recent or external information."""

    def __init__(self) -> None:
        self.provider = (os.getenv("WEB_SEARCH_PROVIDER", "duckduckgo") or "duckduckgo").lower().strip()
        self.api_key = (os.getenv("WEB_SEARCH_API_KEY", "") or "").strip()
        self.base_url = (os.getenv("WEB_SEARCH_BASE_URL", "") or "").strip()
        if self.provider not in ("duckduckgo", "tavily", "serper"):
            logger.warning("未知的 WEB_SEARCH_PROVIDER=%s，回退到 duckduckgo", self.provider)
            self.provider = "duckduckgo"

    async def execute(
        self,
        query: str,
        max_results: int = 5,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Search the web using the configured backend.

        Args:
            query: Search query
            max_results: Maximum number of results (1-10)

        Returns:
            List of search results with title, url, and snippet
        """
        max_results = max(1, min(max_results, 10))

        if self.provider == "tavily":
            return await self._search_tavily(query, max_results)
        if self.provider == "serper":
            return await self._search_serper(query, max_results)
        return await self._search_duckduckgo(query, max_results)

    async def _search_duckduckgo(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """DuckDuckGo Instant Answer API (no key needed)."""
        try:
            import httpx

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "https://api.duckduckgo.com/",
                    params={
                        "q": query,
                        "format": "json",
                        "no_html": 1,
                        "skip_disambig": 1,
                    },
                    headers={"User-Agent": "HFusionHub/1.0"},
                )
                resp.raise_for_status()
                data = resp.json()

            results: List[Dict[str, Any]] = []
            if data.get("AbstractText"):
                results.append({
                    "title": data.get("AbstractSource", "DuckDuckGo"),
                    "url": data.get("AbstractURL", ""),
                    "snippet": data.get("AbstractText", ""),
                    "type": "abstract",
                })
            # DuckDuckGo groups related topics into nested categories
            # ({Text: …} leaves and {Topics: […]}) — flatten both levels.
            def _flatten_topics(topics: List[Any]) -> List[Dict[str, Any]]:
                flat: List[Dict[str, Any]] = []
                for topic in topics:
                    if isinstance(topic, dict):
                        if "Text" in topic:
                            flat.append(topic)
                        elif isinstance(topic.get("Topics"), list):
                            flat.extend(_flatten_topics(topic["Topics"]))
                return flat

            for topic in _flatten_topics(data.get("RelatedTopics", []))[:max_results]:
                results.append({
                    "title": topic.get("FirstURL", "").split("/")[-1].replace("_", " "),
                    "url": topic.get("FirstURL", ""),
                    "snippet": topic.get("Text", ""),
                    "type": "related",
                })

            # Instant Answer API only returns curated cards and returns empty
            # for most plain queries — fall back to the lite HTML endpoint
            # (no API key required) which returns real search results.
            if not results:
                results = await self._search_duckduckgo_lite(query, max_results)
            return (results or [{"error": "No results found", "query": query}])[:max_results]
        except Exception as e:
            logger.warning("DuckDuckGo web search failed: %s", e)
            return [{"error": f"Web search failed: {e}", "query": query}]

    async def _search_duckduckgo_lite(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """DuckDuckGo Lite HTML search — real web results, no API key."""
        import re

        import httpx

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.post(
                    "https://lite.duckduckgo.com/lite/",
                    data={"q": query},
                    headers={"User-Agent": "Mozilla/5.0 (HFusionHub/1.0)"},
                )
                resp.raise_for_status()
            html = resp.text
            results: List[Dict[str, Any]] = []
            link_re = re.compile(r'<a rel="nofollow" href="([^"]+)"[^>]*>(.*?)</a>', re.S)
            snip_re = re.compile(r'class="result-snippet">(.*?)</td>', re.S)
            snippets = snip_re.findall(html)
            for i, (url, title_html) in enumerate(link_re.findall(html)):
                if url.startswith("//"):
                    url = "https:" + url
                title = re.sub(r"<[^>]+>", "", title_html).strip()
                snippet = ""
                if i < len(snippets):
                    snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()
                results.append({
                    "title": title or url.split("/")[-1],
                    "url": url,
                    "snippet": snippet,
                    "type": "web",
                })
            return results[:max_results]
        except Exception as e:
            logger.warning("DuckDuckGo lite search failed: %s", e)
            return []

    async def _search_tavily(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """Tavily Search API (needs WEB_SEARCH_API_KEY)."""
        if not self.api_key:
            return [{"error": "Tavily 需要配置 WEB_SEARCH_API_KEY", "query": query}]
        try:
            import httpx

            endpoint = self.base_url or "https://api.tavily.com/search"
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    endpoint,
                    json={
                        "api_key": self.api_key,
                        "query": query,
                        "max_results": max_results,
                        "search_depth": "basic",
                    },
                    headers={"User-Agent": "HFusionHub/1.0"},
                )
                resp.raise_for_status()
                data = resp.json()
            results = []
            for item in (data.get("results") or [])[:max_results]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("content", ""),
                    "type": "web",
                })
            return results or [{"error": "No results found", "query": query}]
        except Exception as e:
            logger.warning("Tavily web search failed: %s", e)
            return [{"error": f"Web search failed: {e}", "query": query}]

    async def _search_serper(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """Serper.dev Google Search API (needs WEB_SEARCH_API_KEY)."""
        if not self.api_key:
            return [{"error": "Serper 需要配置 WEB_SEARCH_API_KEY", "query": query}]
        try:
            import httpx

            endpoint = self.base_url or "https://google.serper.dev/search"
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    endpoint,
                    json={"q": query, "num": max_results},
                    headers={
                        "X-API-KEY": self.api_key,
                        "User-Agent": "HFusionHub/1.0",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            results = []
            for item in (data.get("organic") or [])[:max_results]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                    "type": "web",
                })
            return results or [{"error": "No results found", "query": query}]
        except Exception as e:
            logger.warning("Serper web search failed: %s", e)
            return [{"error": f"Web search failed: {e}", "query": query}]
