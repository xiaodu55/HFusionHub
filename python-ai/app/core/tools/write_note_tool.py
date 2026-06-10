"""WriteNoteTool — 高风险写入工具：把笔记持久化到 Java 后端（note 表）。

risk_level=READ_WRITE，需要人工审批后才能执行（Agent V1 Step 5）。
审批通过后由 decide/resume 流程以 scoped grant 放行，本工具执行时将
笔记内容回调 Java 的 /api/internal/notes 端点保存。

Security:
  - ``knowledge_base_id`` 与 ``user_id`` 均由 ToolRegistry 从执行上下文注入，
    模型无法伪造。
  - 回调 Java 使用 X-Internal-Token（与 Java 端配置一致）。
  - 返回 ``{"error": ...}`` 会让 Registry 产生 ToolResult.failure，而不是
    谎报写入成功。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.core.tools.base import BaseTool

logger = logging.getLogger(__name__)


class WriteNoteTool(BaseTool):
    """写入一条笔记（持久化到 Java 后端 note 表）。"""

    async def execute(
        self,
        content: str,
        knowledge_base_id: int,
        user_id: Optional[int] = None,
        title: Optional[str] = None,
        conversation_id: Optional[int] = None,
        message_id: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Write a note to the knowledge base via the Java backend.

        Args:
            content: The note content (Markdown).
            knowledge_base_id: Target KB ID — injected by the ToolRegistry
                from the execution context (anti-spoofing).
            user_id: Authenticated user ID — injected by the ToolRegistry
                from the execution context (anti-spoofing).
            title: Optional note title.
        """
        # ── Security: knowledge_base_id MUST be a valid positive integer ──
        if knowledge_base_id is None or (isinstance(knowledge_base_id, str) and knowledge_base_id == "unknown"):
            logger.error("[write_note] REJECTED: knowledge_base_id is missing or 'unknown'")
            return {"error": "knowledge_base_id 是必填参数，拒绝写入到 unknown 知识库"}
        if not isinstance(knowledge_base_id, int) or knowledge_base_id <= 0:
            logger.error("[write_note] REJECTED: invalid knowledge_base_id=%s", knowledge_base_id)
            return {"error": f"knowledge_base_id 必须为正整数，收到: {knowledge_base_id}"}

        # ── Security: user_id MUST be present (injected by registry) ──────
        if user_id is None or user_id <= 0:
            logger.error("[write_note] REJECTED: missing user_id")
            return {"error": "缺少用户身份（user_id），拒绝写入"}

        if not content or not str(content).strip():
            return {"error": "笔记内容不能为空"}

        # ── Persist via Java backend (internal endpoint) ──────────────────
        try:
            import httpx

            # 注意：必须从 app.utils.config 导入 Config 实例（config = Config()），
            # 而非 app.utils.config 模块本身——模块上没有 JAVA_BACKEND_URL 等属性
            from app.utils.config import config

            url = f"{config.JAVA_BACKEND_URL}/api/internal/notes"
            payload = {
                "user_id": int(user_id),
                "knowledge_base_id": int(knowledge_base_id),
                "tenant_id": kwargs.get("tenant_id"),
                "conversation_id": conversation_id,
                "message_id": message_id,
                "title": str(title or "").strip(),
                "content": str(content),
                "source": "agent_write_note",
            }
            headers = {"X-Internal-Token": config.INTERNAL_API_TOKEN or ""}
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
            if resp.is_error:
                logger.error("[write_note] Java backend returned %s", resp.status_code)
                return {"error": f"笔记保存失败：Java 后端返回 HTTP {resp.status_code}"}
            data = resp.json()
            if data.get("code") != 200:
                msg = data.get("msg") or "unknown error"
                logger.error("[write_note] Java rejected note: %s", msg)
                return {"error": f"笔记保存失败：{msg}"}
            note_id = (data.get("data") or {}).get("note_id")
            saved_title = (data.get("data") or {}).get("title") or ""
            logger.info("[write_note] Note persisted: note_id=%s user_id=%s kb_id=%s", note_id, user_id, knowledge_base_id)
            return {
                "success": True,
                "note_id": note_id,
                "title": saved_title,
                "message": f"笔记已保存到知识库（ID: {note_id}）",
            }
        except Exception as exc:
            logger.error("[write_note] persistence error: %s", exc)
            return {"error": f"笔记保存失败：{exc}"}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": "write_note",
            "description": "把内容整理成笔记并保存到知识库。需要人工审批。",
        }
