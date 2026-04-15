# Copyright (c) 2026 HFusionHub. All rights reserved.
"""
QueryRouter 模块单元测试

覆盖：
- 数据模型验证
- 查询分类逻辑
- 路由策略选择
- 通道选择逻辑
- 多通道检索
- 工厂类
- 全局实例管理
"""

import pytest
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from app.core.rag.query_router import (
    ChannelType,
    RouteStrategy,
    QueryType,
    ChannelConfig,
    RouteResult,
    SearchResult,
    MergedResult,
    BaseChannel,
    VectorChannel,
    KeywordChannel,
    GraphChannel,
    QueryRouter,
    QueryRouterFactory,
    get_router,
    reset_router,
)


# =============================================================================
# 数据模型测试
# =============================================================================

class TestChannelConfig:
    """ChannelConfig 数据模型测试"""

    def test_create_channel_config(self):
        """测试创建通道配置"""
        config = ChannelConfig(
            channel_type=ChannelType.VECTOR,
            weight=1.0,
            enabled=True,
            timeout=10.0,
            max_results=10
        )
        assert config.channel_type == ChannelType.VECTOR
        assert config.weight == 1.0
        assert config.enabled is True
        assert config.timeout == 10.0
        assert config.max_results == 10

    def test_channel_config_default_values(self):
        """测试默认值"""
        config = ChannelConfig(channel_type=ChannelType.KEYWORD)
        assert config.weight == 1.0
        assert config.enabled is True
        assert config.timeout == 10.0
        assert config.max_results == 10
        assert config.params == {}

    def test_channel_config_invalid_weight(self):
        """测试无效权重"""
        with pytest.raises(ValueError, match="weight must be between"):
            ChannelConfig(channel_type=ChannelType.VECTOR, weight=-0.1)

        with pytest.raises(ValueError, match="weight must be between"):
            ChannelConfig(channel_type=ChannelType.VECTOR, weight=2.1)

    def test_channel_config_invalid_timeout(self):
        """测试无效超时时间"""
        with pytest.raises(ValueError, match="timeout must be positive"):
            ChannelConfig(channel_type=ChannelType.VECTOR, timeout=0)

        with pytest.raises(ValueError, match="timeout must be positive"):
            ChannelConfig(channel_type=ChannelType.VECTOR, timeout=-1)


class TestRouteResult:
    """RouteResult 数据模型测试"""

    def test_create_route_result(self):
        """测试创建路由结果"""
        result = RouteResult(
            query_type=QueryType.FACTUAL,
            selected_channels=[ChannelType.VECTOR, ChannelType.KEYWORD],
            channel_weights={
                ChannelType.VECTOR: 0.7,
                ChannelType.KEYWORD: 0.3
            },
            strategy=RouteStrategy.MULTI,
            confidence=0.85,
            reasoning="Factual query detected"
        )
        assert result.query_type == QueryType.FACTUAL
        assert len(result.selected_channels) == 2
        assert result.strategy == RouteStrategy.MULTI
        assert result.confidence == 0.85

    def test_route_result_default_values(self):
        """测试默认值"""
        result = RouteResult(
            query_type=QueryType.GENERAL,
            selected_channels=[ChannelType.VECTOR],
            channel_weights={ChannelType.VECTOR: 1.0},
            strategy=RouteStrategy.SINGLE
        )
        assert result.confidence == 0.0
        assert result.reasoning == ""
        assert result.metadata == {}


class TestSearchResult:
    """SearchResult 数据模型测试"""

    def test_create_search_result(self):
        """测试创建检索结果"""
        result = SearchResult(
            content="测试内容",
            score=0.95,
            source=ChannelType.VECTOR,
            document_id=123,
            metadata={"key": "value"}
        )
        assert result.content == "测试内容"
        assert result.score == 0.95
        assert result.source == ChannelType.VECTOR
        assert result.document_id == 123

    def test_search_result_default_values(self):
        """测试默认值"""
        result = SearchResult(content="内容", score=0.8, source=ChannelType.KEYWORD)
        assert result.document_id is None
        assert result.metadata == {}


