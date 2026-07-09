# Copyright (c) 2026 HFusionHub. All rights reserved.
"""
查询路由器模块 - 智能选择检索通道

参考项目：
- Ragent: 意图分析、多轮检索策略
- LangGraph: 状态机、多 Agent 协作
- LlamaIndex: 子问题分解、查询引擎

设计模式：
- 枚举模式: ChannelType, RouteStrategy - 类型安全的枚举定义
- 策略模式: 多种路由策略，运行时可切换
- 工厂模式: QueryRouterFactory - 统一路由器创建
- 单例模式: 全局唯一路由器实例
- 责任链模式: 多个通道按权重执行
"""

import asyncio
import math
import re
import time
import logging
from collections import defaultdict
from enum import Enum
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field

from .utils import (
    DEFAULT_CHANNEL_WEIGHT,
    ADAPTIVE_THRESHOLD,
    WEIGHT_MAX_VALUE,
    WEIGHT_MIN_VALUE,
    TIMEOUT_MIN_VALUE,
    CONFIDENCE_BASE_SCORE,
    CONFIDENCE_MAX_SCORE,
    CONFIDENCE_WEIGHT_FACTOR,
    ENTITY_MATCH_BASE_SCORE,
    NEIGHBOR_RELATION_SCORE,
)
from app.utils.config import config as app_config
from app.utils.feature_flag import feature_flags
from app.core.vectorstore.milvus_store import _matches_metadata_filter

logger = logging.getLogger(__name__)


# =============================================================================
# 枚举定义
# =============================================================================

class ChannelType(str, Enum):
    """检索通道类型"""
    VECTOR = "vector"          # 向量检索
    KEYWORD = "keyword"        # 关键词检索
    HYBRID = "hybrid"         # 混合检索


class RouteStrategy(str, Enum):
    """路由策略"""
    SINGLE = "single"         # 单通道
    MULTI = "multi"          # 多通道并行
    CASCADING = "cascading"  # 级联检索
    ADAPTIVE = "adaptive"    # 自适应


class QueryType(str, Enum):
    """查询类型"""
    FACTUAL = "factual"           # 事实查询
    COMPARISON = "comparison"     # 比较分析
    SUMMARY = "summary"          # 总结归纳
    ENTITY = "entity"            # 实体查询
    RELATIONSHIP = "relationship" # 关系查询
    GENERAL = "general"          # 通用查询


# =============================================================================
# 数据模型
# =============================================================================

@dataclass
class ChannelConfig:
    """通道配置"""
    channel_type: ChannelType
    weight: float = 1.0
    enabled: bool = True
    timeout: float = 10.0
    max_results: int = 10
    params: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not WEIGHT_MIN_VALUE <= self.weight <= WEIGHT_MAX_VALUE:
            raise ValueError(f"weight must be between {WEIGHT_MIN_VALUE} and {WEIGHT_MAX_VALUE}")
        if self.timeout <= TIMEOUT_MIN_VALUE:
            raise ValueError(f"timeout must be positive (>{TIMEOUT_MIN_VALUE})")


@dataclass
class RouteResult:
    """路由结果"""
    query_type: QueryType
    selected_channels: List[ChannelType]
    channel_weights: Dict[ChannelType, float]
    strategy: RouteStrategy
    confidence: float = 0.0
    reasoning: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """检索结果"""
    content: str
    score: float
    source: ChannelType
    document_id: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MergedResult:
    """合并后的结果"""
    results: List[SearchResult]
    total_count: int
    channels_used: List[ChannelType]
    merge_strategy: str = "score_based"
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# 通道抽象基类
# =============================================================================

class BaseChannel:
    """通道基类"""

    def __init__(self, config: ChannelConfig):
        self.config = config

    async def search(
        self,
        query: str,
        knowledge_base_id: int,
        top_k: int = 10,
        **kwargs
    ) -> List[SearchResult]:
        """执行检索"""
        raise NotImplementedError


