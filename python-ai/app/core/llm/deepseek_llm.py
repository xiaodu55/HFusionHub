"""
DeepSeek LLM Implementation
Uses DeepSeek API for chat completion
"""

import json
import time
from collections import OrderedDict
from typing import List, AsyncGenerator, NoReturn, Optional

import httpx

from .base import BaseLLM, ChatMessage, LLMResponse
from .http_client import get_shared_client, post_with_retry

# Non-streaming response cache (P2).  Keyed by
# (model, temperature, max_tokens, api_key, normalized messages) so repeated
# FAQ-style prompts reuse the answer within the TTL instead of re-billing.
# Module-level so all DeepSeekLLM instances share one bounded LRU.
# _response_cache holds exact keys; _fuzzy_response_cache holds normalized
# (whitespace-collapsed / casefolded) keys as a secondary lookup so trivially
# identical prompts hit the same entry.
_response_cache: "OrderedDict[tuple, tuple[float, LLMResponse]]" = OrderedDict()
_fuzzy_response_cache: "OrderedDict[tuple, tuple[float, LLMResponse]]" = OrderedDict()
_RESPONSE_CACHE_MAX = 1024


def _cache_key(
    model: str,
    temperature: float,
    max_tokens: int,
    api_key: str,
    messages: List[ChatMessage],
) -> tuple:
    return (
        model,
        temperature,
        max_tokens,
        api_key,
        tuple((msg.role, msg.content) for msg in messages),
    )


def _normalise_text(text: str) -> str:
    """Collapse whitespace runs and case differences for fuzzy cache lookup."""
    return " ".join(text.split()).casefold()


def _fuzzy_cache_key(key: tuple) -> tuple:
    """Derive the normalized lookup key from an exact cache key."""
    model, temperature, max_tokens, api_key, messages = key
    return (
        model,
        temperature,
        max_tokens,
        api_key,
        tuple((role, _normalise_text(content)) for role, content in messages),
    )


def _fuzzy_enabled() -> bool:
    from app.utils.config import config
    return config.LLM_RESPONSE_CACHE_FUZZY_ENABLED


def _cache_get(key: tuple) -> Optional[LLMResponse]:
    entry = _response_cache.get(key)
    if entry is None and _fuzzy_enabled():
        entry = _fuzzy_response_cache.get(_fuzzy_cache_key(key))
    if entry is None:
        return None
    cached_at, cached = entry
    if time.monotonic() - cached_at < _cache_ttl_seconds():
        return cached
    # Expired — drop both the exact entry and its fuzzy twin.
    _response_cache.pop(key, None)
    _fuzzy_response_cache.pop(_fuzzy_cache_key(key), None)
    return None


def _cache_put(key: tuple, response: LLMResponse) -> None:
    now = time.monotonic()
    _response_cache[key] = (now, response)
    if len(_response_cache) > _RESPONSE_CACHE_MAX:
        _response_cache.popitem(last=False)
    fuzzy_key = _fuzzy_cache_key(key)
    if fuzzy_key != key:
        _fuzzy_response_cache[fuzzy_key] = (now, response)
        if len(_fuzzy_response_cache) > _RESPONSE_CACHE_MAX:
            _fuzzy_response_cache.popitem(last=False)


def _cache_ttl_seconds() -> float:
    from app.utils.config import config
    return config.LLM_RESPONSE_CACHE_TTL_SECONDS


# Placeholder values that indicate the user has NOT configured a real API key
# yet (copied from .env.example / scaffolding).  Treating these as "configured"
# makes every chat request burn a failing upstream call (401) before failover
# kicks in, which adds seconds of latency to the first token.
_PLACEHOLDER_KEYS = {
    "your_api_key_here",
    "your_api_key",
    "your-key-here",
    "sk-xxx",
    "xxx",
    "changeme",
}


def _is_placeholder_key(api_key: str) -> bool:
    if not api_key:
        return True
    lowered = api_key.strip().lower()
    if lowered in _PLACEHOLDER_KEYS:
        return True
    # Common scaffolding shapes: "your_..._key", "your-...-key", "xxx...".
    if lowered.startswith("your_") and lowered.endswith("_key"):
        return True
    if lowered.startswith("your-") and lowered.endswith("-key"):
        return True
    if lowered.startswith("xxx"):
        return True
    return False