class TestMergedResult:
    """MergedResult 数据模型测试"""

    def test_create_merged_result(self):
        """测试创建合并结果"""
        results = [
            SearchResult(content="内容1", score=0.9, source=ChannelType.VECTOR),
            SearchResult(content="内容2", score=0.8, source=ChannelType.KEYWORD),
        ]
        merged = MergedResult(
            results=results,
            total_count=2,
            channels_used=[ChannelType.VECTOR, ChannelType.KEYWORD],
            merge_strategy="score_based"
        )
        assert merged.total_count == 2
        assert len(merged.channels_used) == 2


# =============================================================================
# 通道测试
# =============================================================================

class TestVectorChannel:
    """VectorChannel 测试"""

    @pytest.mark.asyncio
    async def test_vector_channel_search(self):
        """测试向量检索"""
        config = ChannelConfig(channel_type=ChannelType.VECTOR)
        channel = VectorChannel(config)

        # Mock Milvus Lite 同步搜索函数
        mock_search = MagicMock(return_value=[
            {"content": "测试文档", "score": 0.9, "document_id": 1}
        ])
        mock_milvus = MagicMock()
        mock_milvus.search_similar = mock_search

        with patch.dict("sys.modules", {"app.core.vectorstore.milvus_store": mock_milvus}):
            results = await channel.search(
                query="测试查询",
                knowledge_base_id=1,
                top_k=5
            )

        assert len(results) == 1
        assert results[0].content == "测试文档"
        assert results[0].source == ChannelType.VECTOR

    @pytest.mark.asyncio
    async def test_vector_channel_search_error(self):
        """测试向量检索错误处理"""
        config = ChannelConfig(channel_type=ChannelType.VECTOR)
        channel = VectorChannel(config)

        # Mock the import to raise exception
        mock_milvus = MagicMock()
        mock_milvus.get_milvus_store.side_effect = Exception("连接失败")

        with patch.dict("sys.modules", {"app.core.vectorstore.milvus_store": mock_milvus}):
            results = await channel.search(
                query="测试查询",
                knowledge_base_id=1,
                top_k=5
            )

        assert results == []


