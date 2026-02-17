"""
Agent Core Module - ReAct Loop Implementation
"""

from .agent import Agent, AgentResponse
from .react import ReactAgent
from .workflow_runtime import SingleAgentWorkflow, get_agent_run_store
from .multi_agent_runtime import BoundedMultiAgentWorkflow
from ..tools import ToolExecutionPolicy
from app.utils.config import config
from .collaboration import (
    ExpertRole,
    CollaborationTask,
    ExpertContribution,
    CollaborationResult,
    ExpertAgent,
    CallableExpertAgent,
    MultiAgentCoordinator,
)

__all__ = [
    'Agent', 'AgentResponse', 'ReactAgent', 'SingleAgentWorkflow', 'BoundedMultiAgentWorkflow', 'get_agent', 'get_agent_run_store',
    'ExpertRole', 'CollaborationTask', 'ExpertContribution',
    'CollaborationResult', 'ExpertAgent', 'CallableExpertAgent',
    'MultiAgentCoordinator',
]


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
    tool_policy = None
    if config.RAG_AGENT_WORKFLOW_ENABLED:
        tool_policy = ToolExecutionPolicy(
            allowed_names=set(config.RAG_AGENT_ALLOWED_TOOLS),
            knowledge_base_id=knowledge_base_id,
            timeout_seconds=config.RAG_AGENT_TOOL_TIMEOUT_SECONDS,
            max_search_results=config.RAG_AGENT_MAX_SEARCH_RESULTS,
        )
    agent = ReactAgent(
        knowledge_base_id=knowledge_base_id,
        model=model,
        max_steps=config.RAG_AGENT_MAX_STEPS if config.RAG_AGENT_WORKFLOW_ENABLED else 5,
        tool_policy=tool_policy,
        **kwargs
    )
    if not config.RAG_AGENT_WORKFLOW_ENABLED:
        return agent
    bounded_agent = SingleAgentWorkflow(
        delegate=agent,
        knowledge_base_id=knowledge_base_id,
        timeout_seconds=config.RAG_AGENT_TIMEOUT_SECONDS,
        max_retries=config.RAG_AGENT_MAX_RETRIES,
        retry_delay_seconds=config.RAG_AGENT_RETRY_DELAY_SECONDS,
    )
    if not (config.RAG_MULTI_AGENT_ENABLED and knowledge_base_id and knowledge_base_id > 0):
        return bounded_agent
    return BoundedMultiAgentWorkflow(
        delegate=bounded_agent,
        knowledge_base_id=knowledge_base_id,
        timeout_seconds=config.RAG_MULTI_AGENT_TIMEOUT_SECONDS,
    )