class DeepSeekLLM(BaseLLM):
    """DeepSeek LLM implementation"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-v4-flash",
        *,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        retry_backoff: Optional[float] = None,
    ):
        from app.utils.config import config

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        # Connection/timeout/retry knobs default to the environment-config
        # values (see app/utils/config.py); per-instance overrides let
        # request-scoped providers (user_model_config) tune behaviour.
        self.timeout = timeout if timeout is not None else config.LLM_HTTP_TIMEOUT_SECONDS
        self.max_retries = max_retries if max_retries is not None else config.LLM_MAX_RETRIES
        self.retry_backoff = retry_backoff if retry_backoff is not None else config.LLM_RETRY_BACKOFF_SECONDS
        self._available = not _is_placeholder_key(api_key)

    def _chat_completions_url(self) -> str:
        # Accept the two common Base URL forms users encounter in provider docs:
        # https://host and https://host/v1.
        if self.base_url.endswith("/v1"):
            return f"{self.base_url}/chat/completions"
        return f"{self.base_url}/v1/chat/completions"

    @staticmethod
    def _raise_api_error(response: httpx.Response) -> NoReturn:
        try:
            payload = response.json()
            message = payload.get("error", {}).get("message") or response.text
        except (ValueError, AttributeError):
            message = response.text
        detail = (message or "unknown upstream error").strip()[:1000]
        raise RuntimeError(
            f"DeepSeek API request failed ({response.status_code}): {detail}"
        )

    @classmethod
    def _ensure_success(cls, response: httpx.Response) -> None:
        if response.is_error:
            cls._raise_api_error(response)

    async def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> LLMResponse:
        """Chat completion via DeepSeek API.

        Non-streaming responses are cached on an exact (model, temperature,
        max_tokens, messages) key within ``LLM_RESPONSE_CACHE_TTL_SECONDS`` so
        repeated FAQ-style prompts do not re-bill.  The cache is shared across
        all DeepSeekLLM instances and bounded to ``_RESPONSE_CACHE_MAX``
        entries (LRU eviction).
        """
        from app.utils.config import config

        key = _cache_key(self.model, temperature, max_tokens, self.api_key, messages)
        if config.LLM_RESPONSE_CACHE_TTL_SECONDS > 0:
            cached = _cache_get(key)
            if cached is not None:
                return cached

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Convert ChatMessage to API format
        api_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

        payload = {
            "model": self.model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs
        }

        client = get_shared_client(owner="deepseek", timeout=self.timeout)
        response = await post_with_retry(
            client,
            self._chat_completions_url(),
            headers=headers,
            json=payload,
            timeout=self.timeout,
            max_retries=self.max_retries,
            backoff=self.retry_backoff,
        )
        self._ensure_success(response)
        data = response.json()

        # Extract response
        choice = data["choices"][0]
        content = choice["message"]["content"]
        usage = data.get("usage", {})

        result = LLMResponse(
            content=content,
            model=self.model,
            token_count=usage.get("total_tokens", 0),
            finish_reason=choice.get("finish_reason", "stop")
        )
        if config.LLM_RESPONSE_CACHE_TTL_SECONDS > 0:
            _cache_put(key, result)
        return result

    async def chat_stream(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Chat completion with streaming via DeepSeek API.

        The exact-match response cache (same key space as ``chat``) is
        consulted before the upstream call and populated on completion, so
        repeated FAQ-style prompts do not re-bill even on the streaming path.
        A cache hit is yielded as a single chunk to preserve SSE semantics.
        """
        from app.utils.config import config

        key = _cache_key(self.model, temperature, max_tokens, self.api_key, messages)
        if config.LLM_RESPONSE_CACHE_TTL_SECONDS > 0:
            cached = _cache_get(key)
            if cached is not None:
                yield cached.content
                return

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Convert ChatMessage to API format
        api_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

        payload = {
            "model": self.model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            **kwargs
        }

        # Streaming deliberately does not retry: once the generator starts
        # yielding it cannot transparently restart, and the failover layer
        # already fails over before the first chunk. The shared client still
        # gives connection reuse on the stream path.
        client = get_shared_client(owner="deepseek", timeout=self.timeout)
        async with client.stream(
            "POST",
            self._chat_completions_url(),
            headers=headers,
            json=payload,
            timeout=self.timeout,
        ) as response:
            self._ensure_success(response)

            parts: List[str] = []
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break

                    # 空 choices / 非字典载荷与 JSONDecodeError 一样按心跳行跳过
                    # （此前只捕获 JSONDecodeError，choices 为空时 IndexError 直接崩流）
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    choices = data.get("choices") or []
                    if not choices:
                        continue
                    delta = (choices[0] or {}).get("delta") or {}
                    content = delta.get("content", "")
                    if content:
                        parts.append(content)
                        yield content

            if config.LLM_RESPONSE_CACHE_TTL_SECONDS > 0 and parts:
                from .base import LLMResponse
                _cache_put(key, LLMResponse(
                    content="".join(parts),
                    model=self.model,
                    finish_reason="stop",
                ))

    def is_available(self) -> bool:
        """Check if DeepSeek API is available"""
        return self._available and bool(self.api_key)
