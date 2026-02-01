"""
Agent Core Module - ReAct Loop Implementation
"""

from .agent import Agent, AgentResponse
from .react import ReactAgent

__all__ = ['Agent', 'AgentResponse', 'ReactAgent', 'get_agent']


def get_agent(
    knowledge_base_id: int = None,
    model: str = None,
    **kwargs
) -> Agent:
    """
    Get agent instance

    Args:
        knowledge_base_id: Knowledge base ID for RAG
        model: LLM model name

    Returns:
        Agent instance
    """
    return ReactAgent(
        knowledge_base_id=knowledge_base_id,
        model=model,
        **kwargs
    )
