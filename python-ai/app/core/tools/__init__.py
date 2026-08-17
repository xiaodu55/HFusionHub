"""
Tools Module — Tool definitions, execution, and registry.

Agent V1: all tool access goes through the ToolRegistry.  Agents MUST NOT
import tool modules directly.  The Registry enforces the V1 whitelist,
input validation, KB scope, and timeout at a single choke point.

Legacy ``get_tools()`` / ``execute_tool()`` are kept for backward compat
with MCP and non-agent callers but delegate to the Registry internally.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from .base import BaseTool
from .calculator_tool import CalculatorTool
from .list_document_chunks_tool import ListDocumentChunksTool
from .read_chunk_tool import ReadChunkTool
from .registry import (
    RegistryError,
    ToolRegistry,
    clear_expired_grants,
    consume_scoped_grant,
    create_full_registry,
    create_v1_registry,
    register_scoped_grant,
)
from .result import ToolResult
from .search_tool import SearchTool
from .spec import ErrorCode, Permissions, RiskLevel, ToolSpec
from .time_tool import TimeTool
from .web_search_tool import WebSearchTool

logger = logging.getLogger(__name__)

__all__ = [
    # Models
    'ToolSpec', 'ToolResult', 'ToolExecutionPolicy',
    'ErrorCode', 'RiskLevel', 'Permissions',
    # Registry
    'ToolRegistry', 'RegistryError',
    'create_v1_registry', 'create_full_registry',
    # Scoped grants (Agent V1 Step 5)
    'register_scoped_grant', 'consume_scoped_grant', 'clear_expired_grants',
    # Tools
    'BaseTool', 'SearchTool', 'TimeTool', 'CalculatorTool',
    'WebSearchTool', 'ReadChunkTool', 'ListDocumentChunksTool',
    # Legacy compat
    'get_tools', 'execute_tool',
    # Constants
    'AGENT_V1_TOOL_NAMES',
]


# Agent V1 whitelist（B3 扩展：+20 沙箱业务工具，与评测 tool 用例一一对应）
AGENT_V1_TOOL_NAMES: set[str] = {
    "search_knowledge_base",
    "read_chunk",
    "list_document_chunks",
    # 演示业务工具（沙箱语义，read_only；生产可替换为真实业务系统调用）
    "add_device", "apply_annual_leave", "apply_sick_leave", "cancel_auto_renew",
    "create_incident", "export_finance_report", "get_cloud_footage",
    "query_credits", "query_order_logistics", "redeem_gift_card",
    "request_access", "run_database_backup", "schedule_service", "send_coupon",
    "submit_expense", "submit_refund", "submit_warranty_claim", "subscribe_plan",
    "switch_backup_link", "upgrade_firmware",
}

# legacy 入口的「每进程一次」告警标记：execute_tool 是 ReAct Agent 的活跃热路径，
# 逐次告警会淹没日志，仅在首次调用时记录用于退役流量评估
_LEGACY_WARNED: set[str] = set()


def _warn_legacy_once(entry: str) -> None:
    if entry not in _LEGACY_WARNED:
        _LEGACY_WARNED.add(entry)
        logger.warning(
            "Legacy tools entry point %s() used — prefer ToolRegistry (deprecation candidate, "
            "see OPTIMIZATION_PLAN R15; logged once per process)",
            entry,
        )


class ToolPolicyError(ValueError):
    """A tool call did not satisfy the safety policy."""


@dataclass(frozen=True)
class ToolExecutionPolicy:
    """Legacy policy — still used for non-Registry paths (MCP)."""

    allowed_names: set[str]
    knowledge_base_id: int | None = None
    timeout_seconds: float = 10.0
    max_search_results: int = 5
    max_input_characters: int = 512

    def normalize(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        if tool_name not in self.allowed_names:
            raise ToolPolicyError(f"tool_not_allowed:{tool_name}")
        if not isinstance(tool_input, dict):
            raise ToolPolicyError("invalid_tool_input")
        normalized = dict(tool_input)

        if tool_name == "search_knowledge_base":
            if not self.knowledge_base_id:
                raise ToolPolicyError("knowledge_base_required")
            normalized.pop("knowledge_base_id", None)
            query = str(normalized.get("query", "")).strip()
            if not query or len(query) > self.max_input_characters:
                raise ToolPolicyError("invalid_search_query")
            try:
                rtk = int(normalized.get("top_k", self.max_search_results))
            except (TypeError, ValueError) as error:
                raise ToolPolicyError("invalid_top_k") from error
            normalized["query"] = query
            normalized["top_k"] = max(1, min(rtk, self.max_search_results))

        elif tool_name == "read_chunk":
            if not self.knowledge_base_id:
                raise ToolPolicyError("knowledge_base_required")
            chunk_id = str(normalized.get("chunk_id", "")).strip()
            if not chunk_id or len(chunk_id) > 128:
                raise ToolPolicyError("invalid_chunk_id")
            normalized["chunk_id"] = chunk_id

        elif tool_name == "list_document_chunks":
            if not self.knowledge_base_id:
                raise ToolPolicyError("knowledge_base_required")
            try:
                doc_id = int(normalized.get("document_id", 0))
            except (TypeError, ValueError) as error:
                raise ToolPolicyError("invalid_document_id") from error
            if doc_id <= 0:
                raise ToolPolicyError("invalid_document_id")
            normalized["document_id"] = doc_id

        elif tool_name == "calculate":
            expression = str(normalized.get("expression", ""))
            if not expression or len(expression) > self.max_input_characters:
                raise ToolPolicyError("invalid_expression")
            normalized["expression"] = expression

        elif tool_name == "get_current_time":
            pass

        elif tool_name == "web_search":
            query = str(normalized.get("query", "")).strip()
            if not query or len(query) > self.max_input_characters:
                raise ToolPolicyError("invalid_search_query")
            try:
                mr = int(normalized.get("max_results", 5))
            except (TypeError, ValueError):
                mr = 5
            normalized["query"] = query
            normalized["max_results"] = max(1, min(mr, 10))

        elif normalized:
            raise ToolPolicyError("unexpected_tool_arguments")
        return normalized


# ── Legacy compat — delegates to Registry internally ──────────────────

def get_tools(
    knowledge_base_id: int = None,
    v1_only: bool = True,
    **kwargs
) -> list[dict[str, Any]]:
    """Get tool definitions with instance references.

    Returns tools from the Registry, each carrying an ``_registry``
    back-reference so ``execute_tool`` routes through the Registry.
    For backward compat, also attaches the ``instance`` key used by MCP.
    """
    _warn_legacy_once("get_tools")

    if v1_only and knowledge_base_id:
        registry = create_v1_registry(knowledge_base_id)
    else:
        registry = create_full_registry(knowledge_base_id)

    specs = registry.get_tools(v1_only=v1_only)

    # Attach tool instances for legacy MCP execute_tool path
    for spec_dict in specs:
        tool_name = spec_dict["name"]
        inst = registry._instances.get(tool_name)
        if inst is not None:
            spec_dict["instance"] = inst

    return specs


async def execute_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    tools: list[dict[str, Any]],
    policy: ToolExecutionPolicy | None = None,
    context: Any | None = None,  # AgentExecutionContext (lazy import)
) -> str:
    """Execute a tool through the Registry, returning a JSON string.

    Prefer ``ToolRegistry.execute()`` for new code — it returns a
    ``ToolResult`` object with structured success/error fields.
    This function exists for backward compat with the ReAct agent's
    text-based observation loop.

    When *context* is provided, the Registry enforces mode gates,
    permission checks, and KB-scope isolation before execution.
    """
    _warn_legacy_once("execute_tool")

    # Registry-attached 形式（审批流等场景在 tool dict 携带 _registry）走
    # Registry 执行（模式门/权限/KB 隔离生效）；否则回退 policy-based 执行。
    registry: ToolRegistry | None = None
    for tool in tools:
        reg = tool.get("_registry")
        if reg is not None:
            registry = reg
            break

    if registry is not None:
        result = await registry.execute(tool_name, tool_input, context=context)
        return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)

    # Policy-based execution (MCP path)
    try:
        safe_input = policy.normalize(tool_name, tool_input) if policy else tool_input
    except ToolPolicyError as error:
        return json.dumps(
            ToolResult.failure(tool_name, ErrorCode.INVALID_INPUT, str(error)).to_dict(),
            ensure_ascii=False,
        )

    tool_instance = None
    for tool in tools:
        if tool["name"] == tool_name:
            tool_instance = tool["instance"]
            break

    if tool_instance is None:
        return json.dumps(
            ToolResult.failure(tool_name, ErrorCode.NOT_FOUND, f"工具 '{tool_name}' 不存在").to_dict(),
            ensure_ascii=False,
        )

    try:
        if policy:
            result = await asyncio.wait_for(
                tool_instance.execute(**safe_input),
                timeout=max(0.1, policy.timeout_seconds),
            )
        else:
            result = await tool_instance.execute(**safe_input)

        if isinstance(result, dict) and "error" in result:
            return json.dumps(
                ToolResult.failure(tool_name, ErrorCode.INTERNAL, result["error"]).to_dict(),
                ensure_ascii=False,
            )

        return json.dumps(
            ToolResult.success(tool_name, result).to_dict(),
            ensure_ascii=False, indent=2,
        )

    except TimeoutError:
        return json.dumps(
            ToolResult.failure(tool_name, ErrorCode.TIMEOUT, "工具调用超时").to_dict(),
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps(
            ToolResult.failure(tool_name, ErrorCode.INTERNAL, f"工具执行错误：{e}").to_dict(),
            ensure_ascii=False,
        )
