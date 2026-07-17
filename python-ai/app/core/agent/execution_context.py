"""Agent Execution Context & Approval Boundary — Agent V1 Step 3.

The ``AgentExecutionContext`` is created by Java after authentication and
passed to Python.  It is **immutable** and **cannot be forged by the model**
because the model never sees it — it is only consumed by the Tool Registry
at execution time.

The ``ApprovalRequest`` models a human-approval gate for future write /
external tools.  V1 (read_only mode) does NOT open write tools, but the
approval data structure is defined here so it can be adopted uniformly
when write tools are introduced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from ..tools.spec import RiskLevel

# ── Valid modes ────────────────────────────────────────────────────────────

MODE_READ_ONLY = "read_only"
MODE_READ_WRITE = "read_write"

_VALID_MODES = {MODE_READ_ONLY, MODE_READ_WRITE}

# ── Approval statuses ──────────────────────────────────────────────────────

APPROVAL_PENDING = "pending"
APPROVAL_APPROVED = "approved"
APPROVAL_DENIED = "denied"
APPROVAL_EXPIRED = "expired"

_APPROVAL_TERMINAL = {APPROVAL_APPROVED, APPROVAL_DENIED, APPROVAL_EXPIRED}


# ═══════════════════════════════════════════════════════════════════════════
# Agent Execution Context
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class AgentExecutionContext:
    """Immutable, Java-authored context for a single Agent run.

    The model CANNOT forge or override these values — they are injected by
    the Tool Registry at execution time after stripping any user-supplied
    ``user_id`` / ``knowledge_base_id`` from the tool input.

    Fields:
        user_id: Authenticated user ID (from Java session).
        knowledge_base_id: Target knowledge base ID (from conversation scope).
        permissions: Set of permission strings, e.g. ``{"knowledge_base:read"}``.
        agent_run_id: UUID of the current agent run.
        mode: ``"read_only"`` (V1 default) or ``"read_write"`` (resume after approval).
        capability_profile: ``"approval_write"`` enables V1.1 write tools (write_note)
            while keeping read_only mode — the agent can SEE write_note but the
            registry returns approval_required on invocation.  Must be explicitly
            chosen by Java; the model cannot upgrade its own capability.
    """

    user_id: int
    knowledge_base_id: int
    tenant_id: int | None = None
    permissions: frozenset[str] = field(default_factory=lambda: frozenset({"knowledge_base:read"}))
    agent_run_id: str = ""
    mode: str = MODE_READ_ONLY
    capability_profile: str | None = None
    user_role: str = "user"
    environment: str | None = None

    _VALID_PROFILES = {None, "approval_write"}
    _VALID_ROLES = {"user", "admin"}

    def __post_init__(self):
        if self.mode not in _VALID_MODES:
            raise ValueError(f"Invalid mode: {self.mode!r}. Must be one of {_VALID_MODES}")
        if self.user_id <= 0:
            raise ValueError(f"user_id must be positive, got {self.user_id}")
        if self.knowledge_base_id <= 0:
            raise ValueError(f"knowledge_base_id must be positive, got {self.knowledge_base_id}")
        if self.tenant_id is not None and self.tenant_id <= 0:
            raise ValueError(f"tenant_id must be positive when set, got {self.tenant_id}")
        if self.capability_profile not in self._VALID_PROFILES:
            raise ValueError(
                f"Invalid capability_profile: {self.capability_profile!r}. "
                f"Must be one of {self._VALID_PROFILES}"
            )
        if self.user_role not in self._VALID_ROLES:
            raise ValueError(
                f"Invalid user_role: {self.user_role!r}. Must be one of {self._VALID_ROLES}"
            )

    # ── Permission helpers ────────────────────────────────────────────────

    def has_permission(self, permission: str) -> bool:
        """Return True when the context grants *permission*."""
        return permission in self.permissions

    def allows_risk_level(self, risk_level: str) -> bool:
        """Return True when the current *mode* permits *risk_level*.

        V1 (read_only):
          - ``read_only`` tools → auto-execute ✅
          - ``read_write`` / ``external`` → denied ❌
        """
        if self.mode == MODE_READ_ONLY:
            return risk_level == RiskLevel.READ_ONLY
        # read_write mode allows everything
        return True

    def owns_knowledge_base(self, kb_id: int) -> bool:
        """Return True when *kb_id* matches the context's knowledge base."""
        return kb_id == self.knowledge_base_id

    # ── Serialisation ─────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "knowledge_base_id": self.knowledge_base_id,
            "tenant_id": self.tenant_id,
            "permissions": sorted(self.permissions),
            "agent_run_id": self.agent_run_id,
            "mode": self.mode,
            "capability_profile": self.capability_profile,
            "user_role": self.user_role,
            "environment": self.environment,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Approval Request
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ApprovalRequest:
    """Human-approval gate for a single tool invocation.

    V1 (read_only) does NOT require approval — all three V1 tools are
    ``read_only`` and execute automatically.  This data structure is defined
    NOW so that when write / external tools are introduced the approval
    boundary is already modelled uniformly.

    Lifecycle:
      pending → approved  (tool executes)
      pending → denied    (tool skipped, agent notified)
      pending → expired   (treated as denied)
    """

    approval_id: str
    agent_run_id: str
    tool_name: str
    arguments_summary: str       # Desensitised — never includes raw PII / full content.
    status: str = APPROVAL_PENDING
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(minutes=5))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # ── Status helpers ────────────────────────────────────────────────────

    @property
    def is_terminal(self) -> bool:
        return self.status in _APPROVAL_TERMINAL

    @property
    def is_approved(self) -> bool:
        return self.status == APPROVAL_APPROVED

    @property
    def is_expired(self) -> bool:
        if self.status == APPROVAL_EXPIRED:
            return True
        if self.status == APPROVAL_PENDING and datetime.now(UTC) > self.expires_at:
            self.status = APPROVAL_EXPIRED
            return True
        return False

    # ── Actions ───────────────────────────────────────────────────────────

    def approve(self) -> None:
        if self.is_terminal:
            raise ValueError(f"Cannot approve: approval is already {self.status}")
        self.status = APPROVAL_APPROVED

    def deny(self) -> None:
        if self.is_terminal:
            raise ValueError(f"Cannot deny: approval is already {self.status}")
        self.status = APPROVAL_DENIED

    # ── Serialisation ─────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "approval_id": self.approval_id,
            "agent_run_id": self.agent_run_id,
            "tool_name": self.tool_name,
            "arguments_summary": self.arguments_summary,
            "status": self.status,
            "expires_at": self.expires_at.isoformat(),
            "created_at": self.created_at.isoformat(),
        }
