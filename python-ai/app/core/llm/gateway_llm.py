"""BaseLLM-compatible facade over the :class:`ModelGateway`.

The agent / ReAct code expects a concrete ``BaseLLM`` it can call ``chat`` /
``chat_stream`` on.  ``GatewayLLM`` presents exactly that interface while
routing through the gateway, so streaming and non-streaming agent calls get
rate limiting, circuit breaking, cost tracking and the exact-match response
cache — the governance the legacy ``get_llm()`` chain lacks.

When the gateway cannot route (disabled, no provider, unresolvable model) the
gateway itself degrades to the legacy ``get_llm()`` chain, so the facade never
turns a healthy request into an outage.
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator, List, Optional

from .base import BaseLLM, ChatMessage, LLMResponse
from .model_gateway import ModelGateway

logger = logging.getLogger(__name__)


class GatewayLLM(BaseLLM):
    """Adapter that delegates ``chat`` / ``chat_stream`` to a ModelGateway."""

    def __init__(self, gateway: ModelGateway, model: Optional[str] = None):
        self._gateway = gateway
        # An unpinned model resolves to the gateway's default provider model.
        self.model = model or gateway._default_model()

    async def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> LLMResponse:
        result = await self._gateway.chat(
            self.model,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        return LLMResponse(
            content=result.content,
            model=result.model,
            token_count=result.usage.total_tokens if result.usage else 0,
            finish_reason=result.finish_reason,
            tool_calls=result.tool_calls,
        )

    async def chat_stream(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        async for chunk in self._gateway.chat_stream(
            self.model,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        ):
            yield chunk

    def is_available(self) -> bool:
        """The facade is usable when the gateway can route."""
        return self._gateway._can_route()
