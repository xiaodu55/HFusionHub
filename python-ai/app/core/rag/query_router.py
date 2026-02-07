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
import re
import time
import logging
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

logger = logging.getLogger(__name__)


# =============================================================================
# 枚举定义
# =============================================================================

class ChannelType(str, Enum):
    """检索通道类型"""
    VECTOR = "vector"          # 向量检索
    KEYWORD = "keyword"        # 关键词检索
    GRAPH = "graph"           # 图谱检索
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
            )

            return [
                SearchResult(
                    content=r.get("content", ""),
                    score=r.get("score", 0.0),
                    source=ChannelType.VECTOR,
                    document_id=r.get("document_id"),
                    metadata=r.get("metadata", {})
                )
                for r in results
            ]
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []


class KeywordChannel(BaseChannel):
    """关键词检索通道"""

    async def search(
        self,
        query: str,
        knowledge_base_id: int,
        top_k: int = 10,
        **kwargs
    ) -> List[SearchResult]:
        """关键词检索。

        优先使用项目在文档入库时维护的 ``chunks_store.json``，因此本地开发
        不依赖 Elasticsearch。部署 Elasticsearch 后，可在该通道前增加专用
        索引实现，而不会改变路由器接口。
        """
        try:
            from app.core.vectorstore.milvus_store import _load_chunks_store

            store = await asyncio.to_thread(_load_chunks_store)
            terms = self._tokenize(query)
            if not terms:
                return []

            scored: List[SearchResult] = []
            for document_id, chunks in store.items():
                for chunk in chunks:
                    if (knowledge_base_id is not None and
                            chunk.get("knowledge_base_id") != knowledge_base_id):
                        continue

                    content = chunk.get("content", "")
                    score = self._score(terms, content)
                    if score <= 0:
                        continue

                    scored.append(SearchResult(
                        content=content,
                        score=score,
                        source=ChannelType.KEYWORD,
                        document_id=chunk.get("document_id", document_id),
                        metadata={
                            "chunk_id": chunk.get("chunk_id"),
                            "knowledge_base_id": chunk.get("knowledge_base_id"),
                            "outline_path": chunk.get("outline_path", []),
                            "match_terms": [term for term in terms if term.lower() in content.lower()],
                        },
                    ))

            scored.sort(key=lambda item: item.score, reverse=True)
            return scored[:top_k]
        except Exception as e:
            logger.error("Keyword search failed: %s", e)
            return []

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """提取英文词、数字和单个中文字符，适配中英文混合文档。"""
        tokens = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text.lower())
        return list(dict.fromkeys(token for token in tokens if len(token) > 1 or "\u4e00" <= token <= "\u9fff"))

    @staticmethod
    def _score(terms: List[str], content: str) -> float:
        if not content:
            return 0.0
        lowered = content.lower()
        matches = sum(1 for term in terms if term in lowered)
        # 覆盖率为主，轻微奖励多次出现，保持得分在 0 到 1。
        coverage = matches / len(terms)
        frequency_bonus = min(sum(lowered.count(term) for term in terms) / 100, 0.1)
        return min(coverage + frequency_bonus, 1.0)


class GraphChannel(BaseChannel):
    """图谱检索通道 - 基于知识图谱的实体关系检索"""

    def __init__(self, config: ChannelConfig):
        super().__init__(config)
        self._manager = None

    def _get_manager(self):
        """延迟加载 KnowledgeGraphManager"""
        if self._manager is None:
            from app.core.rag.knowledge_graph import get_knowledge_graph_manager
            self._manager = get_knowledge_graph_manager()
        return self._manager

    async def search(
        self,
        query: str,
        knowledge_base_id: int,
        top_k: int = 10,
        **kwargs
    ) -> List[SearchResult]:
        """
        图谱检索

        检索策略：
        1. 实体搜索：查找与查询相关的实体
        2. 关系搜索：查找实体间的关系
        3. 子图搜索：获取相关实体的子图
        """
        try:
            manager = self._get_manager()
            if not manager._initialized:
                await manager.initialize()

            results = []

            # 1. 实体搜索
            entities = await manager.search_entities(
                query=query,
                limit=top_k
            )

            for entity in entities:
                results.append(SearchResult(
                    content=f"{entity.name}: {entity.description or 'No description'}",
                    score=ENTITY_MATCH_BASE_SCORE,
                    source=ChannelType.GRAPH,
                    document_id=None,
                    metadata={
                        "entity_id": entity.id,
                        "entity_type": entity.entity_type.value,
                        "entity_name": entity.name
                    }
                ))

            # 2. 获取实体的邻居关系
            for entity in entities[:3]:  # 限制前3个实体
                neighbors, relations = await manager.get_neighbors(
                    entity_id=entity.id,
                    depth=1
                )

                for neighbor in neighbors:
                    results.append(SearchResult(
                        content=f"{entity.name} -> {neighbor.name}: {neighbor.description or 'Related entity'}",
                        score=NEIGHBOR_RELATION_SCORE,
                        source=ChannelType.GRAPH,
                        document_id=None,
                        metadata={
                            "source_entity": entity.id,
                            "target_entity": neighbor.id,
                            "relation_type": "neighbor"
                        }
                    ))

            # 3. 按分数排序，取 top_k
            results.sort(key=lambda x: x.score, reverse=True)
            return results[:top_k]

        except Exception as e:
            logger.error(f"Graph search failed: {e}")
            return []


