"""LLM provider selection with runtime failover for configured providers."""

import asyncio
import concurrent.futures
import logging
import os
import time
from typing import Dict, Tuple

from .base import BaseLLM, ChatMessage, LLMResponse
from .deepseek_llm import DeepSeekLLM, _is_placeholder_key
from .failover_llm import FailoverLLM
from .gateway_llm import GatewayLLM
from .mock_llm import MockLLM
from .ollama_llm import OllamaLLM

__all__ = [
    "BaseLLM", "ChatMessage", "LLMResponse", "DeepSeekLLM", "OllamaLLM",
    "MockLLM", "FailoverLLM", "GatewayLLM", "get_llm",
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


def _gateway_stream_enabled() -> bool:
    """Whether agent/chat streaming routes through the ModelGateway.

    Controlled by ``MODEL_GATEWAY_STREAM_ENABLED`` (default ON in production so
    streaming gets rate limiting, circuit breaking, cost tracking and the
    response cache). Tests set it to ``false`` in conftest so the suite keeps
    exercising the legacy FailoverLLM / monkeypatched paths deterministically.
    """
    return os.getenv("MODEL_GATEWAY_STREAM_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def get_llm(model: str = None) -> BaseLLM:
    """Select the LLM for agent/chat use.

    When ``MODEL_GATEWAY_STREAM_ENABLED`` (default ON) and the gateway can
    route, returns a :class:`GatewayLLM` facade so streaming and non-streaming
    calls get rate limiting, circuit breaking, cost tracking and the exact-match
    response cache. Otherwise falls back to the concrete provider chain
    (mock / DeepSeek / Ollama / failover) — the same result ``get_llm()``
    produced before the gateway existed.
    """
    # Explicit test/development mock mode wins over everything — it must never
    # touch configured providers (including the gateway's).
    if os.getenv("LLM_ALLOW_MOCK", "false").lower() in ("true", "1", "yes"):
        logger.info("Using Mock LLM because LLM_ALLOW_MOCK=true")
        return MockLLM()

    if _gateway_stream_enabled():
        from .model_gateway import get_model_gateway

        gateway = get_model_gateway()
        if gateway._can_route():
            logger.info("Using GatewayLLM (ModelGateway) for model=%s", model or "<default>")
            return GatewayLLM(gateway, model=model)
    return _build_providers(model)


def _build_providers(model: str = None) -> BaseLLM:
    """Build the concrete provider chain (mock / DeepSeek / Ollama / failover).

    This is exactly what ``get_llm()`` returned before the ModelGateway branch
    existed. Kept separate so the gateway's own graceful-degradation path
    (``_legacy_chat`` / ``_legacy_stream``) can call it directly — re-entering
    ``get_llm()`` there would hit the gateway branch again and recurse forever
    on a resolve failure.
    """
    from app.utils.config import config

    # Explicit test/development mock mode must not call configured providers.
    if os.getenv("LLM_ALLOW_MOCK", "false").lower() in ("true", "1", "yes"):
        logger.info("Using Mock LLM because LLM_ALLOW_MOCK=true")
        return MockLLM()

    providers = []
    if config.DEEPSEEK_API_KEY and not _is_placeholder_key(config.DEEPSEEK_API_KEY):
        providers.append(DeepSeekLLM(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
            model=model or config.DEEPSEEK_MODEL,
        ))

    ollama_url = config.OLLAMA_BASE_URL
    ollama_available = _is_ollama_available(ollama_url)
    # A cold local Ollama probe can narrowly miss the bounded timeout even
    # though the service is starting successfully.  When a cloud provider is
    # already configured, retain Ollama as a runtime fallback candidate; the
    # FailoverLLM will handle a genuinely unavailable local service safely.
    # The same applies when Ollama would be the ONLY provider (e.g. the
    # DeepSeek key is still a scaffolding placeholder): dropping it because of
    # a cold probe would leave the user with no LLM at all — a cold local
    # Ollama is far more likely than a misconfigured one.
    if ollama_available or providers:
        providers.append(OllamaLLM(base_url=ollama_url, model=model or config.OLLAMA_MODEL))
    elif not providers:
        # Ollama is the only candidate (no cloud provider configured/valid).
        # Keep it so a cold probe does not leave the user with no LLM; the
        # FailoverLLM path (single provider) fails fast if truly unavailable.
        logger.warning(
            "Ollama cold probe failed (%s) and no cloud provider is configured; "
            "retaining Ollama as the sole LLM candidate",
            ollama_url,
        )
        providers.append(OllamaLLM(base_url=ollama_url, model=model or config.OLLAMA_MODEL))

    # Optional OpenAI-compatible backup provider (B2): any chat-completions
    # compatible endpoint (OpenAI, 通义, Kimi, …) joins the chain after
    # DeepSeek/Ollama so a configured primary failure can fail over.
    if config.OPENAI_COMPATIBLE_API_KEY and config.OPENAI_COMPATIBLE_BASE_URL \
            and not _is_placeholder_key(config.OPENAI_COMPATIBLE_API_KEY):
        providers.append(DeepSeekLLM(
            api_key=config.OPENAI_COMPATIBLE_API_KEY,
            base_url=config.OPENAI_COMPATIBLE_BASE_URL,
            model=model or config.OPENAI_COMPATIBLE_MODEL or config.DEEPSEEK_MODEL,
        ))

    if len(providers) > 1:
        return FailoverLLM(providers)
    if providers:
        return providers[0]

    raise RuntimeError(
        "No LLM provider available. Set DEEPSEEK_API_KEY or start Ollama, "
        "or set LLM_ALLOW_MOCK=true for development."
    )
