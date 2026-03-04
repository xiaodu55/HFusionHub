"""
Read Chunk Tool — Read full text of a single chunk by its chunk_id.

Agent V1 whitelisted tool.  Only reads chunks in the currently selected
knowledge base; the caller must pass knowledge_base_id for scope enforcement.
"""

from typing import Any, Dict, Optional

from .base import BaseTool


class ReadChunkTool(BaseTool):
    """Read the full text content of a specific document chunk."""

    def __init__(self, knowledge_base_id: Optional[int] = None):
        self.knowledge_base_id = knowledge_base_id

    async def execute(
        self,
        chunk_id: str,
        knowledge_base_id: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Read a single chunk by its chunk_id.

        Args:
            chunk_id: The chunk identifier, e.g. "4_chunk_0000".
            knowledge_base_id: Must match the selected knowledge base.

        Returns:
            Dict with chunk_id, content, document_id, title, metadata,
            or an error key when the chunk is not found or does not belong
            to the selected knowledge base.
        """
        kb_id = knowledge_base_id or self.knowledge_base_id

        if kb_id is None:
            return {"error": "未指定知识库ID，无法读取分块。"}

        if not chunk_id or not isinstance(chunk_id, str):
            return {"error": "chunk_id 参数无效。"}

        try:
            from ..vectorstore.milvus_store import get_chunk_detail

            detail = get_chunk_detail(chunk_id)
            if detail is None:
                return {"error": f"未找到分块 {chunk_id}。"}

            # Scope enforcement: the chunk must belong to the selected KB.
            chunk_kb_id = detail.get("knowledge_base_id")
            if chunk_kb_id is not None and int(chunk_kb_id) != int(kb_id):
                return {"error": f"分块 {chunk_id} 不属于当前知识库。"}

            metadata = detail.get("metadata")
            if isinstance(metadata, str):
                import json
                try:
                    metadata = json.loads(metadata)
                except (json.JSONDecodeError, TypeError):
                    metadata = {}

            title = ""
            if isinstance(metadata, dict):
                title = metadata.get("document_title", "")

            return {
                "chunk_id": detail.get("chunk_id", chunk_id),
                "content": detail.get("content", ""),
                "document_id": detail.get("document_id"),
                "title": title,
                "block_type": detail.get("block_type"),
                "metadata": metadata or {},
            }

        except Exception as e:
            return {"error": f"读取分块失败: {str(e)}"}
