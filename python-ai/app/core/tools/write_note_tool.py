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

        # In production, this would write to the database.
        # For V1 approval testing, we simulate the write.
        logger.info("[write_note] Writing note to KB %d: %s", knowledge_base_id, content[:100])
        return {
            "status": "written",
            "knowledge_base_id": knowledge_base_id,
            "content_preview": content[:200],
            "char_count": len(content),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": "write_note",
            "description": "Write a note to the knowledge base. Requires human approval.",
        }
