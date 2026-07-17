"""
Base Tool - Abstract base class for tools
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """Abstract base class for all tools"""

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """
        Execute the tool

        Args:
            **kwargs: Tool-specific parameters

        Returns:
            Tool execution result
        """
        pass

    def to_dict(self) -> dict[str, Any]:
        """Convert tool to dictionary representation"""
        return {
            "name": self.__class__.__name__,
            "description": self.__doc__ or "",
        }
