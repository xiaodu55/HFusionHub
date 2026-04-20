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
            for topic in data.get("RelatedTopics", [])[:max_results]:
                if isinstance(topic, dict) and "Text" in topic:
                    results.append({
                        "title": topic.get("FirstURL", "").split("/")[-1].replace("_", " "),
                        "url": topic.get("FirstURL", ""),
                        "snippet": topic.get("Text", ""),
                        "type": "related",
                    })
            return (results or [{"error": "No results found", "query": query}])[:max_results]
        except Exception as e:
            logger.warning("DuckDuckGo web search failed: %s", e)
            return [{"error": f"Web search failed: {e}", "query": query}]

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
