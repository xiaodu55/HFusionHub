"""
List Document Chunks Tool — List all chunk summaries for a document.

Agent V1 whitelisted tool.  Returns an excerpt (first 200 chars) per chunk
without the full content, so the agent can decide which chunks to deep-read.
"""

from typing import Any

from .base import BaseTool

# Safety cap: prevent returning thousands of chunk summaries in one call.
_MAX_CHUNKS = 100


class ListDocumentChunksTool(BaseTool):
    """List all chunk summaries (excerpts) for a single document."""

    def __init__(self, knowledge_base_id: int | None = None):
        self.knowledge_base_id = knowledge_base_id

    async def execute(
        self,
        document_id: int,
        knowledge_base_id: int | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        List chunk summaries for a document.

        Args:
            document_id: The numeric document ID in MySQL.
            knowledge_base_id: Must match the selected knowledge base.

        Returns:
            Dict with ``chunks`` (list of {chunk_id, excerpt, block_type})
            and ``truncated`` (bool) when the result exceeds the 100-chunk cap.
        """
        kb_id = knowledge_base_id or self.knowledge_base_id

        if kb_id is None:
            return {"error": "未指定知识库ID，无法列出分块。"}

        if not document_id:
            return {"error": "document_id 参数无效。"}

        try:
            from ..security.clearance import subject_can_see_metadata
            from ..vectorstore.milvus_store import get_document_chunks

            # The local store returns paginated results.  Fetch all pages up to
            # the safety cap.
            all_chunks: list[dict[str, Any]] = []
            page = 1
            while len(all_chunks) < _MAX_CHUNKS:
                result = get_document_chunks(
                    document_id=str(document_id),
                    page=page,
                    size=50,
                )
                if result.get("code") != 200:
                    break
                records = result.get("data", {}).get("records", [])
                if not records:
                    break
                for r in records:
                    # Enforce knowledge-base scope.
                    r_kb = r.get("knowledge_base_id")
                    if r_kb is None:
                        return {"error": "chunk has no knowledge-base scope"}
                    if int(r_kb) != int(kb_id):
                        continue
                    # ACL enforcement: 与检索同规则——高可见性分块对当前主体
                    # 不存在（摘要也属内容泄露面）。
                    if not subject_can_see_metadata(r.get("metadata")):
                        continue
                    content = r.get("content", "")
                    all_chunks.append({
                        "chunk_id": r.get("chunk_id"),
                        "excerpt": content[:200] if content else "",
                        "block_type": r.get("block_type"),
                    })
                    if len(all_chunks) >= _MAX_CHUNKS:
                        break
                page += 1

            return {
                "document_id": document_id,
                "chunks": all_chunks,
                "total": len(all_chunks),
                "truncated": len(all_chunks) >= _MAX_CHUNKS,
            }

        except Exception as e:
            return {"error": f"列出文档分块失败: {str(e)}"}
