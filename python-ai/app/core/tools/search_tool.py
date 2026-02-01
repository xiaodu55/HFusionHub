"""
Search Tool - Search knowledge base documents
"""

from typing import Any, Dict, List, Optional

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
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Search knowledge base

        Args:
            query: Search query text
            top_k: Number of results to return
            knowledge_base_id: Override knowledge base ID

        Returns:
            List of search results
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
                collection_name="hfusionhub_chunks",
                query_text=query,
                top_k=top_k,
                knowledge_base_id=kb_id
            )

            # Format results
            formatted_results = []
            for result in results:
                formatted_results.append({
                    "content": result.get("text", ""),
                    "score": result.get("score", 0),
                    "document_id": result.get("document_id"),
                    "outline_path": result.get("outline_path", [])
                })

            return formatted_results

        except Exception as e:
            return [{"error": f"搜索失败: {str(e)}"}]
