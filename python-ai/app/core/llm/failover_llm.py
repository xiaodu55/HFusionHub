"""Runtime failover wrapper for independently configured LLM providers."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import AsyncGenerator, List

from .base import BaseLLM, ChatMessage, LLMResponse

logger = logging.getLogger(__name__)


@dataclass
class _ProviderState:
    provider: BaseLLM
    failures: int = 0
    open_until: float = 0.0


class FailoverLLM(BaseLLM):
    """Fail over before a response starts and open a small circuit on repeats."""

    def __init__(self, providers: List[BaseLLM], failure_threshold: int = 3, cooldown_seconds: float = 30.0):
        if not providers:
            raise ValueError("FailoverLLM requires at least one provider")
        self._providers = [_ProviderState(provider) for provider in providers]
        self._failure_threshold = max(1, failure_threshold)
        self._cooldown_seconds = max(0.0, cooldown_seconds)

    async def chat(self, messages: List[ChatMessage], temperature: float = 0.7,
                   max_tokens: int = 2048, **kwargs) -> LLMResponse:
        last_error = None
        for state in self._eligible_providers():
            try:
                response = await state.provider.chat(messages, temperature=temperature, max_tokens=max_tokens, **kwargs)
                state.failures = 0
                state.open_until = 0.0
                return response
            except Exception as exc:
                last_error = exc
                self._record_failure(state, exc)
        raise RuntimeError("All configured LLM providers failed") from last_error

    async def chat_stream(self, messages: List[ChatMessage], temperature: float = 0.7,
                          max_tokens: int = 2048, **kwargs) -> AsyncGenerator[str, None]:
        last_error = None
        for state in self._eligible_providers():
            yielded = False
            try:
                async for chunk in state.provider.chat_stream(messages, temperature=temperature, max_tokens=max_tokens, **kwargs):
                    yielded = True
                    yield chunk
                state.failures = 0
                state.open_until = 0.0
                return
            except Exception as exc:
                if yielded:
                    raise RuntimeError("LLM stream failed after response content was emitted") from exc
                last_error = exc
                self._record_failure(state, exc)
        raise RuntimeError("All configured LLM providers failed before streaming began") from last_error

    def is_available(self) -> bool:
        return any(state.provider.is_available() for state in self._providers)

    def _eligible_providers(self) -> List[_ProviderState]:
        now = time.monotonic()
        eligible = [state for state in self._providers if state.open_until <= now]
        return eligible or self._providers[-1:]

    def _record_failure(self, state: _ProviderState, error: Exception) -> None:
        state.failures += 1
        if state.failures >= self._failure_threshold:
            state.open_until = time.monotonic() + self._cooldown_seconds
        logger.warning("LLM provider %s failed (%d/%d): %s", type(state.provider).__name__,
                       state.failures, self._failure_threshold, error)
