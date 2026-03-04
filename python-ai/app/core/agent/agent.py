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
    """Agent V1 response data model — canonical fields for Java ↔ Python ↔ Frontend."""

    # ── Core answer ──
    content: str = ""  # Final answer text (Markdown).
    answer: str = ""  # Alias for content; set by the agent before returning.

    # ── Status (Agent V1 enum) ──
    # completed | insufficient_evidence | tool_error | timeout
    status: str = "completed"
    finish_reason: str = "stop"

    # ── Sources ──
    sources: List[Dict[str, Any]] = field(default_factory=list)

    # ── Execution metadata ──
    steps: List[AgentStep] = field(default_factory=list)
    model: str = ""
    token_count: int = 0
    token_usage: Optional[Dict[str, int]] = None  # {prompt_tokens, completion_tokens, total_tokens}
    tool_calls_count: int = 0
    style_used: str = "detailed"  # concise | detailed | report
    max_tool_steps: int = 5

    # ── Agent identity ──
    agent_run_id: Optional[str] = None  # P9 workflow run ID (no prompt content)
    agent_status: Optional[str] = None  # deprecated — prefer `status`

    # ── Error detail (only populated on tool_error / timeout) ──
    error_detail: Optional[str] = None
    failed_tool: Optional[str] = None

    # ── Intent / decomposition (diagnostic) ──
    intent: Optional[Dict[str, Any]] = None  # 意图分类结果
    decomposition: Optional[Dict[str, Any]] = None  # 问题分解结果
    auto_detected_kb_id: Optional[int] = None  # 自动检测的知识库 ID

    def __post_init__(self):
        """Ensure content and answer stay in sync."""
        if self.answer and not self.content:
            self.content = self.answer
        elif self.content and not self.answer:
            self.answer = self.content

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to the Agent V1 JSON contract."""
        return {
            "answer": self.answer or self.content,
            "sources": self.sources,
            "status": self.status,
            "agent_run_id": self.agent_run_id,
            "token_usage": self.token_usage or {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": self.token_count,
            },
            "tool_calls_count": self.tool_calls_count,
            "style_used": self.style_used,
            "max_tool_steps": self.max_tool_steps,
            "error_detail": self.error_detail,
            "failed_tool": self.failed_tool,
            "model": self.model,
            "finish_reason": self.finish_reason,
        }


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
