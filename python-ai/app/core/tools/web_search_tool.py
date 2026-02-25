"""
Web Search Tool — search the web for information outside the knowledge base.

Uses a configurable search backend (DuckDuckGo by default, no API key required).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base import BaseTool

logger = logging.getLogger(__name__)


class WebSearchTool(BaseTool):
    """Search the web for recent or external information."""

    async def execute(
        self,
        query: str,
        max_results: int = 5,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Search the web using DuckDuckGo (no API key required).

        Args:
            query: Search query
            max_results: Maximum number of results (1-10)

        Returns:
            List of search results with title, url, and snippet
        """
        max_results = max(1, min(max_results, 10))

        try:
            # Use DuckDuckGo Instant Answer API (no key needed)
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

            # Abstract (direct answer)
            if data.get("AbstractText"):
                results.append({
                    "title": data.get("AbstractSource", "DuckDuckGo"),
                    "url": data.get("AbstractURL", ""),
                    "snippet": data.get("AbstractText", ""),
                    "type": "abstract",
                })

            # Related topics
            for topic in data.get("RelatedTopics", [])[:max_results]:
                if isinstance(topic, dict) and "Text" in topic:
                    results.append({
                        "title": topic.get("FirstURL", "").split("/")[-1].replace("_", " "),
                        "url": topic.get("FirstURL", ""),
                        "snippet": topic.get("Text", ""),
                        "type": "related",
                    })

            if not results:
                return [{"error": "No results found", "query": query}]

            return results[:max_results]

        except Exception as e:
            logger.warning("Web search failed: %s", e)
            return [{"error": f"Web search failed: {e}", "query": query}]
