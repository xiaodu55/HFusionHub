"""
Intent Classifier Tests - 意图分类器单元测试

测试内容：
- 数据模型测试
- 分类策略测试
- 工厂类测试
- 主类测试
- 集成测试
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.rag import get_intent_classifier, reset_intent_classifier
from app.core.rag.intent_classifier import ClassificationStrategyType, IntentClassifier, IntentClassifierFactory
from app.core.rag.models import ComplexityLevel, DomainType, IntentResult, IntentType
from app.core.rag.strategies import (
    HybridClassificationStrategy,
    LLMClassificationStrategy,
    RuleClassificationStrategy,
)

# ==================== 数据模型测试 ====================

class TestIntentResult:
    """IntentResult 数据模型测试"""

    def test_intent_result_creation(self):
        """测试 IntentResult 创建"""
        result = IntentResult(
            intent=IntentType.FACTUAL,
            complexity=ComplexityLevel.SIMPLE,
            domain=DomainType.TECH,
            confidence=0.8,
            entities=["Python"],
            reasoning="测试推理"
        )

        assert result.intent == IntentType.FACTUAL
        assert result.complexity == ComplexityLevel.SIMPLE
        assert result.domain == DomainType.TECH
        assert result.confidence == 0.8
        assert result.entities == ["Python"]
        assert result.reasoning == "测试推理"

    def test_should_decompose(self):
        """测试 should_decompose 方法"""
        # 简单问题不需要分解
        simple = IntentResult(
            intent=IntentType.FACTUAL,
            complexity=ComplexityLevel.SIMPLE,
            domain=DomainType.GENERAL,
            confidence=0.8
        )
        assert simple.should_decompose() is False

        # 复杂问题需要分解
        complex_query = IntentResult(
            intent=IntentType.COMPARISON,
            complexity=ComplexityLevel.COMPLEX,
            domain=DomainType.GENERAL,
            confidence=0.8
        )
        assert complex_query.should_decompose() is True

    def test_needs_tool(self):
        """测试 needs_tool 方法"""
        # 操作指令需要工具
        operation = IntentResult(
            intent=IntentType.OPERATION,
            complexity=ComplexityLevel.SIMPLE,
            domain=DomainType.GENERAL,
            confidence=0.8
        )
        assert operation.needs_tool() is True

        # 其他意图不需要工具
        factual = IntentResult(
            intent=IntentType.FACTUAL,
            complexity=ComplexityLevel.SIMPLE,
            domain=DomainType.GENERAL,
            confidence=0.8
        )
        assert factual.needs_tool() is False

    def test_is_direct_llm(self):
        """测试 is_direct_llm 方法"""
        # 闲聊直接用 LLM
        chitchat = IntentResult(
            intent=IntentType.CHITCHAT,
            complexity=ComplexityLevel.SIMPLE,
            domain=DomainType.GENERAL,
            confidence=0.8
        )
        assert chitchat.is_direct_llm() is True

        # 其他意图需要检索
        factual = IntentResult(
            intent=IntentType.FACTUAL,
            complexity=ComplexityLevel.SIMPLE,
            domain=DomainType.GENERAL,
            confidence=0.8
        )
        assert factual.is_direct_llm() is False

    def test_to_dict(self):
        """测试 to_dict 方法"""
        result = IntentResult(
            intent=IntentType.FACTUAL,
            complexity=ComplexityLevel.SIMPLE,
            domain=DomainType.TECH,
            confidence=0.8,
            entities=["Python"],
            reasoning="测试"
        )

        data = result.to_dict()

        assert data["intent"] == "factual"
        assert data["complexity"] == "simple"
        assert data["domain"] == "tech"
        assert data["confidence"] == 0.8
        assert data["entities"] == ["Python"]

    def test_from_dict(self):
        """测试 from_dict 方法"""
        data = {
            "intent": "factual",
            "complexity": "simple",
            "domain": "tech",
            "confidence": 0.8,
            "entities": ["Python"],
            "reasoning": "测试"
        }

        result = IntentResult.from_dict(data)

        assert result.intent == IntentType.FACTUAL
        assert result.complexity == ComplexityLevel.SIMPLE
        assert result.domain == DomainType.TECH
        assert result.confidence == 0.8

    def test_str_representation(self):
        """测试字符串表示"""
        result = IntentResult(
            intent=IntentType.FACTUAL,
            complexity=ComplexityLevel.SIMPLE,
            domain=DomainType.TECH,
            confidence=0.8
        )

        str_repr = str(result)
        assert "factual" in str_repr
        assert "simple" in str_repr
        assert "0.80" in str_repr


# ==================== 分类策略测试 ====================

class TestRuleClassificationStrategy:
    """RuleClassificationStrategy 测试"""

    @pytest.fixture
    def strategy(self):
        return RuleClassificationStrategy()

    @pytest.mark.asyncio
    async def test_classify_factual_query(self, strategy):
        """测试事实查询分类"""
        result = await strategy.classify("Python是什么？")

        assert result.intent == IntentType.FACTUAL
        assert result.confidence > 0

    @pytest.mark.asyncio
    async def test_classify_comparison_query(self, strategy):
        """测试比较查询分类"""
        result = await strategy.classify("Python和Java有什么区别？")

        assert result.intent == IntentType.COMPARISON

    @pytest.mark.asyncio
    async def test_classify_summary_query(self, strategy):
        """测试总结查询分类"""
        result = await strategy.classify("总结一下这篇文章")

        assert result.intent == IntentType.SUMMARY

    @pytest.mark.asyncio
    async def test_classify_operation_query(self, strategy):
        """测试操作指令分类"""
        result = await strategy.classify("帮我创建一个知识库")

        assert result.intent == IntentType.OPERATION

    @pytest.mark.asyncio
    async def test_classify_chitchat_query(self, strategy):
        """测试闲聊分类"""
        result = await strategy.classify("你好")

        assert result.intent == IntentType.CHITCHAT

    @pytest.mark.asyncio
    async def test_classify_complex_query(self, strategy):
        """测试复杂查询分类"""
        result = await strategy.classify(
            "比较Python和Java的优缺点，以及它们各自适合什么场景？"
        )

        assert result.complexity == ComplexityLevel.COMPLEX

    @pytest.mark.asyncio
    async def test_classify_medium_query(self, strategy):
        """测试中等复杂度查询分类"""
        result = await strategy.classify("Python和Java有什么区别？")

        assert result.complexity == ComplexityLevel.MEDIUM

    @pytest.mark.asyncio
    async def test_classify_tech_domain(self, strategy):
        """测试技术领域识别"""
        result = await strategy.classify("Python是什么编程语言？")

        assert result.domain == DomainType.TECH

    @pytest.mark.asyncio
    async def test_classify_business_domain(self, strategy):
        """测试业务领域识别"""
        result = await strategy.classify("本月销售额是多少？")

        assert result.domain == DomainType.BUSINESS

    def test_strategy_name(self, strategy):
        """测试策略名称"""
        assert strategy.get_strategy_name() == "rule"


class TestLLMClassificationStrategy:
    """LLMClassificationStrategy 测试"""

    @pytest.fixture
    def mock_llm(self):
        """Mock LLM 实例"""
        llm = AsyncMock()
        llm.chat = AsyncMock(return_value=MagicMock(
            content='{"intent": "factual", "complexity": "simple", "domain": "tech", "confidence": 0.9, "entities": ["Python"], "reasoning": "测试"}'
        ))
        return llm

    @pytest.fixture
    def strategy(self, mock_llm):
        return LLMClassificationStrategy(llm=mock_llm)

    @pytest.mark.asyncio
    async def test_classify_with_llm(self, strategy, mock_llm):
        """测试使用 LLM 分类"""
        result = await strategy.classify("Python是什么？")

        assert result.intent == IntentType.FACTUAL
        assert result.complexity == ComplexityLevel.SIMPLE
        assert result.domain == DomainType.TECH
        assert result.confidence == 0.9
        mock_llm.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_classify_with_history(self, strategy, mock_llm):
        """测试带历史的分类"""
        history = [
            {"role": "user", "content": "什么是机器学习？"},
            {"role": "assistant", "content": "机器学习是..."}
        ]

        result = await strategy.classify("它有什么应用？", history=history)

        assert result.intent == IntentType.FACTUAL
        mock_llm.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_hit(self, strategy, mock_llm):
        """测试缓存命中"""
        query = "测试查询"

        # 第一次调用
        result1 = await strategy.classify(query)

        # 第二次调用（应该命中缓存）
        result2 = await strategy.classify(query)

        assert result1 == result2
        # LLM 只应该被调用一次
        assert mock_llm.chat.call_count == 1

    def test_strategy_name(self, strategy):
        """测试策略名称"""
        assert strategy.get_strategy_name() == "llm"


class TestHybridClassificationStrategy:
    """HybridClassificationStrategy 测试"""

    @pytest.fixture
    def strategy(self):
        return HybridClassificationStrategy()

    @pytest.mark.asyncio
    async def test_simple_query_uses_rule(self, strategy):
        """测试简单查询使用规则策略"""
        # 简单查询，规则应该有高置信度
        result = await strategy.classify("你好")

        assert result.intent == IntentType.CHITCHAT

    @pytest.mark.asyncio
    async def test_strategy_name(self, strategy):
        """测试策略名称"""
        assert strategy.get_strategy_name() == "hybrid"


# ==================== 工厂类测试 ====================

class TestIntentClassifierFactory:
    """IntentClassifierFactory 测试"""

    def test_create_rule_strategy(self):
        """测试创建规则策略"""
        strategy = IntentClassifierFactory.create(
            ClassificationStrategyType.RULE
        )

        assert isinstance(strategy, RuleClassificationStrategy)
        assert strategy.get_strategy_name() == "rule"

    def test_create_llm_strategy(self):
        """测试创建 LLM 策略"""
        mock_llm = AsyncMock()

        strategy = IntentClassifierFactory.create(
            ClassificationStrategyType.LLM,
            llm=mock_llm
        )

        assert isinstance(strategy, LLMClassificationStrategy)
        assert strategy.get_strategy_name() == "llm"

    def test_create_hybrid_strategy(self):
        """测试创建混合策略"""
        strategy = IntentClassifierFactory.create(
            ClassificationStrategyType.HYBRID
        )

        assert isinstance(strategy, HybridClassificationStrategy)
        assert strategy.get_strategy_name() == "hybrid"

    def test_create_unknown_strategy(self):
        """测试创建未知策略"""
        with pytest.raises(ValueError):
            IntentClassifierFactory.create("unknown")

    def test_get_available_strategies(self):
        """测试获取可用策略"""
        strategies = IntentClassifierFactory.get_available_strategies()

        assert "llm" in strategies
        assert "rule" in strategies
        assert "hybrid" in strategies


# ==================== 主类测试 ====================

class TestIntentClassifier:
    """IntentClassifier 主类测试"""

    @pytest.fixture
    def classifier(self):
        return IntentClassifier(
            strategy=IntentClassifierFactory.create(
                ClassificationStrategyType.RULE
            )
        )

    @pytest.mark.asyncio
    async def test_classify(self, classifier):
        """测试分类功能"""
        result = await classifier.classify("Python是什么？")

        assert isinstance(result, IntentResult)
        assert result.intent == IntentType.FACTUAL

    @pytest.mark.asyncio
    async def test_classify_with_cache(self, classifier):
        """测试带缓存的分类"""
        query = "测试查询"

        # 第一次调用
        result1 = await classifier.classify(query)

        # 第二次调用（应该命中缓存）
        result2 = await classifier.classify(query)

        assert result1 == result2
        assert classifier.get_cache_stats()["valid"] == 1

    def test_clear_cache(self, classifier):
        """测试清空缓存"""
        classifier.clear_cache()
        stats = classifier.get_cache_stats()

        assert stats["total"] == 0
        assert stats["valid"] == 0

    def test_get_strategy_name(self, classifier):
        """测试获取策略名称"""
        assert classifier.get_strategy_name() == "rule"


# ==================== 全局实例测试 ====================

class TestGlobalInstance:
    """全局实例测试"""

    def setup_method(self):
        """每个测试前重置"""
        reset_intent_classifier()

    def test_get_intent_classifier(self):
        """测试获取全局分类器"""
        classifier = get_intent_classifier()

        assert classifier is not None
        assert isinstance(classifier, IntentClassifier)

    def test_get_intent_classifier_singleton(self):
        """测试单例模式"""
        classifier1 = get_intent_classifier()
        classifier2 = get_intent_classifier()

        assert classifier1 is classifier2

    def test_reset_intent_classifier(self):
        """测试重置分类器"""
        classifier1 = get_intent_classifier()
        reset_intent_classifier()
        classifier2 = get_intent_classifier()

        assert classifier1 is not classifier2


# ==================== 集成测试 ====================

class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_end_to_end_rule(self):
        """端到端测试（规则策略）"""
        classifier = IntentClassifier(
            strategy=IntentClassifierFactory.create(
                ClassificationStrategyType.RULE
            )
        )

        # 测试各种查询
        test_cases = [
            ("Python是什么？", IntentType.FACTUAL),
            ("Python和Java有什么区别？", IntentType.COMPARISON),
            ("总结一下这篇文章", IntentType.SUMMARY),
            ("帮我创建知识库", IntentType.OPERATION),
            ("你好", IntentType.CHITCHAT),
        ]

        for query, expected_intent in test_cases:
            result = await classifier.classify(query)
            assert result.intent == expected_intent, f"Failed for query: {query}"

    @pytest.mark.asyncio
    async def test_intent_driven_processing(self):
        """测试意图驱动的处理流程"""
        classifier = IntentClassifier(
            strategy=IntentClassifierFactory.create(
                ClassificationStrategyType.RULE
            )
        )

        # 事实查询应该需要检索
        factual_result = await classifier.classify("Python是什么？")
        assert factual_result.needs_retrieval() is True
        assert factual_result.should_decompose() is False

        # 复杂查询应该需要分解
        complex_result = await classifier.classify(
            "比较Python和Java的优缺点，以及它们各自适合什么场景？"
        )
        assert complex_result.should_decompose() is True

        # 闲聊应该直接用 LLM
        chitchat_result = await classifier.classify("你好")
        assert chitchat_result.is_direct_llm() is True
        assert chitchat_result.needs_retrieval() is False


def test_classify_sync_shares_bounded_executor():
    """M13: classify_sync 的运行中事件循环分支复用进程级共享线程池（4 workers），
    不再每次调用新建 ThreadPoolExecutor 造成线程泄漏。"""
    import concurrent.futures

    from app.core.rag.intent_classifier import _get_classify_executor

    executor = _get_classify_executor()
    # 单例：两次获取同一实例（泄漏修复前每次调用都新建）
    assert _get_classify_executor() is executor
    assert isinstance(executor, concurrent.futures.ThreadPoolExecutor)
    assert executor._max_workers == 4

    classifier = IntentClassifier()
    result = classifier.classify_sync("帮我查一下订单")
    assert result is not None
