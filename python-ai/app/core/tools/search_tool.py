"""
Search Tool - Search knowledge base documents
"""

from typing import Any

from .base import BaseTool


class SearchTool(BaseTool):
    """Search tool for knowledge base"""

    def __init__(self, knowledge_base_id: int = None):
        self.knowledge_base_id = knowledge_base_id

    async def execute(
        self,
        query: str,
        top_k: int = 5,
        knowledge_base_id: int = None,
        metadata_filter: dict[str, Any] = None,
        **kwargs
    ) -> list[dict[str, Any]]:
        """
        Search knowledge base

        Args:
            query: Search query text
            top_k: Number of results to return
            knowledge_base_id: Override knowledge base ID
            metadata_filter: Optional {field: value} equality filter on chunk
                metadata (Batch 5)

        Returns:
            List of search results with source information
        """
        # Use provided knowledge_base_id or default
        kb_id = knowledge_base_id or self.knowledge_base_id

        if kb_id is None:
            return [{"error": "未指定知识库ID"}]

        try:
            # Import here to avoid circular imports
            from ..vectorstore.milvus_store import search_similar

            # Search similar chunks
            results = search_similar(
                query_text=query,
                top_k=top_k,
                knowledge_base_id=kb_id,
                metadata_filter=metadata_filter,
            )

            # Format results with source information
            formatted_results = []
            for result in results:
                document_id = result.get("document_id")

                # The title is persisted with the vector chunk at indexing
                # time.  Avoid an unauthenticated Python -> Java lookup that
                # could bypass document ownership checks.
                metadata = result.get("metadata") or {}
                document_name = metadata.get("document_title") or f"文档-{document_id}"

                formatted_results.append({
                    "content": result.get("content", ""),
                    "score": result.get("score", 0),
                    "document_id": document_id,
                    "document_name": document_name,
                    "knowledge_base_id": result.get("knowledge_base_id"),
                    "outline_path": result.get("outline_path", []),
                    "source": f"{document_name}"
                })

            return formatted_results

        except Exception as e:
            return [{"error": f"搜索失败: {str(e)}"}]
