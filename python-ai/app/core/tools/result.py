"""ToolResult — unified tool execution result for Agent V1.

Every tool execution MUST return a ToolResult.  Success and failure
share the same structure; the ``ok`` flag disambiguates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ToolResult:
    """Unified execution result for ALL tool calls.

    Success:
        {"ok": true, "data": {...}, "tool_name": "search_knowledge_base",
         "duration_ms": 120}

    Failure:
        {"ok": false, "error_code": "knowledge_base_scope_denied",
         "message": "无权访问该知识库", "tool_name": "search_knowledge_base",
         "duration_ms": 0}
    """

    ok: bool
    tool_name: str
    duration_ms: float = 0.0
    # Success fields
    data: Any = None
    # Failure fields
    error_code: Optional[str] = None
    message: str = ""
    # Approval fields (Agent V1 Step 5)
    approval_required: bool = False
    approval_tool_input: Optional[Dict[str, Any]] = None

    # ── Factory methods ────────────────────────────────────────────────

    @classmethod
    def success(cls, tool_name: str, data: Any, duration_ms: float = 0.0) -> "ToolResult":
        return cls(
            ok=True,
            tool_name=tool_name,
            data=data,
            duration_ms=duration_ms,
        )

    @classmethod
    def failure(
        cls,
        tool_name: str,
        error_code: str,
        message: str = "",
        duration_ms: float = 0.0,
    ) -> "ToolResult":
        return cls(
            ok=False,
            tool_name=tool_name,
            error_code=error_code,
            message=message,
            duration_ms=duration_ms,
        )

    @classmethod
    def approval_required(
        cls,
        tool_name: str,
        tool_input: Dict[str, Any],
        message: str = "",
    ) -> "ToolResult":
        """High-risk tool requires human approval before execution."""
        return cls(
            ok=False,
            tool_name=tool_name,
            error_code="approval_required",
            message=message,
            approval_required=True,
            approval_tool_input=tool_input,
        )

    # ── Serialisation ──────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        base: Dict[str, Any] = {
            "ok": self.ok,
            "tool_name": self.tool_name,
            "duration_ms": self.duration_ms,
        }
        if self.ok:
            base["data"] = self.data
        else:
            base["error_code"] = self.error_code
            base["message"] = self.message
            if self.approval_required:
                base["approval_required"] = True
                base["approval_tool_input"] = self.approval_tool_input
        return base