class TestKeywordChannel:
    """KeywordChannel 测试"""

    @pytest.mark.asyncio
    async def test_keyword_channel_search(self):
        """测试基于本地 chunk store 的关键词检索"""
        config = ChannelConfig(channel_type=ChannelType.KEYWORD)
        channel = KeywordChannel(config)

        mock_milvus = MagicMock()
        mock_milvus._load_chunks_store.return_value = {
            "1": [{
                "chunk_id": "chunk-1",
                "document_id": "1",
                "knowledge_base_id": 1,
                "content": "Python 查询路由器支持关键词检索",
            }]
        }
        with patch.dict("sys.modules", {"app.core.vectorstore.milvus_store": mock_milvus}):
            results = await channel.search(
                query="Python 查询",
                knowledge_base_id=1,
                top_k=5
            )

        assert len(results) == 1
        assert results[0].source == ChannelType.KEYWORD
        assert results[0].document_id == "1"

    @pytest.mark.asyncio
    async def test_keyword_channel_uses_bm25_and_knowledge_base_scope(self):
        config = ChannelConfig(channel_type=ChannelType.KEYWORD)
        channel = KeywordChannel(config)

        mock_milvus = MagicMock()
        mock_milvus._load_chunks_store.return_value = {
            "1": [
                {
                    "chunk_id": "common",
                    "document_id": "1",
                    "knowledge_base_id": 7,
                    "content": "部署 部署 部署 部署",
                },
                {
                    "chunk_id": "specific",
                    "document_id": "1",
                    "knowledge_base_id": 7,
                    "content": "部署时使用 bluegreen 发布策略",
                },
            ],
            "2": [{
                "chunk_id": "foreign-kb",
                "document_id": "2",
                "knowledge_base_id": 8,
                "content": "bluegreen 发布策略只属于另一个知识库",
            }],
        }
        with patch.dict("sys.modules", {"app.core.vectorstore.milvus_store": mock_milvus}):
            results = await channel.search(
                query="bluegreen 部署",
                knowledge_base_id=7,
                top_k=5,
            )

        assert [result.metadata["chunk_id"] for result in results] == ["specific", "common"]
        assert all(result.metadata["knowledge_base_id"] == 7 for result in results)
        assert results[0].metadata["bm25_score"] > results[1].metadata["bm25_score"]

    @pytest.mark.asyncio
    async def test_keyword_heading_expands_adjacent_body_chunks(self):
        config = ChannelConfig(channel_type=ChannelType.KEYWORD)
        channel = KeywordChannel(config)

        mock_milvus = MagicMock()
        mock_milvus._load_chunks_store.return_value = {
            "2": [
                {
                    "chunk_id": "2_chunk_0001",
                    "document_id": "2",
                    "knowledge_base_id": 1,
                    "block_type": "HEADING",
                    "content": "一、什么是虚拟线程",
                },
                {
                    "chunk_id": "2_chunk_0002",
                    "document_id": "2",
                    "knowledge_base_id": 1,
                    "block_type": "PARAGRAPH",
                    "content": "虚拟线程是由 JVM 管理的轻量级线程。",
                },
                {
                    "chunk_id": "2_chunk_0003",
                    "document_id": "2",
                    "knowledge_base_id": 1,
                    "block_type": "PARAGRAPH",
                    "content": "它适合高并发的 I/O 密集型任务。",
                },
                {
                    "chunk_id": "2_chunk_0004",
                    "document_id": "2",
                    "knowledge_base_id": 1,
                    "block_type": "HEADING",
                    "content": "二、使用方式",
                },
            ]
        }
        with patch.dict("sys.modules", {"app.core.vectorstore.milvus_store": mock_milvus}):
            results = await channel.search(
                query="什么是虚拟线程",
                knowledge_base_id=1,
                top_k=5,
            )

        assert "JVM 管理" in results[0].content
        assert "I/O 密集型" in results[0].content
        assert "二、使用方式" not in results[0].content
        assert results[0].metadata["expanded_from_heading"] is True
        assert results[0].metadata["neighbor_chunk_ids"] == [
            "2_chunk_0002",
            "2_chunk_0003",
        ]


class TestGraphChannel:
    """GraphChannel 测试"""

    @pytest.mark.asyncio
    async def test_graph_channel_search(self):
        """测试图谱检索（预留）"""
        config = ChannelConfig(channel_type=ChannelType.GRAPH)
        graph_store = MagicMock()
        graph_store.search.return_value = []
        channel = GraphChannel(config, graph_store=graph_store, chunk_loader=lambda: {})

        results = await channel.search(
            query="测试查询",
            knowledge_base_id=1,
            top_k=5
        )

        assert results == []
        graph_store.search.assert_called_once()


# =============================================================================
# QueryRouter 核心逻辑测试
# =============================================================================

