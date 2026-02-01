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
        # Get the last user message
        last_user_msg = ""
        for msg in reversed(messages):
            if msg.role == "user":
                last_user_msg = msg.content
                break

        # Generate mock response
        mock_response = f"""您好！我是AI助手。

您刚才说的是："{last_user_msg}"

这是一个模拟回复。要使用真实的AI模型，请确保：
1. DeepSeek API Key 已配置
2. 或者 Ollama 服务正在运行

当前处于降级模式，无法提供真实的AI对话能力。"""

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