# =============================================================================
# 查询路由器
# =============================================================================

class QueryRouter:
    """查询路由器 - 智能选择检索通道"""

    def __init__(self, channels: Optional[Dict[ChannelType, BaseChannel]] = None):
        # 默认通道配置
        self.channel_configs: Dict[ChannelType, ChannelConfig] = {
            ChannelType.VECTOR: ChannelConfig(
                channel_type=ChannelType.VECTOR,
                weight=DEFAULT_CHANNEL_WEIGHT
            ),
            ChannelType.KEYWORD: ChannelConfig(
                channel_type=ChannelType.KEYWORD,
                weight=DEFAULT_CHANNEL_WEIGHT * 0.5
            ),
            ChannelType.GRAPH: ChannelConfig(
                channel_type=ChannelType.GRAPH,
                weight=DEFAULT_CHANNEL_WEIGHT * 0.3
            ),
        }

        # 通道实例
        self.channels = channels or {
            ChannelType.VECTOR: VectorChannel(self.channel_configs[ChannelType.VECTOR]),
            ChannelType.KEYWORD: KeywordChannel(self.channel_configs[ChannelType.KEYWORD]),
            ChannelType.GRAPH: GraphChannel(self.channel_configs[ChannelType.GRAPH]),
        }

        # 查询类型与通道权重映射
        self._channel_weights: Dict[QueryType, Dict[ChannelType, float]] = {
            QueryType.FACTUAL: {
                ChannelType.VECTOR: 0.7,
                ChannelType.KEYWORD: 0.3,
                ChannelType.GRAPH: 0.0,
            },
            QueryType.COMPARISON: {
                ChannelType.VECTOR: 0.8,
                ChannelType.KEYWORD: 0.1,
                ChannelType.GRAPH: 0.1,
            },
            QueryType.SUMMARY: {
                ChannelType.VECTOR: 0.6,
                ChannelType.KEYWORD: 0.2,
                ChannelType.GRAPH: 0.2,
            },
            QueryType.ENTITY: {
                ChannelType.VECTOR: 0.3,
                ChannelType.KEYWORD: 0.4,
                ChannelType.GRAPH: 0.3,
            },
            QueryType.RELATIONSHIP: {
                ChannelType.VECTOR: 0.2,
                ChannelType.KEYWORD: 0.2,
                ChannelType.GRAPH: 0.6,
            },
            QueryType.GENERAL: {
                ChannelType.VECTOR: 0.6,
                ChannelType.KEYWORD: 0.3,
                ChannelType.GRAPH: 0.1,
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
        # 1. 路由
        route_result = self.route(query, query_type, strategy)

        logger.info(
            f"Routing query to channels: {[ch.value for ch in route_result.selected_channels]}, "
            f"strategy: {route_result.strategy.value}"
        )

        # 2. 执行检索
        all_results: List[SearchResult] = []

        if route_result.strategy == RouteStrategy.CASCADING:
            # 级联检索：第一个通道结果足够则不查第二个
            for channel_type in route_result.selected_channels:
                channel = self.channels.get(channel_type)
                if channel:
                    results = await channel.search(
                        query=query,
                        knowledge_base_id=knowledge_base_id,
                        top_k=top_k,
                        **kwargs
                    )
                    all_results.extend(results)

                    # 如果结果足够，停止检索
                    if len(all_results) >= top_k:
                        break
        else:
            # 并行检索
            import asyncio
            tasks = []
            for channel_type in route_result.selected_channels:
                channel = self.channels.get(channel_type)
                if channel:
                    tasks.append(
                        channel.search(
                            query=query,
                            knowledge_base_id=knowledge_base_id,
                            top_k=top_k,
                            **kwargs
                        )
                    )

            if tasks:
                results_list = await asyncio.gather(*tasks, return_exceptions=True)
                for results in results_list:
                    if isinstance(results, list):
                        all_results.extend(results)

        # 3. 合并结果
        merged = self._merge_results(all_results, top_k, route_result)

        return merged

    def _merge_results(
        self,
        results: List[SearchResult],
        top_k: int,
        route_result: RouteResult
    ) -> MergedResult:
        """合并多通道结果"""
        if not results:
            return MergedResult(
                results=[],
                total_count=0,
                channels_used=[]
            )

        # 按分数排序
        sorted_results = sorted(results, key=lambda x: x.score, reverse=True)

        # 取 top_k
        final_results = sorted_results[:top_k]

        # 统计使用的通道
        channels_used = list(set(r.source for r in final_results))

        return MergedResult(
            results=final_results,
            total_count=len(final_results),
            channels_used=channels_used,
            merge_strategy="score_based",
            metadata={
                "route_result": {
                    "query_type": route_result.query_type.value,
                    "strategy": route_result.strategy.value,
                    "confidence": route_result.confidence,
                    "selected_channels": [
                        channel.value for channel in route_result.selected_channels
                    ],
                }
            }
        )

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
