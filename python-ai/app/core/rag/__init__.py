"""
RAG Module - 检索增强生成模块
参考 Ragent 项目的架构设计

组件:
- IntentClassifier: 意图分类器
- QueryDecomposer: 问题分解器
- ContextCompressor: 上下文压缩器
- SelfReflector: 自我反思器
- QueryRouter: 查询路由器
- MultiTurnStrategy: 多轮检索策略
- KnowledgeGraph: 知识图谱
- QueryRewriter: 问题重写器
- MultiChannelRetriever: 多通道检索器
- Postprocessor: 后处理器
- Utils: 公共工具函数
"""

from typing import Optional

from .utils import (
    estimate_tokens,
    extract_key_phrases,
    split_sentences,
    calculate_text_similarity,
    truncate_text,
)

from .models import (
    IntentType,
    ComplexityLevel,
    DomainType,
    IntentResult
)
from .strategies import (
    ClassificationStrategy,
    LLMClassificationStrategy,
    RuleClassificationStrategy,
    HybridClassificationStrategy
)
from .intent_classifier import (
    IntentClassifierFactory,
    ClassificationStrategyType,
    IntentClassifier
)
from .query_decomposer import (
    SubQuestion,
    DecompositionResult,
    QuestionTreeNode,
    DecompositionStrategy,
    DecompositionStrategyType,
    LLMDecompositionStrategy,
    RuleDecompositionStrategy,
    HybridDecompositionStrategy,
    QueryDecomposer,
    QueryDecomposerFactory,
    SubQuestionStatus,
)
from .context_compressor import (
    ContextCompressor,
    ContextCompressorFactory,
    CompressionStrategyType,
    CompressionResult,
    CompressionConfig,
    CompressionStatus,
    ExtractiveCompressionStrategy,
    AbstractiveCompressionStrategy,
    HybridCompressionStrategy,
    RecursiveCompressionStrategy,
    get_compressor,
    reset_compressor,
)
from .self_reflector import (
    SelfReflector,
    SelfReflectorFactory,
    ReflectionStrategyType,
    ReflectionResult,
    ReflectionConfig,
    ReflectionStatus,
    QualityCriteria,
    QualityDimension,
    LLMReflectionStrategy,
    RuleBasedReflectionStrategy,
    HybridReflectionStrategy,
    get_reflector,
    reset_reflector,
)
from .query_router import (
    QueryRouter,
    QueryRouterFactory,
    ChannelType,
    RouteStrategy,
    QueryType,
    ChannelConfig,
    RouteResult,
    SearchResult,
    MergedResult,
    VectorChannel,
    KeywordChannel,
    GraphChannel,
    get_router,
    reset_router,
)
from .multi_turn_strategy import (
    MultiTurnManager,
    MultiTurnStrategyFactory,
    ConversationState,
    StrategyType,
    TurnRole,
    ConversationTurn,
    ConversationContext,
    StrategyConfig,
    RetrievalAdjustment,
    ConversationStateManager,
    TopicEntityExtractor,
    ContextualStrategy,
    TopicFocusedStrategy,
    ExpansiveStrategy,
    HistoryBasedStrategy,
    AdaptiveMultiTurnStrategy,
    get_manager,
    reset_manager,
)
from .knowledge_graph import (
    EntityType,
    RelationType,
    GraphQueryType,
    Entity,
    Relation,
    GraphNode,
    GraphEdge,
    GraphPath,
    SubGraph,
    GraphQueryResult,
    GraphDatabase,
    Neo4jDatabase,
    InMemoryGraphDatabase,
    KnowledgeGraphManager,
    GraphBuilder,
    KnowledgeGraphFactory,
    get_knowledge_graph_manager,
    reset_knowledge_graph_manager,
)
from .query_rewriter import QueryRewriter, get_query_rewriter, RewriteResult
from .retriever import MultiChannelRetriever, get_retriever, RetrievalResult
from .postprocessor import Postprocessor, get_postprocessor, ProcessedResult

