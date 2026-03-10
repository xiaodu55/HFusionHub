"""
Agent Core Module - ReAct Loop Implementation
"""

from .agent import Agent, AgentResponse
from .react import ReactAgent
from .workflow_runtime import SingleAgentWorkflow, get_agent_run_store
from .multi_agent_runtime import BoundedMultiAgentWorkflow
from .execution_context import AgentExecutionContext, ApprovalRequest
from .citation import normalize_source
from ..tools import ToolExecutionPolicy, create_v1_registry
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
    'AgentExecutionContext', 'ApprovalRequest', 'normalize_source',
    'ExpertRole', 'CollaborationTask', 'ExpertContribution',
    'CollaborationResult', 'ExpertAgent', 'CallableExpertAgent',
    'MultiAgentCoordinator',
]


def get_agent(
    knowledge_base_id: int = None,
    model: str = None,
    execution_context=None,  # AgentExecutionContext (optional)
    **kwargs
) -> Agent:
    """
    Get agent instance

    Args:
        knowledge_base_id: Knowledge base ID for RAG
        model: LLM model name
        execution_context: Agent V1 Step 3 — immutable context (user_id,
            permissions, mode, …) created by Java after authentication.
            Passed to the Tool Registry for permission enforcement.

    Returns:
        Agent instance
    """
    # Agent V1: create a ToolRegistry for KB-scoped agents.
    # The Registry is the SINGLE choke point for tool access — agents
    # MUST NOT bypass it.  Non-KB agents get no tools at all.
    #
    # Version gating:
    #   "1.0" — read-only KB tools (search, read_chunk, list_chunks)
    #   "1.1" — adds write_note (visible to see → approval_required gate)
    #
    # "1.1" is triggered by EITHER:
    #   - capability_profile="approval_write" (initial write-request, read_only
    #     mode — agent sees write_note → registry returns approval_required)
    #   - mode="read_write" (decide/resume after human approval)
    tool_registry = None
    if knowledge_base_id and knowledge_base_id > 0:
        _want_1_1 = False
        if execution_context is not None:
            if getattr(execution_context, 'mode', 'read_only') == 'read_write':
                _want_1_1 = True
            if getattr(execution_context, 'capability_profile', None) == 'approval_write':
                _want_1_1 = True
        registry_version = "1.1" if _want_1_1 else "1.0"
        tool_registry = create_v1_registry(knowledge_base_id, agent_version=registry_version)

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
        tool_registry=tool_registry,
        execution_context=execution_context,
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