class TestQueryRouter:
    """QueryRouter 核心逻辑测试"""

    def setup_method(self):
        """每个测试前重置"""
        self.router = QueryRouter()

    def test_classify_query_comparison(self):
        """测试比较查询分类"""
        test_cases = [
            ("比较Python和Java", QueryType.COMPARISON),
            ("A和B有什么区别", QueryType.COMPARISON),
            ("对比这两个方案", QueryType.COMPARISON),
        ]
        for query, expected in test_cases:
            result = self.router.classify_query(query)
            assert result == expected, f"Query: {query}"

    def test_classify_query_summary(self):
        """测试总结查询分类"""
        test_cases = [
            ("总结一下这篇文章", QueryType.SUMMARY),
            ("概括主要内容", QueryType.SUMMARY),
            ("归纳一下要点", QueryType.SUMMARY),
        ]
        for query, expected in test_cases:
            result = self.router.classify_query(query)
            assert result == expected, f"Query: {query}"

    def test_classify_query_entity(self):
        """测试实体查询分类"""
        test_cases = [
            ("Python是什么", QueryType.ENTITY),
            ("什么是机器学习", QueryType.ENTITY),
            ("深度学习的定义", QueryType.ENTITY),
        ]
        for query, expected in test_cases:
            result = self.router.classify_query(query)
            assert result == expected, f"Query: {query}"

    def test_classify_query_relationship(self):
        """测试关系查询分类"""
        test_cases = [
            ("Python和Django的关系", QueryType.RELATIONSHIP),
            ("机器学习和深度学习的联系", QueryType.RELATIONSHIP),
        ]
        for query, expected in test_cases:
            result = self.router.classify_query(query)
            assert result == expected, f"Query: {query}"

    def test_classify_query_factual(self):
        """测试事实查询分类"""
        test_cases = [
            ("Python有多少个版本", QueryType.FACTUAL),
            ("Java何时发布", QueryType.FACTUAL),
            ("哪里可以下载", QueryType.FACTUAL),
        ]
        for query, expected in test_cases:
            result = self.router.classify_query(query)
            assert result == expected, f"Query: {query}"

    def test_classify_query_general(self):
        """测试通用查询分类"""
        result = self.router.classify_query("聊聊编程")
        assert result == QueryType.GENERAL

    def test_route_basic(self):
        """测试基本路由"""
        result = self.router.route("Python是什么？")

        assert isinstance(result, RouteResult)
        assert result.query_type == QueryType.ENTITY
        assert ChannelType.VECTOR in result.selected_channels
        assert result.confidence > 0

    def test_route_with_explicit_type(self):
        """测试指定类型路由"""
        result = self.router.route(
            "测试查询",
            query_type=QueryType.COMPARISON
        )

        assert result.query_type == QueryType.COMPARISON
        assert result.strategy == RouteStrategy.MULTI

    def test_route_with_explicit_strategy(self):
        """测试指定策略路由"""
        result = self.router.route(
            "测试查询",
            strategy=RouteStrategy.SINGLE
        )

        assert result.strategy == RouteStrategy.SINGLE
        assert len(result.selected_channels) == 1

    def test_route_single_strategy(self):
        """测试单通道策略"""
        result = self.router.route(
            "Python是什么？",
            strategy=RouteStrategy.SINGLE
        )

        assert len(result.selected_channels) == 1

    def test_route_multi_strategy(self):
        """测试多通道策略"""
        result = self.router.route(
            "Python是什么？",
            strategy=RouteStrategy.MULTI
        )

        assert len(result.selected_channels) >= 1

    def test_route_adaptive_strategy(self):
        """测试自适应策略"""
        result = self.router.route(
            "Python是什么？",
            strategy=RouteStrategy.ADAPTIVE
        )

        # 自适应策略只选择权重高于阈值的通道
        assert len(result.selected_channels) >= 1

    def test_route_confidence_calculation(self):
        """测试置信度计算"""
        # 事实查询权重集中，置信度应该较高
        factual_result = self.router.route("Python是什么？", query_type=QueryType.FACTUAL)

        # 通用查询权重分散，置信度应该较低
        general_result = self.router.route("聊聊编程", query_type=QueryType.GENERAL)

        assert factual_result.confidence >= general_result.confidence

    def test_update_channel_weight(self):
        """测试更新通道权重"""
        self.router.update_channel_weight(
            ChannelType.VECTOR,
            QueryType.FACTUAL,
            0.9
        )

        weights = self.router._channel_weights[QueryType.FACTUAL]
        assert weights[ChannelType.VECTOR] == 0.9

    def test_add_channel(self):
        """测试添加通道"""
        new_channel = MagicMock(spec=BaseChannel)
        self.router.add_channel(ChannelType.KEYWORD, new_channel, weight=0.8)

        assert ChannelType.KEYWORD in self.router.channels
        assert self.router.channel_configs[ChannelType.KEYWORD].weight == 0.8

    def test_remove_channel(self):
        """测试移除通道"""
        self.router.remove_channel(ChannelType.KEYWORD)

        assert ChannelType.KEYWORD not in self.router.channels

    def test_get_stats(self):
        """测试获取统计信息"""
        stats = self.router.get_stats()

        assert "channels" in stats
        assert "query_types" in stats
        assert "strategies" in stats


