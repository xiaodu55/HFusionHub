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
import hashlib
import json
import logging
import time
import threading
from typing import Any, Dict, List, Optional
from uuid import uuid4

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

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Scoped Grant Registry — Agent V1 Step 5
# ═══════════════════════════════════════════════════════════════════════════
#
# When a human approves a high-risk tool call, Java updates MySQL then calls
# Python's /api/agent/v1/chat/decide endpoint.  That endpoint registers a
# *scoped grant* here — a one-time, single-tool, single-parameter permission
# bypass — then re-runs the agent.  The ToolRegistry consumes the grant when
# the matching tool is called, and only then.
#
# Security properties:
#   1. One grant = one execution (consumed immediately on first match).
#   2. Input hash must match (prevents parameter tampering).
#   3. Grant expires after 60 s (prevents stale-grant replay).
#   4. Grant is in-process only; Python restart clears all grants.
#      The authoritative approval record lives in MySQL agent_approval.

_scoped_grants: Dict[str, Dict[str, Any]] = {}
_scoped_grants_lock = threading.Lock()
_SCOPED_GRANT_TTL_SECONDS = 60


def register_scoped_grant(
    tool_name: str,
    tool_input: Dict[str, Any],
    user_id: int,
    knowledge_base_id: int,
) -> str:
    """Register a one-time permission bypass for *tool_name* + *tool_input*.

    Returns a grant token (UUID) that the caller can use to track the grant.
    The grant is automatically consumed by the first matching ``execute()``
    call and expires after ``_SCOPED_GRANT_TTL_SECONDS``.
    """
    token = str(uuid4())
    input_canonical = json.dumps(tool_input, sort_keys=True, ensure_ascii=False)
    input_hash = hashlib.sha256(input_canonical.encode("utf-8")).hexdigest()

    with _scoped_grants_lock:
        _scoped_grants[token] = {
            "tool_name": tool_name,
            "input_hash": input_hash,
            "user_id": user_id,
            "knowledge_base_id": knowledge_base_id,
            "created_at": time.monotonic(),
        }
    logger.info(
        "Scoped grant registered: token=%s tool=%s hash=%s...",
        token[:8], tool_name, input_hash[:16],
    )
    return token


def consume_scoped_grant(
    tool_name: str,
    tool_input: Dict[str, Any],
    user_id: int,
    knowledge_base_id: int,
) -> bool:
    """Check for a matching scoped grant.  Consumes and returns True on match.

    Called by ``ToolRegistry.execute()`` before the mode/permission gates.
    Thread-safe: only one caller can consume a given grant.

    **Security (Agent V1 Step 5):** validates ALL of the following before consuming:
      1. ``tool_name`` — exact match
      2. ``input_hash`` — SHA-256 of canonical JSON (prevents parameter tampering)
      3. ``user_id`` — must match the grant's registered user (prevents cross-user replay)
      4. ``knowledge_base_id`` — must match the grant's registered KB (prevents cross-KB write)
    """
    input_canonical = json.dumps(tool_input, sort_keys=True, ensure_ascii=False)
    input_hash = hashlib.sha256(input_canonical.encode("utf-8")).hexdigest()
    now = time.monotonic()

    with _scoped_grants_lock:
        # Clean expired grants first
        expired = [
            t for t, g in _scoped_grants.items()
            if now - g["created_at"] > _SCOPED_GRANT_TTL_SECONDS
        ]
        for t in expired:
            del _scoped_grants[t]

        # Find matching grant — MUST match ALL four dimensions.
        for token, grant in list(_scoped_grants.items()):
            if grant["tool_name"] != tool_name:
                continue
            if grant["input_hash"] != input_hash:
                logger.warning(
                    "Scoped grant hash mismatch: token=%s tool=%s "
                    "expected_hash=%s... actual_hash=%s...",
                    token[:8], tool_name,
                    grant["input_hash"][:16], input_hash[:16],
                )
                continue
            if grant["user_id"] != user_id:
                logger.warning(
                    "Scoped grant user_id mismatch: token=%s tool=%s "
                    "grant_user=%d actual_user=%d",
                    token[:8], tool_name,
                    grant["user_id"], user_id,
                )
                continue
            if grant["knowledge_base_id"] != knowledge_base_id:
                logger.warning(
                    "Scoped grant knowledge_base_id mismatch: token=%s tool=%s "
                    "grant_kb=%d actual_kb=%d",
                    token[:8], tool_name,
                    grant["knowledge_base_id"], knowledge_base_id,
                )
                continue

            # All four dimensions match → consume the grant.
            del _scoped_grants[token]
            logger.info(
                "Scoped grant consumed: token=%s tool=%s user=%d kb=%d",
                token[:8], tool_name, user_id, knowledge_base_id,
            )
            return True

    return False


