"""Tool execution policy engine — Agent tool governance.

Replaces the ad-hoc mode/permission gates with a single, deterministic
tri-state decision model:

  ALLOW          → the tool may execute (subject to permission / KB-scope /
                    schema checks enforced by the ToolRegistry).
  NEEDS_APPROVAL → a human must approve first (agent pauses for approval).
  DENY           → the tool is refused outright for this context.

Decisions are keyed on the actor identity (user / role), the target knowledge
base, the environment, feature flags, and the tool's declared risk level and
permissions.  The engine is a pure function over a :class:`PolicyContext` and a
tool spec — it performs no I/O; callers resolve feature flags and pass them in.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.core.tools.spec import RiskLevel

logger = logging.getLogger(__name__)


class PolicyAction:
    ALLOW = "allow"
    DENY = "deny"
    NEEDS_APPROVAL = "needs_approval"


MODE_READ_ONLY = "read_only"
MODE_READ_WRITE = "read_write"


@dataclass(frozen=True)
class PolicyContext:
    """Inputs the engine uses to reach a decision.  Immutable, provider-agnostic."""

    user_id: int
    knowledge_base_id: int
    role: str = "user"
    environment: str = "development"
    mode: str = MODE_READ_ONLY
    capability_profile: str | None = None
    flags: dict[str, bool] = field(default_factory=dict)
    permissions: frozenset[str] = frozenset()


@dataclass(frozen=True)
class PolicyVerdict:
    action: str
    reason: str
    rule: str | None = None
    risk_level: str | None = None


class PolicyEngine:
    """Deterministic tri-state tool governance engine.

    Decision pipeline (first match wins, in this order):

      1. Environment lockout — production forbids external network tools.
      2. Mode base — read_only runs read tools; write/external require approval;
         read_write (approved resume) runs everything.
      3. Feature-flag deny overrides (SECURITY flags fail closed):
         - ``agent.write_tools.enabled`` off → write/external DENY
         - ``agent.web_search.enabled`` off  → web_search DENY
      4. Role override — trusted operators (``role=admin``) may bypass approval
         when ``policy.admin_bypass_approval`` is on (default).
      5. Approval-required flag — when ``approval.required_for_write`` is OFF,
         write tools run without approval (unless a higher rule already denied).
    """

    def evaluate(
        self,
        *,
        tool_name: str,
        risk_level: str,
        required_permissions: frozenset[str],
        ctx: PolicyContext,
    ) -> PolicyVerdict:
        env = (ctx.environment or "development").lower()
        flags = ctx.flags

        # 1. Environment lockout (defense in depth).
        if env == "production" and risk_level == RiskLevel.EXTERNAL:
            return PolicyVerdict(
                PolicyAction.DENY,
                "生产环境禁止外部网络工具",
                rule="env:production:external",
                risk_level=risk_level,
            )

        # 2. Feature-flag deny overrides (highest enforcement, fail closed).
        if risk_level in (RiskLevel.READ_WRITE, RiskLevel.EXTERNAL):
            if not flags.get("agent.write_tools.enabled", True):
                return PolicyVerdict(
                    PolicyAction.DENY,
                    f"工具 '{tool_name}' 风险等级为 {risk_level}，写入工具已被策略禁用",
                    rule="flag:agent.write_tools.enabled",
                    risk_level=risk_level,
                )
            if not flags.get("agent.web_search.enabled", True) and tool_name == "web_search":
                return PolicyVerdict(
                    PolicyAction.DENY,
                    "web_search 已被策略禁用",
                    rule="flag:agent.web_search.enabled",
                    risk_level=risk_level,
                )

        # Mode base gate (mirrors legacy allows_risk_level).
        if ctx.mode == MODE_READ_ONLY:
            base = PolicyAction.ALLOW if risk_level == RiskLevel.READ_ONLY else PolicyAction.NEEDS_APPROVAL
        else:
            base = PolicyAction.ALLOW

        # 3. Role override — trusted operator bypasses approval (when enabled).
        if (
            base == PolicyAction.NEEDS_APPROVAL
            and ctx.role == "admin"
            and flags.get("policy.admin_bypass_approval", True)
        ):
            return PolicyVerdict(
                PolicyAction.ALLOW,
                f"管理员角色 {ctx.role} 被授予执行权限，跳过审批",
                rule="role:admin:bypass",
                risk_level=risk_level,
            )

        # 4. Approval-required flag off → run without approval.
        if base == PolicyAction.NEEDS_APPROVAL and not flags.get("approval.required_for_write", True):
            return PolicyVerdict(
                PolicyAction.ALLOW,
                "审批未启用，直接执行",
                rule="flag:approval.required_for_write",
                risk_level=risk_level,
            )

        return PolicyVerdict(
            base,
            _base_reason(base, tool_name, risk_level, ctx.mode),
            rule="mode:" + ctx.mode,
            risk_level=risk_level,
        )

    # ── Content guardrails (defense in depth on top of the tri-state gate) ──

    def guard_tool_input(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        ctx: PolicyContext,
    ) -> PolicyVerdict | None:
        """Run content guardrails on tool arguments before execution.

        Returns a DENY verdict when the input is blocked (critical prompt
        injection or toxic content); returns None when it passes or the
        guardrails are disabled.  Callers (e.g. ToolRegistry) refuse tool
        execution on a DENY verdict.
        """
        if not tool_input:
            return None
        from app.core.policy.guardrails import guardrails_pipeline
        try:
            serialized = json.dumps(tool_input, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            serialized = str(tool_input)
        result = guardrails_pipeline.check_input(
            serialized,
            context={
                "channel": "tool",
                "tool_name": tool_name,
                "user_id": ctx.user_id,
                "knowledge_base_id": ctx.knowledge_base_id,
                "environment": ctx.environment,
            },
        )
        if not result.allowed:
            logger.warning(
                "Guardrails denied tool '%s': %s (flags=%s)",
                tool_name, result.blocked_reason, result.flags,
            )
            return PolicyVerdict(
                PolicyAction.DENY,
                f"工具 '{tool_name}' 的参数未通过内容安全校验（{result.blocked_reason}）",
                rule=f"guardrails:input:{result.blocked_reason}",
                risk_level=None,
            )
        return None

    def guard_model_output(
        self,
        content: str,
        ctx: PolicyContext | None = None,
    ) -> tuple[str, PolicyVerdict | None]:
        """Run content guardrails on the model response before returning it.

        Returns ``(sanitized_content, verdict)``.  The verdict is None when
        the response passes; when blocked, the sanitized content is returned
        alongside a DENY verdict so the caller can decide how to present it
        (e.g. substitute a refusal message).
        """
        if not content:
            return content, None
        from app.core.policy.guardrails import guardrails_pipeline
        result = guardrails_pipeline.check_output(
            content,
            context={
                "channel": "output",
                "user_id": ctx.user_id if ctx else None,
                "knowledge_base_id": ctx.knowledge_base_id if ctx else None,
                "environment": ctx.environment if ctx else None,
            },
        )
        if not result.allowed:
            logger.warning(
                "Guardrails denied model output: %s (flags=%s)",
                result.blocked_reason, result.flags,
            )
            return result.sanitized_content, PolicyVerdict(
                PolicyAction.DENY,
                f"AI 回答未通过内容安全校验（{result.blocked_reason}）",
                rule=f"guardrails:output:{result.blocked_reason}",
                risk_level=None,
            )
        return result.sanitized_content, None


def _base_reason(action: str, tool_name: str, risk_level: str, mode: str) -> str:
    if action == PolicyAction.ALLOW:
        return f"工具 '{tool_name}' 风险等级 {risk_level} 已在 {mode} 模式下放行"
    if action == PolicyAction.NEEDS_APPROVAL:
        return (
            f"工具 '{tool_name}' 风险等级为 {risk_level}，"
            f"当前模式 {mode} 需要人工审批"
        )
    return f"工具 '{tool_name}' 被策略拒绝"
