"""
Multi-Channel Retriever - 多通道检索器
参考 Ragent 项目的 Multi-Channel Retrieval 设计

通过 QueryRouter 路由到向量、关键词和知识图谱检索通道。
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.utils.config import config

from app.core.security.clearance import build_acl_metadata_filter, get_clearance

from .observability import RetrievalTrace, get_trace_store
from .postprocessor import Postprocessor, ProcessedResult, get_postprocessor
from .query_rewriter import QueryRewriter, RewriteResult, get_query_rewriter
from .query_router import QueryRouter, get_router
from .reranker import Reranker, get_reranker

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """检索结果"""
    query: str
    results: list[ProcessedResult]
    rewrite_result: RewriteResult | None = None
    metadata: dict = field(default_factory=dict)


class MultiChannelRetriever:
    """多通道检索器"""

    def __init__(
        self,
        query_rewriter: QueryRewriter | None = None,
        postprocessor: Postprocessor | None = None,
        reranker: Reranker | None = None,
    ):
        """
        初始化多通道检索器

        Args:
            query_rewriter: 问题重写器
            postprocessor: 后处理器
        """
        self.query_rewriter = query_rewriter or get_query_rewriter()
        self.postprocessor = postprocessor or get_postprocessor()
        self._dynamic_reranker = reranker is None
        self.reranker = reranker or get_reranker()
        self.router: QueryRouter = get_router()

    async def retrieve(
        self,
        query: str,
        knowledge_base_id: int | None = None,
        conversation_history: list[dict] | None = None,
        top_k: int = 5,
        enable_rewrite: bool = True,
        metadata_filter: dict[str, Any] | None = None,
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
        started_at = time.perf_counter()
        # 主体级 ACL：按请求主体 clearance 过滤文档可见性。ACL 过滤器叠加在
        # 调用方显式 filter 之上（visibility 键以 ACL 为准，调用方无法放宽）；
        # 未设置 clearance 时按最低权限 general 处理（fail-closed）。
        acl_filter = build_acl_metadata_filter(get_clearance())
        effective_filter: dict[str, Any] | None = None
        if metadata_filter or acl_filter:
            effective_filter = {**(metadata_filter or {}), **(acl_filter or {})}
        rewrite_result = None
        routes: list[dict[str, Any]] = []
        processed: list[ProcessedResult] = []
        queries = [query]
        channel_candidates: list[dict[str, Any]] = []
        postprocessing: list[dict[str, Any]] = []
        stage_timings_ms: dict[str, float] = {}
        rerank_debug: dict[str, Any] = {"applied": False, "reranker": "not_started"}
        error: str | None = None

        try:
            # 1. 问题重写
            if enable_rewrite and conversation_history:
                rewrite_started_at = time.perf_counter()
                rewrite_result = self.query_rewriter.rewrite(query, conversation_history)
                queries = rewrite_result.rewritten_queries or [query]
                stage_timings_ms["rewrite"] = round(
                    (time.perf_counter() - rewrite_started_at) * 1000, 2
                )

            # 2. 路由到向量、关键词或图谱通道。
            all_results = []
            candidate_top_k = top_k
            if self.reranker.name != "disabled":
                candidate_top_k = max(top_k, config.RAG_RERANK_CANDIDATE_COUNT)
            for rewritten_query in queries:
                router_started_at = time.perf_counter()
                merged = await self.router.search(
                    query=rewritten_query,
                    knowledge_base_id=knowledge_base_id,
                    top_k=candidate_top_k,
                    metadata_filter=effective_filter,
                )
                route = merged.metadata.get("route_result", {})
                routes.append({
                    "query": rewritten_query,
                    **route,
                    "router_latency_ms": merged.metadata.get("router_latency_ms"),
                    "channel_latencies_ms": merged.metadata.get("channel_latencies_ms", {}),
                })
                channel_candidates.append({
                    "query": rewritten_query,
                    "candidates": merged.metadata.get("channel_candidates", {}),
                })
                stage_timings_ms["router"] = round(
                    stage_timings_ms.get("router", 0.0)
                    + (time.perf_counter() - router_started_at) * 1000,
                    2,
                )
                all_results.extend({
                    "content": item.content,
                    "score": item.score,
                    "document_id": item.document_id,
                    "knowledge_base_id": item.metadata.get("knowledge_base_id", knowledge_base_id),
                    "outline_path": item.metadata.get("outline_path", []),
                    "source": item.source.value,
                    "metadata": item.metadata,
                } for item in merged.results)

            # 3. Optional second-stage reranking. A disabled or unavailable
            # model leaves the first-stage order intact and records why.
            rerank_started_at = time.perf_counter()
            # Resolve the runtime switch for every retrieval. Configured
            # implementations are cached by the factory.
            active_reranker = get_reranker() if self._dynamic_reranker else self.reranker
            all_results, rerank_debug = await active_reranker.rerank(query, all_results)
            stage_timings_ms["rerank"] = round(
                (time.perf_counter() - rerank_started_at) * 1000, 2
            )

            # 4. 后处理（去重、排序）
            postprocess_started_at = time.perf_counter()
            route_is_scoped_summary = any(
                route.get("query_type") == "summary"
                for route in routes
            ) and knowledge_base_id is not None
            processed, postprocessing = self.postprocessor.process_with_debug(
                all_results,
                top_k=top_k,
                query=query,
                allow_scoped_summary=route_is_scoped_summary,
            )
            stage_timings_ms["postprocess"] = round(
                (time.perf_counter() - postprocess_started_at) * 1000, 2
            )
            result = RetrievalResult(
                query=query,
                results=processed,
                rewrite_result=rewrite_result,
                metadata={
                    "knowledge_base_id": knowledge_base_id,
                    "query_count": len(queries),
                    "total_results": len(all_results),
                    "rewritten_queries": queries,
                    "reranker": rerank_debug,
                },
            )
            logger.info(
                f"Retrieved {len(processed)} results for '{query[:30]}...' "
                f"(queries: {len(queries)}, total: {len(all_results)})"
            )
            return result
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            trace_results = [
                {
                    "document_id": result.document_id,
                    "score": round(result.score, 4),
                    "source": result.source,
                    "content_preview": result.content[:500],
                    "outline_path": result.outline_path,
                }
                for result in processed
            ]
            trace = get_trace_store().record(RetrievalTrace(
                query=query,
                knowledge_base_id=knowledge_base_id,
                top_k=top_k,
                routes=routes,
                results=trace_results,
                debug={
                    "rewritten_queries": queries,
                    "channel_candidates": channel_candidates,
                    "postprocessing": postprocessing,
                    "stage_timings_ms": stage_timings_ms,
                    "reranker": rerank_debug,
                },
                rewrite_count=len(queries),
                latency_ms=round((time.perf_counter() - started_at) * 1000, 2),
                error=error,
            ))
            if 'result' in locals():
                result.metadata["trace_id"] = trace.trace_id

    async def retrieve_for_prompt(
        self,
        query: str,
        knowledge_base_id: int | None = None,
        conversation_history: list[dict] | None = None,
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
        result = await self.retrieve(
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
_retriever: MultiChannelRetriever | None = None


def get_retriever() -> MultiChannelRetriever:
    """获取全局检索器"""
    global _retriever
    if _retriever is None:
        _retriever = MultiChannelRetriever()
    return _retriever
