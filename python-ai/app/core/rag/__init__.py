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
- ConversationMemory: 对话记忆管理
- AgentWorkflow: 工作流引擎
- Utils: 公共工具函数
"""

from typing import Optional

from .adaptive_retrieval import (
    AdaptiveRetrievalPlanner,
    RetrievalPlan,
    get_adaptive_retrieval_planner,
    reset_adaptive_retrieval_planner,
)
from .agent_workflow import (
    BaseWorkflowNode,
    ConditionNode,
    EndNode,
    LoopNode,
    MergeNode,
    NodeResult,
    NodeStatus,
    NodeType,
    ParallelNode,
    StartNode,
    TaskNode,
    Workflow,
    WorkflowBuilder,
    WorkflowConfig,
    WorkflowContext,
    WorkflowEngine,
    WorkflowEvent,
    WorkflowEventType,
    WorkflowFactory,
    WorkflowHistory,
    WorkflowResult,
    WorkflowStatus,
    get_workflow_engine,
    reset_workflow_engine,
)
from .answer_quality_evaluator import (
    AnswerQualityEvaluator,
    AnswerQualityEvaluatorFactory,
    BaseEvaluationStrategy,
    EvaluationConfig,
    EvaluationDimension,
    EvaluationResult,
    EvaluationSample,
    EvaluationStatus,
    EvaluationStrategyType,
    HybridEvaluationStrategy,
    LLMEvaluationStrategy,
    MetricResult,
    RuleBasedEvaluationStrategy,
)
from .context_compressor import (
    AbstractiveCompressionStrategy,
    CompressionConfig,
    CompressionResult,
    CompressionStatus,
    CompressionStrategyType,
    ContextCompressor,
    ContextCompressorFactory,
    ExtractiveCompressionStrategy,
    HybridCompressionStrategy,
    RecursiveCompressionStrategy,
)
from .conversation_memory import (
    BaseMemoryStrategy,
    ConversationMemory,
    ConversationMemoryFactory,
    ConversationSession,
    HybridMemory,
    ImportanceBasedMemory,
    MemoryConfig,
    MemoryEmbedder,
    MemoryEventType,
    MemoryRetriever,
    MemorySearchResponse,
    MemorySearchResult,
    MemoryStats,
    MemoryStorage,
    MemoryStrategyFactory,
    MemoryStrategyType,
    MemoryType,
    Message,
    MessageRole,
    SlidingWindowMemory,
    SummaryMemory,
    TokenBasedMemory,
    get_conversation_memory,
    reset_conversation_memory,
)
from .evaluation import (
    EvaluationCase,
    EvaluationCaseResult,
    RetrievalEvaluator,
)
from .intent_classifier import ClassificationStrategyType, IntentClassifier, IntentClassifierFactory
from .models import ComplexityLevel, DomainType, IntentResult, IntentType
from .multi_turn_strategy import (
    AdaptiveMultiTurnStrategy,
    ContextualStrategy,
    ConversationContext,
    ConversationState,
    ConversationStateManager,
    ConversationTurn,
    ExpansiveStrategy,
    HistoryBasedStrategy,
    MultiTurnManager,
    MultiTurnStrategyFactory,
    RetrievalAdjustment,
    StrategyConfig,
    StrategyType,
    TopicEntityExtractor,
    TopicFocusedStrategy,
    TurnRole,
    get_manager,
    reset_manager,
)
from .observability import (
    RetrievalTrace,
    RetrievalTraceStore,
    get_trace_store,
    reset_trace_store,
)
from .postprocessor import Postprocessor, ProcessedResult, get_postprocessor
from .query_decomposer import (
    DecompositionResult,
    DecompositionStrategy,
    DecompositionStrategyType,
    HybridDecompositionStrategy,
    LLMDecompositionStrategy,
    QueryDecomposer,
    QueryDecomposerFactory,
    QuestionTreeNode,
    RuleDecompositionStrategy,
    SubQuestion,
    SubQuestionStatus,
)
from .query_rewriter import QueryRewriter, RewriteResult, get_query_rewriter
from .query_router import (
    ChannelConfig,
    ChannelType,
    KeywordChannel,
    MergedResult,
    QueryRouter,
    QueryRouterFactory,
    QueryType,
    RouteResult,
    RouteStrategy,
    SearchResult,
    VectorChannel,
    get_router,
    reset_router,
)
from .retriever import MultiChannelRetriever, RetrievalResult, get_retriever
from .self_reflector import (
    HybridReflectionStrategy,
    LLMReflectionStrategy,
    QualityCriteria,
    QualityDimension,
    ReflectionConfig,
    ReflectionResult,
    ReflectionStatus,
    ReflectionStrategyType,
    RuleBasedReflectionStrategy,
    SelfReflector,
    SelfReflectorFactory,
)
from .strategies import (
    ClassificationStrategy,
    HybridClassificationStrategy,
    LLMClassificationStrategy,
    RuleClassificationStrategy,
)
from .utils import (
    calculate_text_similarity,
    estimate_tokens,
    extract_key_phrases,
    split_sentences,
    truncate_text,
)

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
    "RetrievalPlan",
    "AdaptiveRetrievalPlanner",
    "get_adaptive_retrieval_planner",
    "reset_adaptive_retrieval_planner",
    "RetrievalTrace",
    "RetrievalTraceStore",
    "get_trace_store",
    "reset_trace_store",
    "EvaluationCase",
    "EvaluationCaseResult",
    "RetrievalEvaluator",
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
    # 答案质量评估器
    "AnswerQualityEvaluator",
    "AnswerQualityEvaluatorFactory",
    "EvaluationStrategyType",
    "EvaluationDimension",
    "EvaluationStatus",
    "EvaluationSample",
    "EvaluationResult",
    "MetricResult",
    "EvaluationConfig",
    "BaseEvaluationStrategy",
    "RuleBasedEvaluationStrategy",
    "LLMEvaluationStrategy",
    "HybridEvaluationStrategy",
    "get_evaluator",
    "reset_evaluator",
    # 多模态RAG
    # 对话记忆管理
    "ConversationMemory",
    "ConversationMemoryFactory",
    "MemoryType",
    "MemoryStrategyType",
    "MessageRole",
    "MemoryEventType",
    "Message",
    "ConversationSession",
    "MemoryConfig",
    "MemorySearchResult",
    "MemorySearchResponse",
    "MemoryStats",
    "BaseMemoryStrategy",
    "SlidingWindowMemory",
    "TokenBasedMemory",
    "SummaryMemory",
    "ImportanceBasedMemory",
    "HybridMemory",
    "MemoryStrategyFactory",
    "MemoryEmbedder",
    "MemoryStorage",
    "MemoryRetriever",
    "get_conversation_memory",
    "reset_conversation_memory",
    # 工作流引擎
    "Workflow",
    "WorkflowEngine",
    "WorkflowBuilder",
    "WorkflowFactory",
    "WorkflowStatus",
    "NodeType",
    "NodeStatus",
    "WorkflowEventType",
    "WorkflowContext",
    "NodeResult",
    "WorkflowResult",
    "WorkflowConfig",
    "WorkflowEvent",
    "WorkflowHistory",
    "BaseWorkflowNode",
    "StartNode",
    "EndNode",
    "TaskNode",
    "ConditionNode",
    "ParallelNode",
    "LoopNode",
    "MergeNode",
    "get_workflow_engine",
    "reset_workflow_engine",
]


# 全局意图分类器实例
_intent_classifier: IntentClassifier | None = None


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
_query_decomposer: QueryDecomposer | None = None


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
_compressor: ContextCompressor | None = None


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
_reflector: SelfReflector | None = None


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


# 全局答案质量评估器实例
_evaluator: Optional["AnswerQualityEvaluator"] = None


def get_evaluator(
    strategy_type: EvaluationStrategyType = EvaluationStrategyType.HYBRID,
    **kwargs
) -> "AnswerQualityEvaluator":
    """
    获取全局答案质量评估器

    Args:
        strategy_type: 策略类型（默认混合策略）
        **kwargs: 其他参数

    Returns:
        答案质量评估器实例
    """
    global _evaluator

    if _evaluator is None:
        _evaluator = AnswerQualityEvaluatorFactory.create(strategy_type, **kwargs)

    return _evaluator


def reset_evaluator():
    """重置全局答案质量评估器（用于测试）"""
    global _evaluator
    _evaluator = None


# 全局 ConversationMemory 实例
_conversation_memory: Optional["ConversationMemory"] = None


def get_conversation_memory_instance(
    config: Optional["MemoryConfig"] = None
) -> "ConversationMemory":
    """
    获取全局 ConversationMemory 实例

    Args:
        config: 记忆配置

    Returns:
        ConversationMemory 实例
    """
    global _conversation_memory

    if _conversation_memory is None:
        _conversation_memory = ConversationMemoryFactory.create(config)

    return _conversation_memory


def reset_conversation_memory_instance():
    """重置全局 ConversationMemory（用于测试）"""
    global _conversation_memory
    if _conversation_memory:
        _conversation_memory.clear_all()
    _conversation_memory = None


# WorkflowEngine 全局单例统一由 agent_workflow.get_workflow_engine /
# reset_workflow_engine 提供（此前此处重复实现了一份 instance 变体，无任何引用）