__all__ = [
    # 公共工具函数
    "estimate_tokens",
    "extract_key_phrases",
    "split_sentences",
    "calculate_text_similarity",
    "truncate_text",
    # 意图分类器
    "IntentType",
    "ComplexityLevel",
    "DomainType",
    "IntentResult",
    "ClassificationStrategy",
    "LLMClassificationStrategy",
    "RuleClassificationStrategy",
    "HybridClassificationStrategy",
    "IntentClassifierFactory",
    "ClassificationStrategyType",
    "IntentClassifier",
    "get_intent_classifier",
    # 问题分解器
    "SubQuestion",
    "SubQuestionStatus",
    "DecompositionResult",
    "QuestionTreeNode",
    "DecompositionStrategy",
    "DecompositionStrategyType",
    "LLMDecompositionStrategy",
    "RuleDecompositionStrategy",
    "HybridDecompositionStrategy",
    "QueryDecomposer",
    "QueryDecomposerFactory",
    "get_query_decomposer",
    # 上下文压缩器
    "ContextCompressor",
    "ContextCompressorFactory",
    "CompressionStrategyType",
    "CompressionResult",
    "CompressionConfig",
    "CompressionStatus",
    "ExtractiveCompressionStrategy",
    "AbstractiveCompressionStrategy",
    "HybridCompressionStrategy",
    "RecursiveCompressionStrategy",
    "get_compressor",
    "reset_compressor",
    # 自我反思器
    "SelfReflector",
    "SelfReflectorFactory",
    "ReflectionStrategyType",
    "ReflectionResult",
    "ReflectionConfig",
    "ReflectionStatus",
    "QualityCriteria",
    "QualityDimension",
    "LLMReflectionStrategy",
    "RuleBasedReflectionStrategy",
    "HybridReflectionStrategy",
    "get_reflector",
    "reset_reflector",
    # 查询路由器
    "QueryRouter",
    "QueryRouterFactory",
    "ChannelType",
    "RouteStrategy",
    "QueryType",
    "ChannelConfig",
    "RouteResult",
    "SearchResult",
    "MergedResult",
    "VectorChannel",
    "KeywordChannel",
    "GraphChannel",
    "get_router",
    "reset_router",
    # 多轮检索策略
    "MultiTurnManager",
    "MultiTurnStrategyFactory",
    "ConversationState",
    "StrategyType",
    "TurnRole",
    "ConversationTurn",
    "ConversationContext",
    "StrategyConfig",
    "RetrievalAdjustment",
    "ConversationStateManager",
    "TopicEntityExtractor",
    "ContextualStrategy",
    "TopicFocusedStrategy",
    "ExpansiveStrategy",
    "HistoryBasedStrategy",
    "AdaptiveMultiTurnStrategy",
    "get_manager",
    "reset_manager",
    # 知识图谱
    "EntityType",
    "RelationType",
    "GraphQueryType",
    "Entity",
    "Relation",
    "GraphNode",
    "GraphEdge",
    "GraphPath",
    "SubGraph",
    "GraphQueryResult",
    "GraphDatabase",
    "Neo4jDatabase",
    "InMemoryGraphDatabase",
    "KnowledgeGraphManager",
    "GraphBuilder",
    "KnowledgeGraphFactory",
    "get_knowledge_graph_manager",
    "reset_knowledge_graph_manager",
    # 问题重写器
    "QueryRewriter",
    "get_query_rewriter",
    "RewriteResult",
    # 多通道检索器
    "MultiChannelRetriever",
    "get_retriever",
    "RetrievalResult",
    # 后处理器
    "Postprocessor",
    "get_postprocessor",
    "ProcessedResult",
]


# 全局意图分类器实例
_intent_classifier: Optional[IntentClassifier] = None


def get_intent_classifier(
    strategy_type: ClassificationStrategyType = ClassificationStrategyType.HYBRID,
    **kwargs
) -> IntentClassifier:
    """
    获取全局意图分类器

    Args:
        strategy_type: 策略类型（默认混合策略）
        **kwargs: 其他参数

    Returns:
        IntentClassifier 实例
    """
    global _intent_classifier

    if _intent_classifier is None:
        strategy = IntentClassifierFactory.create(strategy_type)
        _intent_classifier = IntentClassifier(strategy=strategy, **kwargs)

    return _intent_classifier


def reset_intent_classifier():
    """重置全局意图分类器（用于测试）"""
    global _intent_classifier
    _intent_classifier = None


# 全局问题分解器实例
_query_decomposer: Optional[QueryDecomposer] = None


def get_query_decomposer(
    strategy_type: DecompositionStrategyType = DecompositionStrategyType.HYBRID,
    **kwargs
) -> QueryDecomposer:
    """
    获取全局问题分解器

    Args:
        strategy_type: 策略类型（默认混合策略）
        **kwargs: 其他参数

    Returns:
        QueryDecomposer 实例
    """
    global _query_decomposer

    if _query_decomposer is None:
        _query_decomposer = QueryDecomposerFactory.create(strategy_type, **kwargs)

    return _query_decomposer


def reset_query_decomposer():
    """重置全局问题分解器（用于测试）"""
    global _query_decomposer
    _query_decomposer = None


# 全局上下文压缩器实例
_compressor: Optional[ContextCompressor] = None


def get_compressor(
    strategy_type: CompressionStrategyType = CompressionStrategyType.EXTRACTIVE,
    **kwargs
) -> ContextCompressor:
    """
    获取全局上下文压缩器

    Args:
        strategy_type: 压缩策略类型（默认抽取式）
        **kwargs: 其他参数

    Returns:
        ContextCompressor 实例
    """
    global _compressor

    if _compressor is None:
        _compressor = ContextCompressorFactory.create(strategy_type, **kwargs)

    return _compressor


def reset_compressor():
    """重置全局上下文压缩器（用于测试）"""
    global _compressor
    _compressor = None


# 全局自我反思器实例
_reflector: Optional[SelfReflector] = None


def get_reflector(
    strategy_type: ReflectionStrategyType = ReflectionStrategyType.LLM,
    **kwargs
) -> SelfReflector:
    """
    获取全局自我反思器

    Args:
        strategy_type: 反思策略类型（默认 LLM 策略）
        **kwargs: 其他参数

    Returns:
        SelfReflector 实例
    """
    global _reflector

    if _reflector is None:
        _reflector = SelfReflectorFactory.create(strategy_type, **kwargs)

    return _reflector


def reset_reflector():
    """重置全局自我反思器（用于测试）"""
    global _reflector
    _reflector = None
