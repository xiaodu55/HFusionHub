"""
LLM Base Module - Abstract base class and data models
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, AsyncGenerator


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


class BaseLLM(ABC):
    """Abstract base class for LLM implementations"""

    @abstractmethod
    async def chat(
        self,
        messages: List[ChatMessage],
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
        messages: List[ChatMessage],
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
