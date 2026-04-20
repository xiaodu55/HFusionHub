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
from app.utils.feature_flag import feature_flags
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
        # Runtime feature flag: agent.write_tools.enabled must be ON for V1.1
        _ff_write = feature_flags.is_enabled(
            "agent.write_tools.enabled",
            user_id=getattr(execution_context, 'user_id', None) if execution_context else None,
            knowledge_base_id=knowledge_base_id,
        )
        registry_version = "1.1" if (_want_1_1 and _ff_write) else "1.0"
        # B4: expose web_search to the agent only when the feature flag is on.
        _ff_web_search = feature_flags.is_enabled(
            "agent.web_search.enabled",
            user_id=getattr(execution_context, 'user_id', None) if execution_context else None,
            knowledge_base_id=knowledge_base_id,
        )
        tool_registry = create_v1_registry(
            knowledge_base_id,
            agent_version=registry_version,
            tenant_id=getattr(execution_context, 'tenant_id', None) if execution_context else None,
            enable_web_search=_ff_web_search,
        )

    # Runtime feature flag override: if agent.enabled is OFF via Java feature
    # flag, force agent workflow and multi-agent off regardless of env config.
    _ff_agent_enabled = feature_flags.is_enabled(
        "agent.enabled",
        user_id=getattr(execution_context, 'user_id', None) if execution_context else None,
        knowledge_base_id=knowledge_base_id,
    )
    _ff_workflow = _ff_agent_enabled
    _ff_multi = _ff_agent_enabled and feature_flags.is_enabled(
        "agent.multi_agent.enabled",
        user_id=getattr(execution_context, 'user_id', None) if execution_context else None,
        knowledge_base_id=knowledge_base_id,
    )

    tool_policy = None
    if _ff_workflow:
        tool_policy = ToolExecutionPolicy(
            allowed_names=set(config.RAG_AGENT_ALLOWED_TOOLS),
            knowledge_base_id=knowledge_base_id,
            timeout_seconds=config.RAG_AGENT_TOOL_TIMEOUT_SECONDS,
            max_search_results=config.RAG_AGENT_MAX_SEARCH_RESULTS,
        )
    agent = ReactAgent(
        knowledge_base_id=knowledge_base_id,
        model=model,
        max_steps=config.RAG_AGENT_MAX_STEPS if _ff_workflow else 5,
        tool_policy=tool_policy,
        tool_registry=tool_registry,
        execution_context=execution_context,
        retrieval_top_k=kwargs.pop("retrieval_top_k", None),
        **kwargs
    )
    if not _ff_workflow:
        return agent
    bounded_agent = SingleAgentWorkflow(
        delegate=agent,
        knowledge_base_id=knowledge_base_id,
        timeout_seconds=config.RAG_AGENT_TIMEOUT_SECONDS,
        max_retries=config.RAG_AGENT_MAX_RETRIES,
        retry_delay_seconds=config.RAG_AGENT_RETRY_DELAY_SECONDS,
    )
    if not (_ff_multi and knowledge_base_id and knowledge_base_id > 0):
        return bounded_agent
    return BoundedMultiAgentWorkflow(
        delegate=bounded_agent,
        knowledge_base_id=knowledge_base_id,
        timeout_seconds=config.RAG_MULTI_AGENT_TIMEOUT_SECONDS,
    )
