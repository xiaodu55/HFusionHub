"""
RAG Module - 检索增强生成模块
参考 Ragent 项目的架构设计

组件:
- QueryRewriter: 问题重写器
- MultiChannelRetriever: 多通道检索器
- Postprocessor: 后处理器
"""

from .query_rewriter import QueryRewriter, get_query_rewriter, RewriteResult
from .retriever import MultiChannelRetriever, get_retriever, RetrievalResult
from .postprocessor import Postprocessor, get_postprocessor, ProcessedResult

__all__ = [
    "QueryRewriter",
    "get_query_rewriter",
    "RewriteResult",
    "MultiChannelRetriever",
    "get_retriever",
    "RetrievalResult",
    "Postprocessor",
    "get_postprocessor",
    "ProcessedResult",
]
