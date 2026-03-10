"""ApprovalStore — thread-safe in-memory store for pending tool approvals.

Agent V1 Step 5: When a high-risk tool is detected, an ApprovalRequest is
created and stored here.  The resume endpoint checks this store to determine
whether the tool can now be executed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Dict, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

APPROVAL_EXPIRY_MINUTES = 5


@dataclass
class StoredApproval:
    """An approval record held in memory pending a human decision."""

    approval_id: str
    task_id: int
    run_id: int
    user_id: int
    tool_name: str
    tool_input: Dict[str, Any]
    arguments_summary: str
    status: str = "pending"  # pending | approved | denied
    reason: Optional[str] = None
    expires_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(minutes=APPROVAL_EXPIRY_MINUTES)
    )
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def is_approved(self) -> bool:
        return self.status == "approved" and not self.is_expired

    def approve(self, reason: Optional[str] = None) -> None:
        if self.status != "pending":
            raise ValueError(f"Cannot approve: status is '{self.status}'")
        if self.is_expired:
            self.status = "expired"
            raise ValueError("Approval has expired")
        self.status = "approved"
        self.reason = reason

    def deny(self, reason: Optional[str] = None) -> None:
        if self.status != "pending":
            raise ValueError(f"Cannot deny: status is '{self.status}'")
        self.status = "denied"
        self.reason = reason

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "user_id": self.user_id,
            "tool_name": self.tool_name,
            "arguments_summary": self.arguments_summary,
            "status": self.status,
            "reason": self.reason,
            "expires_at": self.expires_at.isoformat(),
            "created_at": self.created_at.isoformat(),
        }


class ApprovalStore:
    """Thread-safe in-memory store for pending approvals."""

    def __init__(self, max_entries: int = 1000):
        self._pending: Dict[str, StoredApproval] = {}
        self._lock = Lock()
        self._max = max(1, max_entries)

    def create(
        self,
        task_id: int,
        run_id: int,
        user_id: int,
        tool_name: str,
        tool_input: Dict[str, Any],
        arguments_summary: str,
    ) -> StoredApproval:
        """Create a pending approval and return it."""
        approval_id = str(uuid4())
        approval = StoredApproval(
            approval_id=approval_id,
            task_id=task_id,
            run_id=run_id,
            user_id=user_id,
            tool_name=tool_name,
            tool_input=tool_input,
            arguments_summary=arguments_summary,
        )
        with self._lock:
            if len(self._pending) >= self._max:
                # Evict oldest expired entries
                expired = [k for k, v in self._pending.items() if v.is_expired]
                for k in expired:
                    del self._pending[k]
            self._pending[approval_id] = approval
        logger.info("Approval created: id=%s tool=%s", approval_id, tool_name)
        return approval

    def get(self, approval_id: str) -> Optional[StoredApproval]:
        with self._lock:
            return self._pending.get(approval_id)

    def decide(self, approval_id: str, decision: str, user_id: int, reason: Optional[str] = None) -> StoredApproval:
        """Approve or deny a pending approval.  Raises ValueError on invalid state."""
        with self._lock:
            approval = self._pending.get(approval_id)
            if approval is None:
                raise ValueError(f"Approval not found: {approval_id}")
            if approval.user_id != user_id:
                raise ValueError("User not authorized for this approval")
            if decision == "approved":
                approval.approve(reason)
            elif decision == "denied":
                approval.deny(reason)
            else:
                raise ValueError(f"Invalid decision: {decision}")
            return approval

    def is_approved(self, approval_id: str) -> bool:
        """Check if a tool execution is approved (for ToolRegistry bypass)."""
        with self._lock:
            approval = self._pending.get(approval_id)
            return approval is not None and approval.is_approved

    def remove(self, approval_id: str) -> None:
        with self._lock:
            self._pending.pop(approval_id, None)

    def list_pending(self, user_id: Optional[int] = None) -> list:
        with self._lock:
            items = list(self._pending.values())
            if user_id is not None:
                items = [a for a in items if a.user_id == user_id]
            return [a.to_dict() for a in items if a.status == "pending" and not a.is_expired]

    def cleanup_expired(self) -> int:
        """Remove expired entries. Returns count of removed entries."""
        with self._lock:
            expired = [k for k, v in self._pending.items() if v.is_expired and v.status == "pending"]
            for k in expired:
                self._pending[k].status = "expired"
                del self._pending[k]
            return len(expired)


# Module-level singleton
_approval_store: Optional[ApprovalStore] = None


def get_approval_store() -> ApprovalStore:
    global _approval_store
    if _approval_store is None:
        _approval_store = ApprovalStore()
    return _approval_store
