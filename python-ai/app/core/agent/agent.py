"""
Agent Base Module - Abstract base class and data models
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, AsyncGenerator, Dict, Any


@dataclass
class AgentStep:
    """Single step in agent execution"""
    thought: str
    action: Optional[str] = None
    action_input: Optional[Dict[str, Any]] = None
    observation: Optional[str] = None


@dataclass
class AgentResponse:
    """Agent response data model"""
    content: str
    steps: List[AgentStep] = field(default_factory=list)
    model: str = ""
    token_count: int = 0
    finish_reason: str = "stop"
    sources: List[Dict[str, Any]] = field(default_factory=list)
    intent: Optional[Dict[str, Any]] = None  # 意图分类结果
    decomposition: Optional[Dict[str, Any]] = None  # 问题分解结果
    auto_detected_kb_id: Optional[int] = None  # 自动检测的知识库 ID
    agent_run_id: Optional[str] = None  # P9 workflow run ID (no prompt content)
    agent_status: Optional[str] = None  # completed / insufficient_evidence / failed


class Agent(ABC):
    """Abstract base class for Agent implementations"""

    @abstractmethod
    async def run(
        self,
        query: str,
        history: List[Dict[str, str]] = None,
        **kwargs
    ) -> AgentResponse:
        """
        Run agent with query

        Args:
            query: User query
            history: Chat history [{"role": "user", "content": "..."}, ...]

        Returns:
            AgentResponse with generated content and steps
        """
        pass

    @abstractmethod
    async def run_stream(
        self,
        query: str,
        history: List[Dict[str, str]] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        Run agent with streaming

        Args:
            query: User query
            history: Chat history

        Yields:
            Chunks of generated content
        """
        pass

    @abstractmethod
    def get_tools(self) -> List[Dict[str, Any]]:
        """Get list of available tools"""
        pass
