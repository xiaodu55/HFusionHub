"""WriteNoteTool — 高风险写入工具，用于测试 Agent V1 Step 5 审批流程。

risk_level=READ_WRITE，需要人工审批后才能执行。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from app.core.tools.base import BaseTool

logger = logging.getLogger(__name__)


class WriteNoteTool(BaseTool):
    """写入一条笔记到知识库（高风险：修改状态）。

    此工具仅用于测试审批流程。生产环境中应实现实际的写入逻辑。

    Security (Agent V1 Step 5):
      - ``knowledge_base_id`` is REQUIRED and MUST be a positive integer.
        The ToolRegistry anti-spoofing layer injects this from the execution
        context — the model CANNOT supply or forge it.
      - Returning ``{"error": "..."}`` causes the Registry to produce a
        ``ToolResult.failure(error_code=internal_error, message=...)``
        instead of pretending the write succeeded with "unknown".
    """

    async def execute(self, content: str, knowledge_base_id: int, **kwargs) -> Dict[str, Any]:
        """Write a note to the specified knowledge base.

        Args:
            content: The note content to write.
            knowledge_base_id: Target knowledge base ID (REQUIRED — injected
                by the ToolRegistry from the execution context; the model
                cannot forge this value).
        """
        # ── Security: knowledge_base_id MUST be a valid positive integer ──
        if knowledge_base_id is None or (isinstance(knowledge_base_id, str) and knowledge_base_id == "unknown"):
            logger.error("[write_note] REJECTED: knowledge_base_id is missing or 'unknown'")
            return {"error": "knowledge_base_id 是必填参数，拒绝写入到 unknown 知识库"}
        if not isinstance(knowledge_base_id, int) or knowledge_base_id <= 0:
            logger.error("[write_note] REJECTED: invalid knowledge_base_id=%s", knowledge_base_id)
            return {"error": f"knowledge_base_id 必须为正整数，收到: {knowledge_base_id}"}

        # This tool has no durable repository implementation yet. Never claim
        # success for a write that was only logged; callers can surface this as
        # an explicit capability-unavailable error and retry safely later.
        logger.error("[write_note] rejected: durable note persistence is not configured")
        return {"error": "write_note is unavailable until durable note persistence is configured"}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": "write_note",
            "description": "Write a note to the knowledge base. Requires human approval.",
        }
