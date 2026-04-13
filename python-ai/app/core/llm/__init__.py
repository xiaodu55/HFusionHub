"""LLM provider selection with runtime failover for configured providers."""

import asyncio
import concurrent.futures
import logging
import os
import time
from typing import Dict, Tuple

from .base import BaseLLM, ChatMessage, LLMResponse
from .deepseek_llm import DeepSeekLLM
from .failover_llm import FailoverLLM
from .mock_llm import MockLLM
from .ollama_llm import OllamaLLM

__all__ = [
    "BaseLLM", "ChatMessage", "LLMResponse", "DeepSeekLLM", "OllamaLLM",
    "MockLLM", "FailoverLLM", "get_llm",
]

logger = logging.getLogger(__name__)

# ``get_llm`` is deliberately synchronous because it is used throughout the
# existing agent/RAG code. A cold Ollama probe must therefore be short, and it
# must never run once per request. Cache both successes and failures; a URL
# change gets its own cache entry for tests and runtime reconfiguration.
_OLLAMA_PROBE_TIMEOUT_SECONDS = 0.5
_OLLAMA_PROBE_TTL_SECONDS = 30.0
_ollama_probe_cache: Dict[str, Tuple[float, bool]] = {}

# Shared thread-pool for non-blocking HTTP probes — avoids blocking the
# FastAPI event loop when get_llm() is called from an async context.
_probe_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="llm-probe")


def _probe_ollama_sync(base_url: str) -> bool:
    """Perform a single synchronous HTTP probe (runs in a thread-pool)."""
    try:
        import httpx

        return httpx.get(
            f"{base_url}/api/tags", timeout=_OLLAMA_PROBE_TIMEOUT_SECONDS
        ).status_code == 200
    except Exception as exc:
        logger.debug("Ollama probe failed for %s: %s", base_url, exc)
        return False


def _is_ollama_available(base_url: str) -> bool:
    """Return cached Ollama availability, refreshing at a bounded interval.

    When called from an async context (the common case in FastAPI handlers),
    the probe runs in a thread-pool to avoid blocking the event loop.
    When called from a synchronous context, it runs inline.
    """
    normalized_url = base_url.rstrip("/")
    now = time.monotonic()
    cached = _ollama_probe_cache.get(normalized_url)
    if cached is not None and now - cached[0] < _OLLAMA_PROBE_TTL_SECONDS:
        return cached[1]

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running event loop — synchronous context; probe inline.
        try:
            available = _probe_ollama_sync(normalized_url)
        except Exception as exc:
            logger.debug("Ollama sync probe failed: %s", exc)
            available = False
    else:
        # Async context — offload to thread pool so the event loop stays free.
        try:
            future = _probe_executor.submit(_probe_ollama_sync, normalized_url)
            available = future.result(timeout=_OLLAMA_PROBE_TIMEOUT_SECONDS + 0.5)
        except Exception as exc:
            logger.debug("Ollama async probe failed: %s", exc)
            available = False

    _ollama_probe_cache[normalized_url] = (now, available)
    return available


def get_llm(model: str = None) -> BaseLLM:
    """Select configured providers; runtime failures use a bounded failover."""
    from app.utils.config import config

    # Explicit test/development mock mode must not call configured providers.
    if os.getenv("LLM_ALLOW_MOCK", "false").lower() in ("true", "1", "yes"):
        logger.info("Using Mock LLM because LLM_ALLOW_MOCK=true")
        return MockLLM()

    providers = []
    if config.DEEPSEEK_API_KEY:
        providers.append(DeepSeekLLM(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
            model=model or config.DEEPSEEK_MODEL,
        ))

    ollama_url = config.OLLAMA_BASE_URL
    if _is_ollama_available(ollama_url):
        providers.append(OllamaLLM(base_url=ollama_url, model=model or config.OLLAMA_MODEL))

    if len(providers) > 1:
        return FailoverLLM(providers)
    if providers:
        return providers[0]

    raise RuntimeError(
        "No LLM provider available. Set DEEPSEEK_API_KEY or start Ollama, "
        "or set LLM_ALLOW_MOCK=true for development."
    )
