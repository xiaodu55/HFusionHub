"""
DeepSeek LLM Implementation
Uses DeepSeek API for chat completion
"""

import httpx
import json
from typing import List, AsyncGenerator

from .base import BaseLLM, ChatMessage, LLMResponse


class DeepSeekLLM(BaseLLM):
    """DeepSeek LLM implementation"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat"
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self._available = True

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
                f"{self.base_url}/v1/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
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
                f"{self.base_url}/v1/chat/completions",
                headers=headers,
                json=payload
            ) as response:
                response.raise_for_status()

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