class VectorChannel(BaseChannel):
    """向量检索通道"""

    async def search(
        self,
        query: str,
        knowledge_base_id: int,
        top_k: int = 10,
        metadata_filter: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[SearchResult]:
        """向量检索（兼容 Milvus Lite 的同步搜索接口）"""
        try:
            from app.core.vectorstore.milvus_store import search_similar

            # Milvus Lite 的客户端为同步接口；转到线程中，避免阻塞 FastAPI 事件循环。
            results = await asyncio.to_thread(
                search_similar,
                query_text=query,
                knowledge_base_id=knowledge_base_id,
                top_k=top_k,
                metadata_filter=metadata_filter,
            )

            return [
                SearchResult(
                    content=r.get("content", ""),
                    score=r.get("score", 0.0),
                    source=ChannelType.VECTOR,
                    document_id=r.get("document_id"),
                    metadata={
                        **(r.get("metadata") or {}),
                        "chunk_id": r.get("chunk_id"),
                        "knowledge_base_id": r.get("knowledge_base_id"),
                        "outline_path": r.get("outline_path", []),
                    }
                )
                for r in results
            ]
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []


class KeywordChannel(BaseChannel):
    """知识库范围内的 BM25 关键词检索通道。

    The document ingestion path already maintains ``chunks_store.json`` for
    local development. Building BM25 from that scoped corpus means the first
    hybrid-retrieval release has no Elasticsearch dependency and, crucially,
    applies exactly the same knowledge-base boundary as vector retrieval.

    The expensive parts of BM25 — reading the corpus, tokenising every chunk,
    and building the term→document inverted index — are cached per
    ``(store, knowledge_base_id)`` so repeated queries do not re-parse the
    whole corpus on every request.
    """

    # 语料缓存：key = (id(store), knowledge_base_id)。value 同时持有 store
    # 引用，防止其被 GC 后 id() 复用导致误命中。store 内容变化（文件 mtime
    # 变化）会使 _load_chunks_store 返回新 dict → id 变化 → 缓存自动失效。
    _corpus_cache: Dict[Tuple[int, int], Tuple[Dict, "_KeywordCorpus"]] = {}
    _CORPUS_CACHE_MAX = 16

    @dataclass
    class _KeywordCorpus:
        """预解析后的 BM25 语料（一次构建、多次查询复用）。"""
        documents: List[Tuple[str, Dict, List[str]]]          # (document_id, chunk, tokens)
        chunks_by_document: Dict[str, List[Dict]]              # 全量按文档分组排序
        token_to_doc_idx: Dict[str, Set[int]]                  # term → 文档索引（df 来源）
        average_length: float

    @classmethod
    def _corpus_for(cls, store: Dict[str, List[Dict]], knowledge_base_id: Optional[int]) -> "_KeywordCorpus":
        key = (id(store), knowledge_base_id)
        cached = cls._corpus_cache.get(key)
        if cached is not None and cached[0] is store:
            return cached[1]
        documents: List[Tuple[str, Dict, List[str]]] = []
        token_to_doc_idx: Dict[str, Set[int]] = defaultdict(set)
        for document_id, chunks in store.items():
            for chunk in chunks:
                if (knowledge_base_id is not None and
                        chunk.get("knowledge_base_id") != knowledge_base_id):
                    continue
                content = chunk.get("content", "")
                tokens = cls._tokenize(content)
                if content and tokens:
                    index = len(documents)
                    documents.append((document_id, chunk, tokens))
                    for term in set(tokens):
                        token_to_doc_idx[term].add(index)
        chunks_by_document = {
            str(document_id): sorted(chunks, key=cls._chunk_order)
            for document_id, chunks in store.items()
        }
        average_length = (
            sum(len(tokens) for _, _, tokens in documents) / len(documents)
            if documents else 0.0
        )
        corpus = cls._KeywordCorpus(
            documents=documents,
            chunks_by_document=chunks_by_document,
            token_to_doc_idx=dict(token_to_doc_idx),
            average_length=average_length,
        )
        cls._corpus_cache[key] = (store, corpus)
        if len(cls._corpus_cache) > cls._CORPUS_CACHE_MAX:
            # Evict oldest by insertion order (dict preserves it).
            cls._corpus_cache.pop(next(iter(cls._corpus_cache)))
        return corpus

    async def search(
        self,
        query: str,
        knowledge_base_id: int,
        top_k: int = 10,
        metadata_filter: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[SearchResult]:
        """Return normalized BM25 candidates from the scoped local corpus."""
        try:
            from app.core.vectorstore.milvus_store import _load_chunks_store

            store = await asyncio.to_thread(_load_chunks_store)
            terms = self._tokenize(query)
            if not terms:
                return []

            # 复用预解析语料（分词 + 倒排索引 + 文档分组），避免每次查询
            # 重读整个 corpus + 全量重分词。
            corpus = self._corpus_for(store, knowledge_base_id)
            documents = corpus.documents
            if not documents:
                return []

            chunks_by_document = corpus.chunks_by_document

            document_frequency = {
                term: len(corpus.token_to_doc_idx.get(term, ()))
                for term in terms
            }
            average_length = corpus.average_length
            scored: List[Tuple[float, str, Dict]] = []
            for document_id, chunk, tokens in documents:
                # 元数据过滤（Batch 5）：与向量通道同一谓词语义
                if metadata_filter and not _matches_metadata_filter(
                        chunk.get("metadata"), metadata_filter):
                    continue
                raw_score = self._bm25_score(
                    terms=terms,
                    tokens=tokens,
                    document_frequency=document_frequency,
                    document_count=len(documents),
                    average_length=average_length,
                )
                if raw_score > 0:
                    scored.append((raw_score, document_id, chunk))

            if not scored:
                return []

            max_score = max(score for score, _, _ in scored)
            results: List[SearchResult] = []
            for raw_score, document_id, chunk in sorted(scored, reverse=True, key=lambda item: item[0])[:top_k]:
                content = chunk.get("content", "")
                content, neighbor_chunk_ids = self._expand_heading_context(
                    chunk,
                    chunks_by_document.get(str(document_id), []),
                    knowledge_base_id,
                )
                content_tokens = self._tokenize(content)
                matched_terms = [term for term in terms if term in content_tokens]
                # BM25 is only comparable within this one corpus. Combine its
                # local normalization with term coverage so a document that
                # happens to match one character of a multi-term query does
                # not satisfy the evidence threshold by itself.
                score = (raw_score / max_score) * (len(matched_terms) / len(terms))
                metadata = self._metadata(chunk.get("metadata"))
                outline_path = self._outline_path(chunk.get("outline_path"))
                results.append(SearchResult(
                    content=content,
                    score=score,
                    source=ChannelType.KEYWORD,
                    document_id=chunk.get("document_id", document_id),
                    metadata={
                        **metadata,
                        "chunk_id": chunk.get("chunk_id"),
                        "knowledge_base_id": chunk.get("knowledge_base_id"),
                        "outline_path": outline_path,
                        "match_terms": matched_terms,
                        "keyword_coverage": len(matched_terms) / len(terms),
                        "bm25_score": raw_score,
                        "expanded_from_heading": bool(neighbor_chunk_ids),
                        "neighbor_chunk_ids": neighbor_chunk_ids,
                    },
                ))
            return results
        except Exception as e:
            logger.error("Keyword search failed: %s", e)
            return []

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """提取英文词、数字和单个中文字符，适配中英文混合文档。"""
        tokens = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text.lower())
        return list(dict.fromkeys(token for token in tokens if len(token) > 1 or "\u4e00" <= token <= "\u9fff"))

    @staticmethod
    def _bm25_score(
        terms: List[str],
        tokens: List[str],
        document_frequency: Dict[str, int],
        document_count: int,
        average_length: float,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> float:
        """Calculate BM25 without a runtime dependency on Elasticsearch."""
        if not tokens or not average_length:
            return 0.0
        score = 0.0
        length_normalizer = k1 * (1 - b + b * len(tokens) / average_length)
        for term in terms:
            frequency = tokens.count(term)
            if not frequency:
                continue
            df = document_frequency.get(term, 0)
            idf = math.log(1 + (document_count - df + 0.5) / (df + 0.5))
            score += idf * (frequency * (k1 + 1)) / (frequency + length_normalizer)
        return score

    @staticmethod
    def _metadata(value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                import json
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except (TypeError, ValueError):
                return {}
        return {}

    @staticmethod
    def _outline_path(value: Any) -> List[str]:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                import json
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except (TypeError, ValueError):
                return []
        return []

    @staticmethod
    def _chunk_order(chunk: Dict[str, Any]) -> int:
        """Return a stable document-local order for JSON and cluster stores."""
        explicit_index = chunk.get("chunk_index")
        if isinstance(explicit_index, int):
            return explicit_index

        match = re.search(r"(?:_|-)(\d+)$", str(chunk.get("chunk_id", "")))
        return int(match.group(1)) if match else 2**31 - 1

    @classmethod
    def _expand_heading_context(
        cls,
        heading: Dict[str, Any],
        document_chunks: List[Dict[str, Any]],
        knowledge_base_id: Optional[int],
        max_neighbors: int = 2,
        max_chars: int = 1200,
    ) -> Tuple[str, List[str]]:
        """Attach the paragraph/list/code blocks immediately under a heading."""
        content = heading.get("content", "") or ""
        if str(heading.get("block_type", "")).upper() != "HEADING":
            return content, []

        heading_id = str(heading.get("chunk_id", ""))
        heading_position = next(
            (
                index
                for index, chunk in enumerate(document_chunks)
                if str(chunk.get("chunk_id", "")) == heading_id
            ),
            None,
        )
        if heading_position is None:
            return content, []

        parts = [content]
        neighbor_ids: List[str] = []
        for neighbor in document_chunks[heading_position + 1:]:
            if (
                knowledge_base_id is not None
                and neighbor.get("knowledge_base_id") != knowledge_base_id
            ):
                continue
            if str(neighbor.get("block_type", "")).upper() == "HEADING":
                break

            neighbor_content = (neighbor.get("content", "") or "").strip()
            if not neighbor_content:
                continue
            if len("\n\n".join(parts)) + len(neighbor_content) > max_chars:
                break

            parts.append(neighbor_content)
            neighbor_ids.append(str(neighbor.get("chunk_id", "")))
            if len(neighbor_ids) >= max_neighbors:
                break

        return "\n\n".join(parts), neighbor_ids


# =============================================================================
# 查询路由器
# =============================================================================

class QueryRouter:
    """查询路由器 - 智能选择检索通道"""

    def __init__(
        self,
        channels: Optional[Dict[ChannelType, BaseChannel]] = None,
        rrf_k: Optional[int] = None,
        candidate_multiplier: Optional[int] = None,
        max_candidates: Optional[int] = None,
    ):
        self.rrf_k = rrf_k if rrf_k is not None else app_config.RAG_RRF_K
        self.candidate_multiplier = (
            candidate_multiplier
            if candidate_multiplier is not None
            else app_config.RAG_RETRIEVAL_CANDIDATE_MULTIPLIER
        )
        self.max_candidates = (
            max_candidates
            if max_candidates is not None
            else app_config.RAG_RETRIEVAL_MAX_CANDIDATES
        )
        if self.rrf_k < 1:
            raise ValueError("rrf_k must be positive")
        if self.candidate_multiplier < 1 or self.max_candidates < 1:
            raise ValueError("candidate limits must be positive")
        # 默认通道配置
        self.channel_configs: Dict[ChannelType, ChannelConfig] = {
            ChannelType.VECTOR: ChannelConfig(
                channel_type=ChannelType.VECTOR,
                weight=DEFAULT_CHANNEL_WEIGHT
            ),
            ChannelType.KEYWORD: ChannelConfig(
                channel_type=ChannelType.KEYWORD,
                weight=DEFAULT_CHANNEL_WEIGHT * 0.5,
                enabled=feature_flags.is_enabled("rag.hybrid.enabled"),
            ),
        }

        # 通道实例
        self.channels = channels or {
            ChannelType.VECTOR: VectorChannel(self.channel_configs[ChannelType.VECTOR]),
            ChannelType.KEYWORD: KeywordChannel(self.channel_configs[ChannelType.KEYWORD]),
        }

        # 查询类型与通道权重映射
        self._channel_weights: Dict[QueryType, Dict[ChannelType, float]] = {
            QueryType.FACTUAL: {
                ChannelType.VECTOR: 0.7,
                ChannelType.KEYWORD: 0.3,
            },
            QueryType.COMPARISON: {
                ChannelType.VECTOR: 0.8,
                ChannelType.KEYWORD: 0.1,
            },
            QueryType.SUMMARY: {
                ChannelType.VECTOR: 0.6,
                ChannelType.KEYWORD: 0.2,
            },
            QueryType.ENTITY: {
                ChannelType.VECTOR: 0.3,
                ChannelType.KEYWORD: 0.4,
            },
            QueryType.RELATIONSHIP: {
                ChannelType.VECTOR: 0.2,
                ChannelType.KEYWORD: 0.2,
            },
            QueryType.GENERAL: {
                ChannelType.VECTOR: 0.6,
                ChannelType.KEYWORD: 0.3,
            },
        }

        # 路由策略映射
        self._strategy_map: Dict[QueryType, RouteStrategy] = {
            QueryType.FACTUAL: RouteStrategy.MULTI,
            QueryType.COMPARISON: RouteStrategy.MULTI,
            QueryType.SUMMARY: RouteStrategy.MULTI,
            QueryType.ENTITY: RouteStrategy.CASCADING,
            QueryType.RELATIONSHIP: RouteStrategy.SINGLE,
            QueryType.GENERAL: RouteStrategy.ADAPTIVE,
        }

        logger.info("QueryRouter initialized")

    def classify_query(self, query: str) -> QueryType:
        """
        分类查询类型

        使用规则和关键词匹配进行快速分类
        """
        query_lower = query.lower()

        # 比较类关键词
        comparison_keywords = ["比较", "对比", "区别", "差异", "不同", "vs", "versus", "和.*哪个"]
        if any(kw in query_lower for kw in comparison_keywords):
            return QueryType.COMPARISON

        # 总结类关键词
        summary_keywords = ["总结", "概括", "归纳", "摘要", "简述"]
        if any(kw in query_lower for kw in summary_keywords):
            return QueryType.SUMMARY

        # 实体查询关键词
        entity_keywords = ["是谁", "是什么", "什么是", "定义", "概念"]
        if any(kw in query_lower for kw in entity_keywords):
            return QueryType.ENTITY

        # 关系查询关键词
        relationship_keywords = ["关系", "联系", "关联", "如何.*相关", "之间"]
        if any(kw in query_lower for kw in relationship_keywords):
            return QueryType.RELATIONSHIP

        # 事实查询关键词
        factual_keywords = ["多少", "何时", "哪里", "哪个", "是否", "有没有"]
        if any(kw in query_lower for kw in factual_keywords):
            return QueryType.FACTUAL

        return QueryType.GENERAL

    def route(
        self,
        query: str,
        query_type: Optional[QueryType] = None,
        strategy: Optional[RouteStrategy] = None
    ) -> RouteResult:
        """
        根据查询选择检索通道

        Args:
            query: 用户查询
            query_type: 查询类型（可选，自动分类）
            strategy: 路由策略（可选，自动选择）

        Returns:
            RouteResult 路由结果
        """
        # 1. 分类查询类型
        if query_type is None:
            query_type = self.classify_query(query)

        # 2. 获取通道权重
        weights = self._channel_weights.get(query_type, self._channel_weights[QueryType.GENERAL])

        # 3. 选择策略
        if strategy is None:
            strategy = self._strategy_map.get(query_type, RouteStrategy.ADAPTIVE)

        # 4. 根据策略选择通道
        selected_channels = self._select_channels(weights, strategy)

        # 5. 计算置信度
        confidence = self._calculate_confidence(query_type, weights)

        return RouteResult(
            query_type=query_type,
            selected_channels=selected_channels,
            channel_weights=weights,
            strategy=strategy,
            confidence=confidence,
            reasoning=f"Query classified as {query_type.value}, using {strategy.value} strategy"
        )

    def _select_channels(
        self,
        weights: Dict[ChannelType, float],
        strategy: RouteStrategy
    ) -> List[ChannelType]:
        """根据策略选择通道"""
        # Runtime switches are refreshed for every route decision. The client
        # keeps a short local cache, so UI changes do not require a restart.
        if ChannelType.KEYWORD in self.channel_configs:
            self.channel_configs[ChannelType.KEYWORD].enabled = feature_flags.is_enabled(
                "rag.hybrid.enabled"
            )

        enabled_channels = [
            (ch, w) for ch, w in weights.items()
            if w > 0 and self.channel_configs.get(ch, ChannelConfig(channel_type=ch)).enabled
        ]

        if not enabled_channels:
            return [ChannelType.VECTOR]  # 默认使用向量通道

        if strategy == RouteStrategy.SINGLE:
            # 单通道：选择权重最高的
            best = max(enabled_channels, key=lambda x: x[1])
            return [best[0]]

        if strategy == RouteStrategy.MULTI:
            # 多通道：选择所有启用的通道
            return [ch for ch, _ in enabled_channels]

        if strategy == RouteStrategy.CASCADING:
            # 级联：按权重排序，用于级联检索
            sorted_channels = sorted(enabled_channels, key=lambda x: x[1], reverse=True)
            return [ch for ch, _ in sorted_channels]

        if strategy == RouteStrategy.ADAPTIVE:
            # 自适应：选择权重高于阈值的通道
            return [ch for ch, w in enabled_channels if w >= ADAPTIVE_THRESHOLD]

        # 默认
        return [ChannelType.VECTOR]

    def _calculate_confidence(
        self,
        query_type: QueryType,
        weights: Dict[ChannelType, float]
    ) -> float:
        """计算路由置信度"""
        # 根据权重集中度调整
        max_weight = max(weights.values()) if weights else 0
        weight_sum = sum(weights.values())
        weight_concentration = max_weight / weight_sum if weight_sum > 0 else 0

        # 权重越集中，置信度越高
        confidence = CONFIDENCE_BASE_SCORE + (weight_concentration * CONFIDENCE_WEIGHT_FACTOR)

        return min(confidence, CONFIDENCE_MAX_SCORE)

    async def search(
        self,
        query: str,
        knowledge_base_id: int,
        query_type: Optional[QueryType] = None,
        strategy: Optional[RouteStrategy] = None,
        top_k: int = 10,
        **kwargs
    ) -> MergedResult:
        """
        执行多通道检索

        Args:
            query: 用户查询
            knowledge_base_id: 知识库ID
            query_type: 查询类型
            strategy: 路由策略
            top_k: 返回结果数

        Returns:
            MergedResult 合并后的结果
        """
        started_at = time.perf_counter()

        # 1. 路由
        route_result = self.route(query, query_type, strategy)

        logger.info(
            f"Routing query to channels: {[ch.value for ch in route_result.selected_channels]}, "
            f"strategy: {route_result.strategy.value}"
        )

        # 2. Execute every selected channel against a larger candidate set.
        # This lets RRF recover a good result that is not each channel's top 1.
        candidate_top_k = min(
            max(top_k, top_k * self.candidate_multiplier),
            self.max_candidates,
        )
        results_by_channel: Dict[ChannelType, List[SearchResult]] = {}
        channel_latencies_ms: Dict[str, float] = {}

        if route_result.strategy == RouteStrategy.CASCADING:
            # 级联检索：只有第一个通道返回了实质证据才停止。标题块常会
            # 精确命中关键词，但它本身不足以回答问题，必须继续语义通道。
            for channel_type in route_result.selected_channels:
                channel = self.channels.get(channel_type)
                if channel:
                    channel_started_at = time.perf_counter()
                    results = await channel.search(
                        query=query,
                        knowledge_base_id=knowledge_base_id,
                        top_k=candidate_top_k,
                        **kwargs
                    )
                    results_by_channel[channel_type] = results
                    channel_latencies_ms[channel_type.value] = round(
                        (time.perf_counter() - channel_started_at) * 1000, 2
                    )

                    if self._has_sufficient_cascading_evidence(results):
                        break
        else:
            # 并行检索
            import asyncio
            tasks: List[Tuple[ChannelType, Any]] = []
            for channel_type in route_result.selected_channels:
                channel = self.channels.get(channel_type)
                if channel:
                    tasks.append((
                        channel_type,
                        self._search_channel(
                            channel=channel,
                            query=query,
                            knowledge_base_id=knowledge_base_id,
                            top_k=candidate_top_k,
                            **kwargs,
                        ),
                    ))

            if tasks:
                results_list = await asyncio.gather(
                    *(task for _, task in tasks), return_exceptions=True
                )
                for (channel_type, _), result in zip(tasks, results_list):
                    if isinstance(result, tuple):
                        results, latency_ms = result
                        results_by_channel[channel_type] = results
                        channel_latencies_ms[channel_type.value] = latency_ms

        # 3. 合并结果
        merged = self._merge_results(results_by_channel, top_k, route_result)
        merged.metadata.update({
            "channel_candidates": self._debug_candidates(results_by_channel),
            "channel_latencies_ms": channel_latencies_ms,
            "router_latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
        })

        return merged

    @staticmethod
    def _has_sufficient_cascading_evidence(results: List[SearchResult]) -> bool:
        """Return whether a cascade stage has answer-bearing evidence.

        Candidate count alone is not a quality signal: BM25 can fill the whole
        candidate window with headings and weak lexical matches.  Requiring a
        minimum evidence score plus substantive content lets exact short-title
        hits fall through to vector retrieval and RRF corroboration.
        """
        for result in results:
            compact_content = re.sub(r"\s+", "", result.content or "")
            if (
                result.score >= app_config.RAG_MIN_EVIDENCE_SCORE
                and len(compact_content) >= 40
            ):
                return True
        return False

    @staticmethod
    async def _search_channel(
        channel: BaseChannel,
        query: str,
        knowledge_base_id: int,
        top_k: int,
        **kwargs,
    ) -> Tuple[List[SearchResult], float]:
        """Execute one channel and retain its latency for the debug trace."""
        started_at = time.perf_counter()
        results = await channel.search(
            query=query,
            knowledge_base_id=knowledge_base_id,
            top_k=top_k,
            **kwargs,
        )
        return results, round((time.perf_counter() - started_at) * 1000, 2)

    @staticmethod
    def _debug_candidates(
        results_by_channel: Dict[ChannelType, List[SearchResult]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Normalize raw channel candidates without exposing full chunk text."""
        return {
            channel_type.value: [
                {
                    "rank": rank,
                    "chunk_id": result.metadata.get("chunk_id"),
                    "document_id": result.document_id,
                    "knowledge_base_id": result.metadata.get("knowledge_base_id"),
                    "score": round(result.score, 6),
                    "content_preview": result.content[:500],
                    "multimodal": result.metadata.get("multimodal"),
                }
                for rank, result in enumerate(results, start=1)
            ]
            for channel_type, results in results_by_channel.items()
        }

    def _merge_results(
        self,
        results_by_channel: Dict[ChannelType, List[SearchResult]],
        top_k: int,
        route_result: RouteResult
    ) -> MergedResult:
        """Fuse channel rankings with weighted Reciprocal Rank Fusion (RRF)."""
        if not results_by_channel:
            return MergedResult(
                results=[],
                total_count=0,
                channels_used=[],
                merge_strategy="rrf",
            )

        fused: Dict[str, Dict[str, Any]] = {}
        active_weight = sum(
            route_result.channel_weights.get(channel_type, 1.0)
            for channel_type, results in results_by_channel.items()
            if results
        )
        maximum_rrf = active_weight / (self.rrf_k + 1)

        for channel_type, results in results_by_channel.items():
            weight = route_result.channel_weights.get(channel_type, 1.0)
            for rank, result in enumerate(results, start=1):
                key = self._result_key(result)
                entry = fused.setdefault(key, {
                    "result": result,
                    "rrf_score": 0.0,
                    "evidence_score": 0.0,
                    "source_scores": {},
                    "channels": [],
                })
                entry["rrf_score"] += weight / (self.rrf_k + rank)
                entry["evidence_score"] = max(entry["evidence_score"], result.score)
                entry["source_scores"][channel_type.value] = result.score
                if channel_type not in entry["channels"]:
                    entry["channels"].append(channel_type)

        final_results: List[SearchResult] = []
        for entry in fused.values():
            result = entry["result"]
            channels = entry["channels"]
            fused_score = entry["rrf_score"] / maximum_rrf if maximum_rrf else 0.0
            final_results.append(SearchResult(
                content=result.content,
                score=min(fused_score, 1.0),
                source=ChannelType.HYBRID if len(channels) > 1 else channels[0],
                document_id=result.document_id,
                metadata={
                    **result.metadata,
                    "fusion_method": "rrf",
                    "rrf_score": entry["rrf_score"],
                    "evidence_score": entry["evidence_score"],
                    "source_scores": entry["source_scores"],
                    "channels": [channel.value for channel in channels],
                },
            ))

        final_results.sort(key=lambda result: result.score, reverse=True)
        final_results = final_results[:top_k]
        channels_used = [
            channel for channel in results_by_channel
            if results_by_channel[channel]
        ]

        return MergedResult(
            results=final_results,
            total_count=len(final_results),
            channels_used=channels_used,
            merge_strategy="rrf",
            metadata={
                "route_result": {
                    "query_type": route_result.query_type.value,
                    "strategy": route_result.strategy.value,
                    "confidence": route_result.confidence,
                    "selected_channels": [
                        channel.value for channel in route_result.selected_channels
                    ],
                },
                "rrf_k": self.rrf_k,
                "candidate_top_k": min(
                    max(top_k, top_k * self.candidate_multiplier),
                    self.max_candidates,
                ),
            }
        )

    @staticmethod
    def _result_key(result: SearchResult) -> str:
        """Use the stable chunk identifier before falling back to content."""
        chunk_id = result.metadata.get("chunk_id")
        if chunk_id:
            return f"chunk:{chunk_id}"
        return f"content:{result.document_id}:{result.content.strip()}"

    def update_channel_weight(
        self,
        channel_type: ChannelType,
        query_type: QueryType,
        weight: float
    ):
        """更新通道权重"""
        if query_type in self._channel_weights:
            self._channel_weights[query_type][channel_type] = weight
            logger.info(f"Updated weight: {channel_type.value} -> {query_type.value}: {weight}")

    def add_channel(self, channel_type: ChannelType, channel: BaseChannel, weight: float = 0.5):
        """添加新通道"""
        self.channels[channel_type] = channel
        self.channel_configs[channel_type] = ChannelConfig(
            channel_type=channel_type,
            weight=weight
        )
        logger.info(f"Added channel: {channel_type.value}")

    def remove_channel(self, channel_type: ChannelType):
        """移除通道"""
        if channel_type in self.channels:
            del self.channels[channel_type]
        if channel_type in self.channel_configs:
            del self.channel_configs[channel_type]
        logger.info(f"Removed channel: {channel_type.value}")

    def get_stats(self) -> Dict[str, Any]:
        """获取路由器统计信息"""
        return {
            "channels": [ch.value for ch in self.channels.keys()],
            "query_types": [qt.value for qt in self._channel_weights.keys()],
            "strategies": [s.value for s in RouteStrategy],
        }


# =============================================================================
# 工厂类
# =============================================================================

class QueryRouterFactory:
    """QueryRouter 工厂类"""

    @staticmethod
    def create(
        channels: Optional[Dict[ChannelType, BaseChannel]] = None,
        **kwargs
    ) -> QueryRouter:
        """创建 QueryRouter 实例"""
        return QueryRouter(channels=channels, **kwargs)

    @staticmethod
    def create_with_defaults() -> QueryRouter:
        """创建默认配置的 QueryRouter"""
        return QueryRouter()


# =============================================================================
# 全局实例
# =============================================================================

_global_router: Optional[QueryRouter] = None


def get_router() -> QueryRouter:
    """获取全局 QueryRouter 实例"""
    global _global_router
    if _global_router is None:
        _global_router = QueryRouterFactory.create_with_defaults()
    return _global_router


def reset_router():
    """重置全局 QueryRouter 实例"""
    global _global_router
    _global_router = None
