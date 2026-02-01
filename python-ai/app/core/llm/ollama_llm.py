"""
Ollama LLM Implementation
Uses local Ollama API for chat completion
"""

import httpx
from typing import List, AsyncGenerator

from .base import BaseLLM, ChatMessage, LLMResponse


class OllamaLLM(BaseLLM):
    """Ollama LLM implementation for local models"""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:latest"
    ):
        self.base_url = base_url
        self.model = model
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

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json=payload
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

        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json=payload
            ) as response:
                response.raise_for_status()

                import json
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
        """Check if Ollama is available"""
        try:
            import httpx
            response = httpx.get(f"{self.base_url}/api/tags", timeout=5)
            self._available = response.status_code == 200
        except Exception:
            self._available = False
        return self._available
