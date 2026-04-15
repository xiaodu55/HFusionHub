"""
Mock LLM Implementation
Fallback LLM for testing when no real LLM is available
"""

import asyncio
from typing import List, AsyncGenerator

from .base import BaseLLM, ChatMessage, LLMResponse


class MockLLM(BaseLLM):
    """Mock LLM for testing and fallback"""

    def __init__(self):
        self.model = "mock-model"

    async def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> LLMResponse:
        """Return a mock response"""
        # Mock mode must never echo the assembled user prompt. In RAG flows it
        # can contain retrieved text and system instructions rather than a
        # user-facing answer.
        mock_response = (
            "AI 对话服务当前处于开发测试模式，不能生成真实回答。"
            "请配置 DeepSeek API Key，或启动并配置 Ollama 后重试。"
        )

        await asyncio.sleep(0.1)  # Simulate processing time

        return LLMResponse(
            content=mock_response,
            model=self.model,
            token_count=0,
            finish_reason="stop"
        )

    async def chat_stream(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Return a mock streaming response"""
        response = await self.chat(messages, temperature, max_tokens, **kwargs)

        # Simulate streaming by yielding chunks
        chunk_size = 10
        for i in range(0, len(response.content), chunk_size):
            yield response.content[i:i + chunk_size]
            await asyncio.sleep(0.05)

    def is_available(self) -> bool:
        """Mock LLM is always available"""
        return True
