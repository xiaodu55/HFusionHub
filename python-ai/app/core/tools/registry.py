"""ToolRegistry — Agent V1 unified tool registry.

The Registry is the SINGLE source of truth for tool availability.
Agents MUST obtain tools through the Registry; they MUST NOT bypass it
by importing tool modules directly.

V1 rules:
  - Only ``search_knowledge_base``, ``read_chunk``, ``list_document_chunks``
  - All have ``risk_level=read_only`` and require ``knowledge_base:read``
  - ``knowledge_base_id`` is always required for execution
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Optional

from .base import BaseTool
from .spec import (
    ToolSpec,
    V1_SPECS,
    ErrorCode,
    RiskLevel,
    Permissions,
    SEARCH_KB_SPEC,
    READ_CHUNK_SPEC,
    LIST_DOC_CHUNKS_SPEC,
)
from .result import ToolResult
from .search_tool import SearchTool
from .read_chunk_tool import ReadChunkTool
from .list_document_chunks_tool import ListDocumentChunksTool
from .calculator_tool import CalculatorTool
from .time_tool import TimeTool
from .web_search_tool import WebSearchTool


class RegistryError(ValueError):
    """Raised when a tool is requested but not available in this registry."""


class ToolRegistry:
    """Central tool registry with version-based and permission-based filtering.

    Usage::

        registry = ToolRegistry(knowledge_base_id=1)
        tools = registry.get_tools()          # V1 tools only
        result = await registry.execute("search_knowledge_base", {"query": "..."})
    """

    def __init__(
        self,
        knowledge_base_id: Optional[int] = None,
        agent_version: str = "1.0",
    ):
        self._knowledge_base_id = knowledge_base_id
        self._agent_version = agent_version
        # spec name → (ToolSpec, BaseTool instance)
        self._specs: Dict[str, ToolSpec] = {}
        self._instances: Dict[str, BaseTool] = {}

        # Register all known tools.  The agent_version gate is applied in
        # get_tools(), so non-V1 tools exist internally but are never exposed
        # to V1 agents.
        self._register_all()

    # ── Registration ──────────────────────────────────────────────────

    def _register_all(self) -> None:
        """Register every tool known to the system."""
        kb = self._knowledge_base_id

        # V1 tools — always registered
        self._register(V1_SPECS[SEARCH_KB_SPEC.name], SearchTool(knowledge_base_id=kb))
        self._register(V1_SPECS[READ_CHUNK_SPEC.name], ReadChunkTool(knowledge_base_id=kb))
        self._register(V1_SPECS[LIST_DOC_CHUNKS_SPEC.name], ListDocumentChunksTool(knowledge_base_id=kb))

        # Non-V1 tools — registered but gated by agent_version
        # (These are owned by the registry so MCP can still access them
        #  via v1_only=False queries; V1 agents never see them.)
        from .spec import ToolSpec as TS
        calc_spec = TS(
            name="calculate",
            description="执行数学计算。",
            input_schema={
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
            output_schema={"type": "string"},
            risk_level=RiskLevel.READ_ONLY,
            timeout_seconds=5.0,
            required_permissions=[],
            agent_version="0.0",  # not available in any agent version
        )
        time_spec = TS(
            name="get_current_time",
            description="获取当前日期和时间。",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "string"},
            risk_level=RiskLevel.READ_ONLY,
            timeout_seconds=3.0,
            required_permissions=[Permissions.SYSTEM_TIME],
            agent_version="0.0",
        )
        web_spec = TS(
            name="web_search",
            description="搜索互联网获取最新信息。",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
            output_schema={"type": "array"},
            risk_level=RiskLevel.EXTERNAL,
            timeout_seconds=15.0,
            required_permissions=[Permissions.EXTERNAL_HTTP],
            agent_version="0.0",
        )
        self._register(calc_spec, CalculatorTool())
        self._register(time_spec, TimeTool())
        self._register(web_spec, WebSearchTool())

    def _register(self, spec: ToolSpec, instance: BaseTool) -> None:
        self._specs[spec.name] = spec
        self._instances[spec.name] = instance

    # ── Tool discovery ────────────────────────────────────────────────

    def get_spec(self, tool_name: str) -> Optional[ToolSpec]:
        """Return the ToolSpec for *any* registered tool (including non-V1)."""
        return self._specs.get(tool_name)

    def get_tools(
        self,
        agent_version: Optional[str] = None,
        v1_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """Return tool definitions visible to the given agent version.

        V1 agents (``agent_version="1.0"``) see only V1-whitelisted tools.
        Non-V1 callers (MCP server) pass ``v1_only=False`` to see all tools.
        """
        version = agent_version or self._agent_version
        tools: List[Dict[str, Any]] = []
        for name, spec in self._specs.items():
            if v1_only and spec.agent_version != "1.0":
                continue
            tools.append({
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.input_schema.get("properties", {}),
                "_spec": spec,
            })
        return tools

    # ── Execution ─────────────────────────────────────────────────────

    async def execute(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        timeout_seconds: Optional[float] = None,
    ) -> ToolResult:
        """Execute a tool through the registry.

        Validates:
          1. Tool is registered
          2. Tool is available for the current agent version
          3. Input matches the input_schema
          4. Knowledge base is set (for KB-scoped tools)
        """
        spec = self._specs.get(tool_name)
        if spec is None:
            return ToolResult.failure(
                tool_name=tool_name,
                error_code=ErrorCode.NOT_FOUND,
                message=f"工具 '{tool_name}' 未注册",
            )

        # Agent-version gate
        if spec.agent_version != self._agent_version:
            return ToolResult.failure(
                tool_name=tool_name,
                error_code=ErrorCode.SCOPE_DENIED,
                message=f"工具 '{tool_name}' 不在 Agent V{self._agent_version} 白名单中",
            )

        # KB-scope enforcement
        if Permissions.KB_READ in spec.required_permissions:
            if not self._knowledge_base_id or self._knowledge_base_id <= 0:
                return ToolResult.failure(
                    tool_name=tool_name,
                    error_code=ErrorCode.SCOPE_DENIED,
                    message="未指定知识库ID，无法执行知识库操作",
                )

        # Input validation against JSON Schema
        validation_error = self._validate_input(spec, tool_input)
        if validation_error:
            return ToolResult.failure(
                tool_name=tool_name,
                error_code=ErrorCode.INVALID_INPUT,
                message=validation_error,
            )

        # Inject knowledge_base_id for KB-scoped tools.
        # Always strip any user-supplied value first to prevent KB spoofing.
        safe_input = dict(tool_input)
        safe_input.pop("knowledge_base_id", None)
        if Permissions.KB_READ in spec.required_permissions:
            safe_input["knowledge_base_id"] = self._knowledge_base_id

        instance = self._instances.get(tool_name)
        if instance is None:
            return ToolResult.failure(
                tool_name=tool_name,
                error_code=ErrorCode.INTERNAL,
                message=f"工具 '{tool_name}' 实例未找到",
            )

        effective_timeout = timeout_seconds or spec.timeout_seconds
        started = time.monotonic()

        try:
            result_data = await asyncio.wait_for(
                instance.execute(**safe_input),
                timeout=max(0.1, effective_timeout),
            )
            elapsed = round((time.monotonic() - started) * 1000, 2)

            # Check for error dict returned by the tool itself (e.g. "error" key)
            if isinstance(result_data, dict) and "error" in result_data:
                return ToolResult.failure(
                    tool_name=tool_name,
                    error_code=ErrorCode.INTERNAL,
                    message=result_data["error"],
                    duration_ms=elapsed,
                )

            return ToolResult.success(
                tool_name=tool_name,
                data=result_data,
                duration_ms=elapsed,
            )

        except asyncio.TimeoutError:
            elapsed = round((time.monotonic() - started) * 1000, 2)
            return ToolResult.failure(
                tool_name=tool_name,
                error_code=ErrorCode.TIMEOUT,
                message=spec.error_codes.get(ErrorCode.TIMEOUT, "工具调用超时"),
                duration_ms=elapsed,
            )
        except Exception as e:
            elapsed = round((time.monotonic() - started) * 1000, 2)
            return ToolResult.failure(
                tool_name=tool_name,
                error_code=ErrorCode.INTERNAL,
                message=f"{spec.error_codes.get(ErrorCode.INTERNAL, '工具内部错误')}: {e}",
                duration_ms=elapsed,
            )

    # ── Input validation ──────────────────────────────────────────────

    @staticmethod
    def _validate_input(spec: ToolSpec, tool_input: Dict[str, Any]) -> Optional[str]:
        """Validate input against the tool's input_schema.  Returns None on success."""
        input_schema = spec.input_schema
        if not isinstance(tool_input, dict):
            return "输入必须是 JSON 对象"

        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])

        for field_name in required:
            if field_name not in tool_input or tool_input[field_name] is None:
                return f"缺少必填参数: {field_name}"

        for field_name, value in tool_input.items():
            prop = properties.get(field_name)
            if prop is None:
                continue  # allow extra fields (the tool ignores them)
            expected_type = prop.get("type", "string")

            if expected_type == "string":
                if not isinstance(value, str):
                    return f"参数 '{field_name}' 应为字符串"
                max_len = prop.get("maxLength")
                if max_len and len(value) > max_len:
                    return f"参数 '{field_name}' 超过最大长度 {max_len}"
            elif expected_type == "integer":
                if not isinstance(value, int) or isinstance(value, bool):
                    return f"参数 '{field_name}' 应为整数"
                minimum = prop.get("minimum")
                maximum = prop.get("maximum")
                if minimum is not None and value < minimum:
                    return f"参数 '{field_name}' 小于最小值 {minimum}"
                if maximum is not None and value > maximum:
                    return f"参数 '{field_name}' 超过最大值 {maximum}"

        return None  # valid


# ── Module-level convenience ──────────────────────────────────────────

# Singleton pattern — one registry per knowledge_base_id.
# The Agent creates a fresh registry for each conversation context.
def create_v1_registry(knowledge_base_id: int) -> ToolRegistry:
    """Create a ToolRegistry for Agent V1 with the given KB scope."""
    if not knowledge_base_id or knowledge_base_id <= 0:
        raise RegistryError("Agent V1 registry requires a non-null knowledge_base_id")
    return ToolRegistry(knowledge_base_id=knowledge_base_id, agent_version="1.0")


def create_full_registry(knowledge_base_id: Optional[int] = None) -> ToolRegistry:
    """Create a ToolRegistry with all tools (for MCP / non-agent use)."""
    return ToolRegistry(knowledge_base_id=knowledge_base_id, agent_version="1.0")
