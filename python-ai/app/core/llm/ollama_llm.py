"""
Ollama LLM Implementation
Uses local Ollama API for chat completion
"""

import json
from typing import List, AsyncGenerator, Optional

from .base import BaseLLM, ChatMessage, LLMResponse
from .http_client import get_shared_client, post_with_retry


class OllamaLLM(BaseLLM):
    """Ollama LLM implementation for local models"""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:latest",
        *,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        retry_backoff: Optional[float] = None,
    ):
        from app.utils.config import config

        self.base_url = base_url
        self.model = model
        # Connection/timeout/retry knobs default to the environment-config
        # values; per-instance overrides let request-scoped providers tune.
        self.timeout = timeout if timeout is not None else config.LLM_HTTP_TIMEOUT_SECONDS
        self.max_retries = max_retries if max_retries is not None else config.LLM_MAX_RETRIES
        self.retry_backoff = retry_backoff if retry_backoff is not None else config.LLM_RETRY_BACKOFF_SECONDS
        self._available = False

    async def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> LLMResponse:
        """Chat completion via Ollama API"""
        # Convert ChatMessage to Ollama format
        api_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

        payload = {
            "model": self.model,
            "messages": api_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }

        client = get_shared_client(owner="ollama", timeout=self.timeout)
        response = await post_with_retry(
            client,
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=self.timeout,
            max_retries=self.max_retries,
            backoff=self.retry_backoff,
        )
        response.raise_for_status()
        data = response.json()

        # Extract response
        content = data.get("message", {}).get("content", "")
        total_tokens = data.get("eval_count", 0) + data.get("prompt_eval_count", 0)

        return LLMResponse(
            content=content,
            model=self.model,
            token_count=total_tokens,
            finish_reason="stop"
        )

    async def chat_stream(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Chat completion with streaming via Ollama API"""
        # Convert ChatMessage to Ollama format
        api_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

        payload = {
            "model": self.model,
            "messages": api_messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }

        # Streaming deliberately does not retry (see deepseek_llm.chat_stream);
        # the shared client still gives connection reuse on the stream path.
        client = get_shared_client(owner="ollama", timeout=self.timeout)
        async with client.stream(
            "POST",
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=self.timeout,
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if line.strip():
                    try:
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

    def is_available(self) -> bool:
        """Check if Ollama is available.

        Delegates to the package-level thread-pooled, TTL-cached probe
        (the gateway availability state) so a probe never blocks the
        event loop with a synchronous HTTP call. The late import avoids a
        circular import between this module and the package ``__init__``.
        """
        from app.core.llm import _is_ollama_available

        self._available = _is_ollama_available(self.base_url)
        return self._available