# =============================================================================
# 多通道检索测试
# =============================================================================

class TestQueryRouterSearch:
    """QueryRouter 多通道检索测试"""

    def setup_method(self):
        """每个测试前重置，并隔离本地关键词索引。"""
        self.router = QueryRouter()
        # KeywordChannel now reads the local chunk store. These router unit tests
        # only exercise their explicitly configured channels, so the default
        # keyword channel must not leak fixture data into their assertions.
        mock_keyword = AsyncMock(spec=KeywordChannel)
        mock_keyword.search.return_value = []
        self.router.channels[ChannelType.KEYWORD] = mock_keyword

    @pytest.mark.asyncio
    async def test_search_basic(self):
        """测试基本检索"""
        # Mock 通道
        mock_vector = AsyncMock(spec=VectorChannel)
        mock_vector.search.return_value = [
            SearchResult(content="向量结果", score=0.9, source=ChannelType.VECTOR)
        ]
        self.router.channels[ChannelType.VECTOR] = mock_vector

        result = await self.router.search(
            query="Python是什么？",
            knowledge_base_id=1,
            top_k=5
        )

        assert isinstance(result, MergedResult)
        assert result.total_count == 1
        assert result.results[0].content == "向量结果"

    @pytest.mark.asyncio
    async def test_search_multi_channel(self):
        """测试多通道检索"""
        # Mock 通道
        mock_vector = AsyncMock(spec=VectorChannel)
        mock_vector.search.return_value = [
            SearchResult(content="向量结果", score=0.9, source=ChannelType.VECTOR)
        ]

        mock_keyword = AsyncMock(spec=KeywordChannel)
        mock_keyword.search.return_value = [
            SearchResult(content="关键词结果", score=0.8, source=ChannelType.KEYWORD)
        ]

        self.router.channels[ChannelType.VECTOR] = mock_vector
        self.router.channels[ChannelType.KEYWORD] = mock_keyword

        result = await self.router.search(
            query="Python是什么？",
            knowledge_base_id=1,
            top_k=5
        )

        assert result.total_count == 2
        assert len(result.channels_used) == 2

    @pytest.mark.asyncio
    async def test_search_cascading(self):
        """测试级联检索"""
        # Mock 通道
        mock_vector = AsyncMock(spec=VectorChannel)
        mock_vector.search.return_value = [
            SearchResult(content="向量结果", score=0.9, source=ChannelType.VECTOR)
        ]

        self.router.channels[ChannelType.VECTOR] = mock_vector

        result = await self.router.search(
            query="Python是什么？",
            knowledge_base_id=1,
            strategy=RouteStrategy.CASCADING,
            top_k=5
        )

        assert result.total_count == 1

    @pytest.mark.asyncio
    async def test_cascading_continues_after_heading_only_keyword_hit(self):
        """A full keyword candidate window of headings must not suppress vectors."""
        mock_keyword = AsyncMock(spec=KeywordChannel)
        mock_keyword.search.return_value = [
            SearchResult(
                content="一、什么是虚拟线程",
                score=1.0,
                source=ChannelType.KEYWORD,
                document_id=2,
                metadata={"chunk_id": "2_chunk_0001"},
            )
        ]
        mock_vector = AsyncMock(spec=VectorChannel)
        mock_vector.search.return_value = [
            SearchResult(
                content=(
                    "虚拟线程是由 JVM 调度的轻量级线程，适合高并发的 I/O 密集型任务，"
                    "并在 Java 21 中正式发布。"
                ),
                score=0.91,
                source=ChannelType.VECTOR,
                document_id=2,
                metadata={"chunk_id": "2_chunk_0002"},
            )
        ]
        self.router.channels[ChannelType.KEYWORD] = mock_keyword
        self.router.channels[ChannelType.VECTOR] = mock_vector

        result = await self.router.search(
            query="什么是虚拟线程",
            knowledge_base_id=1,
            query_type=QueryType.ENTITY,
            strategy=RouteStrategy.CASCADING,
            top_k=5,
        )

        mock_vector.search.assert_awaited_once()
        assert ChannelType.KEYWORD in result.channels_used
        assert ChannelType.VECTOR in result.channels_used
        assert any("JVM" in item.content for item in result.results)

    @pytest.mark.asyncio
    async def test_cascading_stops_after_substantive_keyword_evidence(self):
        mock_keyword = AsyncMock(spec=KeywordChannel)
        mock_keyword.search.return_value = [
            SearchResult(
                content=(
                    "虚拟线程是由 JVM 管理的轻量级线程，不会为每个任务绑定一个操作系统线程，"
                    "因此能够以较低资源开销支持大量并发任务。"
                ),
                score=0.9,
                source=ChannelType.KEYWORD,
            )
        ]
        mock_vector = AsyncMock(spec=VectorChannel)
        mock_vector.search.return_value = []
        self.router.channels[ChannelType.KEYWORD] = mock_keyword
        self.router.channels[ChannelType.VECTOR] = mock_vector

        await self.router.search(
            query="什么是虚拟线程",
            knowledge_base_id=1,
            query_type=QueryType.ENTITY,
            strategy=RouteStrategy.CASCADING,
            top_k=5,
        )

        mock_vector.search.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_search_empty_results(self):
        """测试空结果"""
        # Mock 通道返回空
        mock_vector = AsyncMock(spec=VectorChannel)
        mock_vector.search.return_value = []

        self.router.channels[ChannelType.VECTOR] = mock_vector

        result = await self.router.search(
            query="不存在的内容",
            knowledge_base_id=1,
            top_k=5
        )

        assert result.total_count == 0
        assert result.results == []

    @pytest.mark.asyncio
    async def test_search_with_query_type(self):
        """测试指定查询类型检索"""
        mock_vector = AsyncMock(spec=VectorChannel)
        mock_vector.search.return_value = [
            SearchResult(content="结果", score=0.9, source=ChannelType.VECTOR)
        ]
        self.router.channels[ChannelType.VECTOR] = mock_vector

        result = await self.router.search(
            query="测试查询",
            knowledge_base_id=1,
            query_type=QueryType.COMPARISON,
            top_k=5
        )

        assert result.metadata["route_result"]["query_type"] == "comparison"

    def test_rrf_merges_duplicate_chunk_and_preserves_evidence_score(self):
        route = RouteResult(
            query_type=QueryType.FACTUAL,
            selected_channels=[ChannelType.VECTOR, ChannelType.KEYWORD],
            channel_weights={ChannelType.VECTOR: 0.7, ChannelType.KEYWORD: 0.3},
            strategy=RouteStrategy.MULTI,
        )
        merged = self.router._merge_results(
            {
                ChannelType.VECTOR: [
                    SearchResult(
                        content="版本 2.0 在 2026 年发布",
                        score=0.72,
                        source=ChannelType.VECTOR,
                        document_id=1,
                        metadata={"chunk_id": "shared"},
                    ),
                    SearchResult(
                        content="不相关的向量候选",
                        score=0.95,
                        source=ChannelType.VECTOR,
                        document_id=1,
                        metadata={"chunk_id": "vector-only"},
                    ),
                ],
                ChannelType.KEYWORD: [
                    SearchResult(
                        content="版本 2.0 在 2026 年发布",
                        score=0.90,
                        source=ChannelType.KEYWORD,
                        document_id=1,
                        metadata={"chunk_id": "shared"},
                    ),
                ],
            },
            top_k=5,
            route_result=route,
        )

        assert merged.merge_strategy == "rrf"
        assert merged.total_count == 2
        assert merged.results[0].metadata["chunk_id"] == "shared"
        assert merged.results[0].source == ChannelType.HYBRID
        assert merged.results[0].metadata["channels"] == ["vector", "keyword"]
        assert merged.results[0].metadata["evidence_score"] == 0.90

    def test_rrf_candidate_limit_is_configurable(self):
        router = QueryRouter(rrf_k=20, candidate_multiplier=4, max_candidates=12)
        route = RouteResult(
            query_type=QueryType.GENERAL,
            selected_channels=[ChannelType.VECTOR],
            channel_weights={ChannelType.VECTOR: 1.0},
            strategy=RouteStrategy.SINGLE,
        )
        merged = router._merge_results(
            {ChannelType.VECTOR: [
                SearchResult("evidence", 0.9, ChannelType.VECTOR, metadata={"chunk_id": "1"})
            ]},
            top_k=5,
            route_result=route,
        )

        assert merged.metadata["rrf_k"] == 20
        assert merged.metadata["candidate_top_k"] == 12