def clear_expired_grants() -> int:
    """Remove all expired scoped grants.  Returns count removed."""
    now = time.monotonic()
    with _scoped_grants_lock:
        expired = [
            t for t, g in _scoped_grants.items()
            if now - g["created_at"] > _SCOPED_GRANT_TTL_SECONDS
        ]
        for t in expired:
            del _scoped_grants[t]
    if expired:
        logger.info("Cleared %d expired scoped grants", len(expired))
    return len(expired)


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
        # Policy engine instance (swappable in tests).
        from app.core.policy.engine import PolicyEngine
        self._policy_engine = PolicyEngine()

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

        # Agent V1 Step 5: write_note (high-risk, requires approval)
        # Gated behind agent_version="1.1" — NOT visible to default V1 agents
        # (which only see "1.0" tools).  The decide/resume endpoint creates a
        # "1.1" registry so the approved write tool is available for execution.
        from .write_note_tool import WriteNoteTool
        from .spec import ToolSpec as TS
        write_note_spec = TS(
            name="write_note",
            description="Write a note to the knowledge base. Requires human approval.",
            input_schema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The note content to write"},
                },
                "required": ["content"],
            },
            output_schema={"type": "object"},
            risk_level=RiskLevel.READ_WRITE,
            timeout_seconds=10.0,
            required_permissions=[Permissions.KB_WRITE],
            agent_version="1.1",
        )
        self._register(write_note_spec, WriteNoteTool())

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

        # Register plugin tools (sandboxed subprocess execution)
        self.register_plugin_tools()

    def _register(self, spec: ToolSpec, instance: BaseTool) -> None:
        self._specs[spec.name] = spec
        self._instances[spec.name] = instance

    def register_plugin_tools(self) -> int:
        """Register all enabled plugin tools into this registry.

        Plugin tools are loaded from the plugin registry and injected as
        ToolSpec objects with _plugin_id metadata.  Execution is routed
        through the sandboxed subprocess runner.

        Returns the number of plugin tools registered.
        """
        try:
            from app.core.plugin.registry import list_all_tool_specs
        except ImportError:
            return 0

        plugin_specs = list_all_tool_specs(enabled_only=True)
        count = 0
        for pspec in plugin_specs:
            name = pspec.get("name")
            if not name or name in self._specs:
                continue  # skip duplicates

            plugin_id = pspec.get("_plugin_id", "")
            plugin_name = pspec.get("_plugin_name", "")
            plugin_version = pspec.get("_plugin_version", "")

            spec = ToolSpec(
                name=name,
                description=pspec.get("description", f"Plugin tool from {plugin_name}"),
                input_schema=pspec.get("input_schema", {"type": "object", "properties": {}}),
                output_schema=pspec.get("output_schema", {"type": "object"}),
                risk_level=pspec.get("risk_level", RiskLevel.READ_ONLY),
                timeout_seconds=pspec.get("timeout_seconds", 10.0),
                required_permissions=pspec.get("required_permissions", []),
                error_codes=pspec.get("error_codes", {}),
                agent_version=pspec.get("agent_version", self._agent_version),
            )
            # Attach plugin metadata for routing
            spec._plugin_id = plugin_id  # type: ignore
            spec._plugin_name = plugin_name  # type: ignore

            self._specs[name] = spec
            # No local instance — execution goes through sandbox runner
            self._instances[name] = None  # type: ignore
            count += 1

        if count:
            logger.info("已注册 %d 个插件工具到 ToolRegistry", count)
        return count

    # ── Tool discovery ────────────────────────────────────────────────

    def get_spec(self, tool_name: str) -> Optional[ToolSpec]:
        """Return the ToolSpec for *any* registered tool (including non-V1)."""
        return self._specs.get(tool_name)

    @staticmethod
    def _v1_compatible_versions(registry_version: str) -> set:
        """Return the set of ``agent_version`` values visible to a V1 registry.

        Registry "1.0" sees only "1.0" tools (read-only KB tools).
        Registry "1.1" sees "1.0" + "1.1" tools (adds write_note).
        """
        if registry_version == "1.1":
            return {"1.0", "1.1"}
        return {"1.0"}

    def get_tools(
        self,
        agent_version: Optional[str] = None,
        v1_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """Return tool definitions visible to the given agent version.

        V1 agents (``agent_version="1.0"``) see only V1-whitelisted tools
        (search_knowledge_base, read_chunk, list_document_chunks).
        V1.1 agents (``agent_version="1.1"``) additionally see write_note.
        Non-V1 callers (MCP server) pass ``v1_only=False`` to see all tools.
        """
        version = agent_version or self._agent_version
        compatible = self._v1_compatible_versions(version) if v1_only else None
        tools: List[Dict[str, Any]] = []
        for name, spec in self._specs.items():
            if v1_only and spec.agent_version not in compatible:
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
        context: Optional[Any] = None,  # AgentExecutionContext (lazy import)
    ) -> ToolResult:
        """Execute a tool through the registry.

        Validates:
          1. Tool is registered
          2. Tool is available for the current agent version
          3. **Permission check** — context must grant every required permission
          4. **Mode gate** — read_only mode rejects write / external tools
          5. **KB scope** — tool's knowledge_base_id must match context
          6. Input matches the input_schema
          7. Knowledge base is set (for KB-scoped tools)
        """
        spec = self._specs.get(tool_name)
        if spec is None:
            return ToolResult.failure(
                tool_name=tool_name,
                error_code=ErrorCode.NOT_FOUND,
                message=f"工具 '{tool_name}' 未注册",
            )

        # Agent-version gate (registry-level; context-based check follows)
        if spec.agent_version != self._agent_version:
            return ToolResult.failure(
                tool_name=tool_name,
                error_code=ErrorCode.SCOPE_DENIED,
                message=f"工具 '{tool_name}' 不在 Agent V{self._agent_version} 白名单中",
            )

        # ── Permission & mode checks (when context is present) ────────
        if context is not None:
            # ── Build sanitised input early (needed for scoped grant hash) ──
            _safe_for_grant = dict(tool_input)
            _safe_for_grant.pop("knowledge_base_id", None)
            _safe_for_grant.pop("user_id", None)

            # ── Agent V1 Step 5: Scoped grant check (one-time approval bypass) ──
            # A scoped grant is a one-shot permission bypass registered by the
            # /api/agent/v1/chat/decide endpoint after human approval.  It is
            # consumed on first match — the next call to the same tool with
            # different parameters will NOT match and MUST go through approval.
            scoped_grant_consumed = consume_scoped_grant(
                tool_name, _safe_for_grant,
                user_id=context.user_id,
                knowledge_base_id=context.knowledge_base_id,
            )

            if not scoped_grant_consumed:
                # ── Policy engine: tri-state governance (allow/deny/needs-approval) ──
                # Defines whether this tool runs, needs a human, or is refused.
                # The scoped grant above (one-shot), when present, short-circuits
                # policy because the grant IS the post-approval authorization.
                from app.core.policy.engine import PolicyAction
                verdict = self._policy_engine.evaluate(
                    tool_name=tool_name,
                    risk_level=spec.risk_level,
                    required_permissions=frozenset(spec.required_permissions or []),
                    ctx=self._build_policy_context(context),
                )
                if verdict.action == PolicyAction.DENY:
                    return ToolResult.failure(
                        tool_name=tool_name,
                        error_code=ErrorCode.PERMISSION_DENIED,
                        message=verdict.reason,
                    )
                if verdict.action == PolicyAction.NEEDS_APPROVAL:
                    summary_input = dict(tool_input)
                    summary_input.pop("knowledge_base_id", None)
                    summary_input.pop("user_id", None)
                    return ToolResult.approval_required(
                        tool_name=tool_name,
                        tool_input=summary_input,
                        message=verdict.reason,
                    )
                # ALLOW → required-permission check (approval may still gate above).
                for perm in spec.required_permissions:
                    if not context.has_permission(perm):
                        return ToolResult.failure(
                            tool_name=tool_name,
                            error_code=ErrorCode.PERMISSION_DENIED,
                            message=(
                                f"工具 '{tool_name}' 需要权限 '{perm}'，"
                                f"当前上下文未授予该权限"
                            ),
                        )
            # else: scoped grant consumed — skip ALL permission/mode/policy checks.
            # The grant IS the authorization for this exact tool+parameters.

        # KB-scope enforcement (read OR write KB tools)
        if (Permissions.KB_READ in spec.required_permissions
                or Permissions.KB_WRITE in spec.required_permissions):
            if not self._knowledge_base_id or self._knowledge_base_id <= 0:
                return ToolResult.failure(
                    tool_name=tool_name,
                    error_code=ErrorCode.SCOPE_DENIED,
                    message="未指定知识库ID，无法执行知识库操作",
                )
            # Cross-KB check: context KB must match registry KB.
            if context is not None and not context.owns_knowledge_base(self._knowledge_base_id):
                return ToolResult.failure(
                    tool_name=tool_name,
                    error_code=ErrorCode.SCOPE_DENIED,
                    message=(
                        f"无权访问知识库 {self._knowledge_base_id}，"
                        f"当前上下文限定知识库 {context.knowledge_base_id}"
                    ),
                )

        # Input validation against JSON Schema
        validation_error = self._validate_input(spec, tool_input)
        if validation_error:
            return ToolResult.failure(
                tool_name=tool_name,
                error_code=ErrorCode.INVALID_INPUT,
                message=validation_error,
            )

        # ── Anti-spoofing: strip model-supplied identity fields ───────
        # The model MUST NOT be able to forge user_id or knowledge_base_id.
        # The Registry injects the real values from the context / registry.
        safe_input = dict(tool_input)
        safe_input.pop("knowledge_base_id", None)
        safe_input.pop("user_id", None)
        # Inject KB ID for any KB-scoped tool (read OR write).
        if (Permissions.KB_READ in spec.required_permissions
                or Permissions.KB_WRITE in spec.required_permissions):
            safe_input["knowledge_base_id"] = self._knowledge_base_id

        # ── Plugin tool routing ─────────────────────────────────────
        # If the tool spec carries a _plugin_id, it was registered by
        # the plugin system.  Route through the sandboxed subprocess
        # runner instead of the local instance path.
        plugin_id = getattr(spec, '_plugin_id', None) or (
            spec.__dict__.get('_plugin_id') if hasattr(spec, '__dict__') else None
        )
        # Also check the raw tools dict for plugin metadata
        if plugin_id is None and tool_name in self._specs:
            raw = self._specs[tool_name]
            plugin_id = getattr(raw, '_plugin_id', None)

        if plugin_id is not None:
            return await self._execute_plugin_tool(
                plugin_id=plugin_id,
                tool_name=tool_name,
                safe_input=safe_input,
                timeout_seconds=timeout_seconds or spec.timeout_seconds,
                context=context,
            )

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

    # ── Plugin tool execution ─────────────────────────────────────────

    async def _execute_plugin_tool(
        self,
        plugin_id: str,
        tool_name: str,
        safe_input: Dict[str, Any],
        timeout_seconds: float,
        context: Optional[Any] = None,
    ) -> ToolResult:
        """Execute a plugin tool through the sandboxed subprocess runner.

        This is the bridge between the Agent ToolRegistry and the plugin
        sandbox system.  All plugin code runs in an isolated subprocess
        with resource limits, network/filesystem restrictions, and timeout
        enforcement.
        """
        from app.core.plugin.registry import execute_plugin_tool, get_plugin

        plugin = get_plugin(plugin_id)
        if plugin is None:
            return ToolResult.failure(
                tool_name=tool_name,
                error_code=ErrorCode.NOT_FOUND,
                message=f"插件未注册: {plugin_id}",
            )

        if not plugin.enabled:
            return ToolResult.failure(
                tool_name=tool_name,
                error_code=ErrorCode.PERMISSION_DENIED,
                message=f"插件已禁用: {plugin_id}",
            )

        # Extract trace_id from context if available
        trace_id = None
        if context is not None:
            trace_id = getattr(context, 'trace_id', None)

        started = time.monotonic()
        result = execute_plugin_tool(
            plugin_id=plugin_id,
            tool_name=tool_name,
            tool_input=safe_input,
            trace_id=trace_id,
        )
        elapsed = round((time.monotonic() - started) * 1000, 2)

        if result.success:
            return ToolResult.success(
                tool_name=tool_name,
                data=result.data,
                duration_ms=elapsed,
            )
        else:
            error_code = result.error_code or ErrorCode.INTERNAL
            return ToolResult.failure(
                tool_name=tool_name,
                error_code=error_code,
                message=result.error or "插件执行失败",
                duration_ms=elapsed,
            )

    # ── Input validation ──────────────────────────────────────────────

    # ── Policy context ─────────────────────────────────────────────────

    def _build_policy_context(self, context: Any) -> PolicyContext:
        """Translate an AgentExecutionContext into a PolicyContext, resolving flags."""
        # Resolve feature flags lazily; transparent/fail-open modes return True,
        # so the registry's policy defaults mirror current behavior in tests.
        from app.core.policy.engine import PolicyContext
        from app.utils.feature_flag import feature_flags
        from app.utils.config import config

        user_id = getattr(context, "user_id", 0)
        kb_id = getattr(context, "knowledge_base_id", self._knowledge_base_id) or 0
        environment = getattr(context, "environment", None) or config.SERVER_ENV
        flags = {
            # The flag client resolves user/kb/environment scoped overrides; in
            # tests these default to True via transparent degradation.
            "agent.write_tools.enabled": feature_flags.is_enabled(
                "agent.write_tools.enabled", user_id=user_id, knowledge_base_id=kb_id,
                environment=environment,
            ),
            "agent.web_search.enabled": feature_flags.is_enabled(
                "agent.web_search.enabled", user_id=user_id, knowledge_base_id=kb_id,
                environment=environment,
            ),
            "approval.required_for_write": feature_flags.is_enabled(
                "approval.required_for_write", user_id=user_id, knowledge_base_id=kb_id,
                environment=environment,
            ),
            "policy.admin_bypass_approval": feature_flags.is_enabled(
                "policy.admin_bypass_approval", user_id=user_id, knowledge_base_id=kb_id,
                environment=environment,
            ),
        }
        return PolicyContext(
            user_id=getattr(context, "user_id", 0),
            knowledge_base_id=kb_id,
            role=getattr(context, "user_role", "user") or "user",
            environment=environment,
            mode=getattr(context, "mode", "read_only"),
            capability_profile=getattr(context, "capability_profile", None),
            flags=flags,
            permissions=frozenset(getattr(context, "permissions", frozenset()) or frozenset()),
        )

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
def create_v1_registry(knowledge_base_id: int, agent_version: str = "1.0") -> ToolRegistry:
    """Create a ToolRegistry for Agent V1 with the given KB scope.

    ``agent_version="1.0"`` → read-only KB tools only.
    ``agent_version="1.1"`` → also includes write_note (for approve/resume flow).
    """
    if not knowledge_base_id or knowledge_base_id <= 0:
        raise RegistryError("Agent V1 registry requires a non-null knowledge_base_id")
    return ToolRegistry(knowledge_base_id=knowledge_base_id, agent_version=agent_version)


def create_full_registry(knowledge_base_id: Optional[int] = None) -> ToolRegistry:
    """Create a ToolRegistry with all tools (for MCP / non-agent use)."""
    return ToolRegistry(knowledge_base_id=knowledge_base_id, agent_version="1.0")
