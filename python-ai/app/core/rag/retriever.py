"""
Multi-Channel Retriever - 多通道检索器
参考 Ragent 项目的 Multi-Channel Retrieval 设计

功能:
1. 向量检索 - Milvus 语义相似度搜索
2. 关键词检索 - 预留 ES 接口
3. 图谱检索 - 预留 GraphRAG 接口
"""

import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field

from .query_rewriter import QueryRewriter, get_query_rewriter, RewriteResult
from .postprocessor import Postprocessor, get_postprocessor, ProcessedResult

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """检索结果"""
    query: str
    results: List[ProcessedResult]
    rewrite_result: Optional[RewriteResult] = None
    metadata: Dict = field(default_factory=dict)


class VectorChannel:
    """向量检索通道"""

    def __init__(self):
        self._store = None

    def _get_store(self):
        if self._store is None:
            from app.core.vectorstore.milvus_store import search_similar
            self._store = search_similar
        return self._store

    def search(
        self,
        query: str,
        knowledge_base_id: Optional[int] = None,
        top_k: int = 10
    ) -> List[Dict]:
        """
        向量检索

        Args:
            query: 查询文本
            knowledge_base_id: 知识库 ID
            top_k: 返回数量

        Returns:
            检索结果列表
        """
        try:
            search_fn = self._get_store()
            results = search_fn(
                query_text=query,
                top_k=top_k,
                knowledge_base_id=knowledge_base_id
            )

            # 标记来源
            for r in results:
                r["source"] = "vector"

            logger.info(f"Vector search: {len(results)} results for '{query[:30]}...'")
            return results

        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []


class KeywordChannel:
    """关键词检索通道（预留 ES 接口）"""

    def search(
        self,
        query: str,
        knowledge_base_id: Optional[int] = None,
        top_k: int = 10
    ) -> List[Dict]:
        """
        关键词检索（预留实现）

        TODO: 集成 Elasticsearch
        """
        # 预留接口，暂返回空
        logger.info("Keyword search not implemented yet")
        return []


class GraphChannel:
    """图谱检索通道（预留 GraphRAG 接口）"""

    def search(
        self,
        query: str,
        knowledge_base_id: Optional[int] = None,
        top_k: int = 10
    ) -> List[Dict]:
        """
        图谱检索（预留实现）

        TODO: 集成 GraphRAG / Neo4j
        """
        # 预留接口，暂返回空
        logger.info("Graph search not implemented yet")
        return []


class MultiChannelRetriever:
    """多通道检索器"""

    def __init__(
        self,
        query_rewriter: Optional[QueryRewriter] = None,
        postprocessor: Optional[Postprocessor] = None
    ):
        """
        初始化多通道检索器

        Args:
            query_rewriter: 问题重写器
            postprocessor: 后处理器
        """
        self.query_rewriter = query_rewriter or get_query_rewriter()
        self.postprocessor = postprocessor or get_postprocessor()

        # 初始化各通道
        self.vector_channel = VectorChannel()
        self.keyword_channel = KeywordChannel()
        self.graph_channel = GraphChannel()

    def retrieve(
        self,
        query: str,
        knowledge_base_id: Optional[int] = None,
        conversation_history: Optional[List[Dict]] = None,
        top_k: int = 5,
        enable_rewrite: bool = True
    ) -> RetrievalResult:
        """
        多通道检索

        Args:
            query: 用户查询
            knowledge_base_id: 知识库 ID
            conversation_history: 对话历史
            top_k: 返回数量
            enable_rewrite: 是否启用问题重写

        Returns:
            RetrievalResult 检索结果
        """
        rewrite_result = None

        # 1. 问题重写
        if enable_rewrite and conversation_history:
            rewrite_result = self.query_rewriter.rewrite(
                query,
                conversation_history
            )
            queries = rewrite_result.rewritten_queries
        else:
            queries = [query]

        # 2. 多通道并行检索
        all_results = []

        for q in queries:
            # 向量检索
            vector_results = self.vector_channel.search(
                q,
                knowledge_base_id=knowledge_base_id,
                top_k=top_k
            )

            # 关键词检索（预留）
            keyword_results = self.keyword_channel.search(
                q,
                knowledge_base_id=knowledge_base_id,
                top_k=top_k
            )

            # 图谱检索（预留）
            graph_results = self.graph_channel.search(
                q,
                knowledge_base_id=knowledge_base_id,
                top_k=top_k
            )

            # 合并结果
            merged = self.postprocessor.merge_results(
                vector_results=vector_results,
                keyword_results=keyword_results,
                graph_results=graph_results
            )

            all_results.extend(merged)

        # 3. 后处理（去重、排序）
        processed = self.postprocessor.process(all_results, top_k=top_k)

        # 4. 构建结果
        result = RetrievalResult(
            query=query,
            results=processed,
            rewrite_result=rewrite_result,
            metadata={
                "knowledge_base_id": knowledge_base_id,
                "query_count": len(queries),
                "total_results": len(all_results)
            }
        )

        logger.info(
            f"Retrieved {len(processed)} results for '{query[:30]}...' "
            f"(queries: {len(queries)}, total: {len(all_results)})"
        )

        return result

    def retrieve_for_prompt(
        self,
        query: str,
        knowledge_base_id: Optional[int] = None,
        conversation_history: Optional[List[Dict]] = None,
        top_k: int = 3
    ) -> str:
        """
        检索并格式化为 Prompt

        Args:
            query: 用户查询
            knowledge_base_id: 知识库 ID
            conversation_history: 对话历史
            top_k: 返回数量

        Returns:
            格式化的上下文文本
        """
        result = self.retrieve(
            query=query,
            knowledge_base_id=knowledge_base_id,
            conversation_history=conversation_history,
            top_k=top_k
        )

        if not result.results:
            return ""

        # 格式化为上下文
        context_parts = []
        for i, r in enumerate(result.results, 1):
            source_label = {
                "vector": "语义匹配",
                "keyword": "关键词匹配",
                "graph": "知识图谱"
            }.get(r.source, "检索")

            context_parts.append(
                f"[{i}] ({source_label}, 相似度: {r.score:.2f})\n{r.content}"
            )

        return "\n\n".join(context_parts)


# 全局实例
_retriever: Optional[MultiChannelRetriever] = None


def get_retriever() -> MultiChannelRetriever:
    """获取全局检索器"""
    global _retriever
    if _retriever is None:
        _retriever = MultiChannelRetriever()
    return _retriever
