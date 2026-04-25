"""
DeepSeek LLM Implementation
Uses DeepSeek API for chat completion
"""

import httpx
import json
from typing import List, AsyncGenerator, NoReturn

from .base import BaseLLM, ChatMessage, LLMResponse


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
        model: str = "deepseek-v4-flash"
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
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
        """Chat completion via DeepSeek API"""
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

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                self._chat_completions_url(),
                headers=headers,
                json=payload
            )
            self._ensure_success(response)
            data = response.json()

        # Extract response
        choice = data["choices"][0]
        content = choice["message"]["content"]
        usage = data.get("usage", {})

        return LLMResponse(
            content=content,
            model=self.model,
            token_count=usage.get("total_tokens", 0),
            finish_reason=choice.get("finish_reason", "stop")
        )

    async def chat_stream(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Chat completion with streaming via DeepSeek API"""
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

        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                self._chat_completions_url(),
                headers=headers,
                json=payload
            ) as response:
                self._ensure_success(response)

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break

                        try:
                            data = json.loads(data_str)
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue

    def is_available(self) -> bool:
        """Check if DeepSeek API is available"""
        return self._available and bool(self.api_key)