# =============================================================================
# 工厂类测试
# =============================================================================

class TestQueryRouterFactory:
    """QueryRouterFactory 测试"""

    def test_create_router(self):
        """测试创建路由器"""
        router = QueryRouterFactory.create()
        assert isinstance(router, QueryRouter)

    def test_create_with_defaults(self):
        """测试创建默认配置路由器"""
        router = QueryRouterFactory.create_with_defaults()
        assert isinstance(router, QueryRouter)
        assert ChannelType.VECTOR in router.channels


# =============================================================================
# 全局实例测试
# =============================================================================

class TestGlobalInstance:
    """全局实例管理测试"""

    def setup_method(self):
        """每个测试前重置"""
        reset_router()

    def teardown_method(self):
        """每个测试后重置"""
        reset_router()

    def test_get_router_singleton(self):
        """测试单例模式"""
        router1 = get_router()
        router2 = get_router()
        assert router1 is router2

    def test_reset_router(self):
        """测试重置实例"""
        router1 = get_router()
        reset_router()
        router2 = get_router()
        assert router1 is not router2


# =============================================================================
# 集成测试
# =============================================================================

class TestIntegration:
    """集成测试"""

    def test_full_workflow(self):
        """测试完整工作流"""
        # 1. 创建路由器
        router = QueryRouterFactory.create_with_defaults()

        # 2. 分类查询
        query_type = router.classify_query("比较Python和Java的区别")
        assert query_type == QueryType.COMPARISON

        # 3. 路由
        route_result = router.route("比较Python和Java的区别")
        assert route_result.query_type == QueryType.COMPARISON
        assert route_result.strategy == RouteStrategy.MULTI

        # 4. 验证通道选择
        assert len(route_result.selected_channels) >= 1

    def test_channel_weights_consistency(self):
        """测试通道权重一致性"""
        router = QueryRouter()

        # 所有查询类型的权重都应该在0-1之间
        for query_type, weights in router._channel_weights.items():
            for channel_type, weight in weights.items():
                assert 0 <= weight <= 1, f"{query_type.value} -> {channel_type.value}: {weight}"

    def test_strategy_query_type_mapping(self):
        """测试策略与查询类型映射"""
        router = QueryRouter()

        # 所有查询类型都应该有对应的策略
        for query_type in QueryType:
            assert query_type in router._strategy_map, f"Missing strategy for {query_type.value}"
