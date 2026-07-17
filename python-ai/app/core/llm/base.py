"""
LLM Base Module - Abstract base class and data models
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncGenerator


@dataclass
class ChatMessage:
    """Chat message data model"""
    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class LLMResponse:
    """LLM response data model"""
    content: str
    model: str
    token_count: int = 0
    finish_reason: str = "stop"
    # 原生 function calling：provider 返回的 tool_calls（OpenAI 形态
    # [{"id","type","function":{"name","arguments"}}]；arguments 为 JSON 字符串
    # 或 dict——Ollama 原生返回 dict，消费方需同时兼容）。文本 ReAct 降级时为 None。
    tool_calls: list[dict[str, Any]] | None = None


class BaseLLM(ABC):
    """Abstract base class for LLM implementations"""

    async def ainvoke(self, prompt: str, **kwargs) -> LLMResponse:
        """
        Invoke LLM with a prompt (LangChain compatibility)

        Args:
            prompt: The prompt to send to the LLM
            **kwargs: Additional parameters

        Returns:
            LLMResponse with generated content
        """
        messages = [ChatMessage(role="user", content=prompt)]
        return await self.chat(messages=messages, **kwargs)

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> LLMResponse:
        """
        Chat completion

        Args:
            messages: List of chat messages
            temperature: Temperature for sampling
            max_tokens: Maximum tokens to generate

        Returns:
            LLMResponse with generated content
        """
        pass

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        Chat completion with streaming

        Args:
            messages: List of chat messages
            temperature: Temperature for sampling
            max_tokens: Maximum tokens to generate

        Yields:
            Chunks of generated content
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if LLM is available"""
        pass
