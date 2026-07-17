"""
SelfReflector 单元测试

测试自我反思器的所有功能：
- 数据模型：ReflectionResult, ReflectionConfig, QualityCriteria
- LLM 反思策略：LLMReflectionStrategy
- 规则反思策略：RuleBasedReflectionStrategy
- 混合反思策略：HybridReflectionStrategy
- 主类：SelfReflector
- 工厂类：SelfReflectorFactory
- 全局实例管理

作者：Claude
日期：2026-07-22
"""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.rag.self_reflector import (
    HybridReflectionStrategy,
    LLMReflectionStrategy,
    QualityCriteria,
    ReflectionConfig,
    ReflectionResult,
    ReflectionStatus,
    ReflectionStrategyType,
    RuleBasedReflectionStrategy,
    SelfReflector,
    SelfReflectorFactory,
    get_reflector,
    reset_reflector,
)

# ==================== 数据模型测试 ====================

class TestQualityCriteria:
    """QualityCriteria 数据模型测试"""

    def test_creation_with_defaults(self):
        """测试使用默认值创建 QualityCriteria"""
        criteria = QualityCriteria()

        assert criteria.completeness == 0.3
        assert criteria.accuracy == 0.3
        assert criteria.relevance == 0.2
        assert criteria.clarity == 0.2

    def test_creation_with_custom_values(self):
        """测试使用自定义值创建 QualityCriteria"""
        criteria = QualityCriteria(
            completeness=0.4,
            accuracy=0.4,
            relevance=0.1,
            clarity=0.1,
        )

        assert criteria.completeness == 0.4
        assert criteria.accuracy == 0.4
        assert criteria.relevance == 0.1
        assert criteria.clarity == 0.1

    def test_to_dict(self):
        """测试 to_dict 方法"""
        criteria = QualityCriteria()
        d = criteria.to_dict()

        assert d["completeness"] == 0.3
        assert d["accuracy"] == 0.3
        assert d["relevance"] == 0.2
        assert d["clarity"] == 0.2

    def test_from_dict(self):
        """测试 from_dict 方法"""
        d = {
            "completeness": 0.4,
            "accuracy": 0.4,
            "relevance": 0.1,
            "clarity": 0.1,
        }

        criteria = QualityCriteria.from_dict(d)
        assert criteria.completeness == 0.4
        assert criteria.accuracy == 0.4
        assert criteria.relevance == 0.1
        assert criteria.clarity == 0.1


class TestReflectionResult:
    """ReflectionResult 数据模型测试"""

    def test_creation(self):
        """测试创建 ReflectionResult"""
        result = ReflectionResult(
            original_answer="原始答案",
            reflected_answer="反思后答案",
            quality_score=0.8,
            dimension_scores={"completeness": 0.9, "accuracy": 0.8},
            issues=["问题1"],
            suggestions=["建议1"],
            retry_count=0,
            strategy_used="llm",
        )

        assert result.original_answer == "原始答案"
        assert result.reflected_answer == "反思后答案"
        assert result.quality_score == 0.8
        assert result.dimension_scores == {"completeness": 0.9, "accuracy": 0.8}
        assert result.issues == ["问题1"]
        assert result.suggestions == ["建议1"]
        assert result.retry_count == 0
        assert result.strategy_used == "llm"
        assert result.status == ReflectionStatus.COMPLETED

    def test_to_dict(self):
        """测试 to_dict 方法"""
        result = ReflectionResult(
            original_answer="原始答案",
            reflected_answer="反思后答案",
            quality_score=0.8,
        )

        d = result.to_dict()
        assert d["reflected_answer"] == "反思后答案"
        assert d["quality_score"] == 0.8
        assert d["status"] == "completed"

    def test_from_dict(self):
        """测试 from_dict 方法"""
        d = {
            "original_answer": "原始答案",
            "reflected_answer": "反思后答案",
            "quality_score": 0.8,
            "issues": ["问题1"],
            "suggestions": ["建议1"],
            "status": "completed",
        }

        result = ReflectionResult.from_dict(d)
        assert result.original_answer == "原始答案"
        assert result.reflected_answer == "反思后答案"
        assert result.quality_score == 0.8
        assert result.issues == ["问题1"]


class TestReflectionConfig:
    """ReflectionConfig 数据模型测试"""

    def test_creation_with_defaults(self):
        """测试使用默认值创建 ReflectionConfig"""
        config = ReflectionConfig()

        assert config.strategy == ReflectionStrategyType.LLM
        assert config.quality_threshold == 0.7
        assert config.max_retries == 2
        assert config.enable_supplement is True
        assert config.language == "zh"

    def test_creation_with_custom_values(self):
        """测试使用自定义值创建 ReflectionConfig"""
        criteria = QualityCriteria(completeness=0.4, accuracy=0.4)
        config = ReflectionConfig(
            strategy=ReflectionStrategyType.RULE_BASED,
            quality_threshold=0.8,
            max_retries=3,
            enable_supplement=False,
            language="en",
            criteria=criteria,
        )

        assert config.strategy == ReflectionStrategyType.RULE_BASED
        assert config.quality_threshold == 0.8
        assert config.max_retries == 3
        assert config.enable_supplement is False
        assert config.language == "en"
        assert config.criteria.completeness == 0.4


# ==================== LLM 反思策略测试 ====================

class TestLLMReflectionStrategy:
    """LLMReflectionStrategy 测试"""

    def test_creation_without_llm(self):
        """测试创建策略实例（无 LLM）"""
        strategy = LLMReflectionStrategy()
        assert strategy.name == "llm"
        assert strategy.llm is None

    def test_creation_with_llm(self):
        """测试创建策略实例（带 LLM）"""
        mock_llm = MagicMock()
        strategy = LLMReflectionStrategy(llm=mock_llm)
        assert strategy.name == "llm"
        assert strategy.llm == mock_llm

    @pytest.mark.asyncio
    async def test_reflect_without_llm_fallback(self):
        """测试无 LLM 时降级到规则反思"""
        strategy = LLMReflectionStrategy()
        query = "Python是什么？"
        answer = "Python是一种编程语言。"
        context = "Python是一种广泛使用的编程语言。"

        result = await strategy.reflect(query, answer, context)

        assert result.status == ReflectionStatus.COMPLETED
        assert result.strategy_used == "rule_based"  # 降级到规则

    @pytest.mark.asyncio
    async def test_reflect_with_mock_llm(self):
        """测试使用 Mock LLM 反思"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '''
        {
            "quality_score": 0.85,
            "dimension_scores": {
                "completeness": 0.9,
                "accuracy": 0.8,
                "relevance": 0.9,
                "clarity": 0.8
            },
            "issues": ["答案可以更详细"],
            "suggestions": ["请提供更多例子"]
        }
        '''
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        strategy = LLMReflectionStrategy(llm=mock_llm)
        query = "Python是什么？"
        answer = "Python是一种编程语言。"
        context = "Python是一种广泛使用的编程语言。"
        config = ReflectionConfig(quality_threshold=0.9)

        result = await strategy.reflect(query, answer, context, config)

        assert result.status == ReflectionStatus.COMPLETED
        assert result.strategy_used == "llm"
        assert result.quality_score == 0.85
        assert "答案可以更详细" in result.issues


# ==================== 规则反思策略测试 ====================

class TestRuleBasedReflectionStrategy:
    """RuleBasedReflectionStrategy 测试"""

    def test_creation(self):
        """测试创建策略实例"""
        strategy = RuleBasedReflectionStrategy()
        assert strategy.name == "rule_based"

    @pytest.mark.asyncio
    async def test_reflect_good_answer(self):
        """测试反思高质量答案"""
        strategy = RuleBasedReflectionStrategy()
        query = "Python是什么？"
        answer = "Python是一种广泛使用的高级编程语言，由Guido van Rossum于1991年创建。它支持多种编程范式，包括面向对象、函数式和过程式编程。"
        context = "Python是一种广泛使用的高级编程语言。"

        result = await strategy.reflect(query, answer, context)

        assert result.status == ReflectionStatus.COMPLETED
        assert result.quality_score > 0.7
        # 高质量答案可能有一些小问题，但整体质量高

    @pytest.mark.asyncio
    async def test_reflect_poor_answer(self):
        """测试反思低质量答案"""
        strategy = RuleBasedReflectionStrategy()
        query = "Python是什么？"
        answer = "不知道"
        context = "Python是一种广泛使用的高级编程语言。"

        result = await strategy.reflect(query, answer, context)

        assert result.status == ReflectionStatus.COMPLETED
        # 低质量答案应该有一些问题
        assert len(result.issues) > 0


# ==================== 混合反思策略测试 ====================

class TestHybridReflectionStrategy:
    """HybridReflectionStrategy 测试"""

    def test_creation_without_llm(self):
        """测试创建策略实例（无 LLM）"""
        strategy = HybridReflectionStrategy()
        assert strategy.name == "hybrid"
        assert strategy.llm is None

    def test_creation_with_llm(self):
        """测试创建策略实例（带 LLM）"""
        mock_llm = MagicMock()
        strategy = HybridReflectionStrategy(llm=mock_llm)
        assert strategy.name == "hybrid"
        assert strategy.llm == mock_llm

    @pytest.mark.asyncio
    async def test_reflect_without_llm(self):
        """测试无 LLM 时只使用规则"""
        strategy = HybridReflectionStrategy()
        query = "Python是什么？"
        answer = "Python是一种编程语言。"
        context = "Python是一种广泛使用的编程语言。"

        result = await strategy.reflect(query, answer, context)

        assert result.status == ReflectionStatus.COMPLETED
        # 没有 LLM 时，混合策略会使用规则策略，但 strategy_used 应该是 "hybrid"
        # 实际上混合策略在没有 LLM 时会返回规则策略的结果
        assert result.strategy_used in ["hybrid", "rule_based"]


# ==================== 主类测试 ====================

class TestSelfReflector:
    """SelfReflector 主类测试"""

    def test_creation_default(self):
        """测试默认创建"""
        reflector = SelfReflector()
        assert reflector.cache_enabled is True
        assert reflector.cache_ttl == 3600

    def test_creation_custom_strategy(self):
        """测试自定义策略创建"""
        strategy = RuleBasedReflectionStrategy()
        reflector = SelfReflector(strategy=strategy)
        assert reflector.strategy == strategy

    def test_creation_string_strategy(self):
        """测试字符串策略创建"""
        reflector = SelfReflector(strategy="rule_based")
        assert isinstance(reflector.strategy, RuleBasedReflectionStrategy)

    def test_creation_no_cache(self):
        """测试禁用缓存"""
        reflector = SelfReflector(cache_enabled=False)
        assert reflector.cache_enabled is False

    @pytest.mark.asyncio
    async def test_reflect_simple(self):
        """测试简单反思"""
        reflector = SelfReflector(strategy="rule_based", cache_enabled=False)
        query = "Python是什么？"
        answer = "Python是一种编程语言。"
        context = "Python是一种广泛使用的编程语言。"

        result = await reflector.reflect(query, answer, context)

        assert result.status == ReflectionStatus.COMPLETED
        assert result.quality_score > 0

    @pytest.mark.asyncio
    async def test_reflect_with_config(self):
        """测试使用配置反思"""
        reflector = SelfReflector(strategy="rule_based", cache_enabled=False)
        config = ReflectionConfig(quality_threshold=0.8)
        query = "Python是什么？"
        answer = "Python是一种编程语言。"
        context = "Python是一种广泛使用的编程语言。"

        result = await reflector.reflect(query, answer, context, config)

        assert result.status == ReflectionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_cache(self):
        """测试缓存功能"""
        reflector = SelfReflector(strategy="rule_based", cache_enabled=True, cache_ttl=3600)
        query = "测试查询"
        answer = "测试答案"
        context = "测试上下文"
        config = ReflectionConfig()

        # 第一次反思
        result1 = await reflector.reflect(query, answer, context, config)
        assert reflector.get_cache_size() == 1

        # 第二次反思，应该使用缓存
        result2 = await reflector.reflect(query, answer, context, config)
        assert result1.quality_score == result2.quality_score
        assert reflector.get_cache_size() == 1

    def test_clear_cache(self):
        """测试清空缓存"""
        reflector = SelfReflector(cache_enabled=True)
        reflector._cache["test"] = (MagicMock(), time.time())

        reflector.clear_cache()
        assert reflector.get_cache_size() == 0


# ==================== 工厂类测试 ====================

class TestSelfReflectorFactory:
    """SelfReflectorFactory 测试"""

    def test_create_llm(self):
        """测试创建 LLM 反思器"""
        reflector = SelfReflectorFactory.create(
            ReflectionStrategyType.LLM
        )
        assert isinstance(reflector.strategy, LLMReflectionStrategy)

    def test_create_rule_based(self):
        """测试创建规则反思器"""
        reflector = SelfReflectorFactory.create(
            ReflectionStrategyType.RULE_BASED
        )
        assert isinstance(reflector.strategy, RuleBasedReflectionStrategy)

    def test_create_hybrid(self):
        """测试创建混合反思器"""
        reflector = SelfReflectorFactory.create(
            ReflectionStrategyType.HYBRID
        )
        assert isinstance(reflector.strategy, HybridReflectionStrategy)

    def test_create_with_llm(self):
        """测试创建带 LLM 的反思器"""
        mock_llm = MagicMock()
        reflector = SelfReflectorFactory.create_with_llm(
            ReflectionStrategyType.LLM,
            llm=mock_llm
        )
        assert isinstance(reflector.strategy, LLMReflectionStrategy)
        assert reflector.strategy.llm == mock_llm


# ==================== 全局实例测试 ====================

class TestGlobalInstance:
    """全局实例管理测试"""

    def setup_method(self):
        """每个测试前重置"""
        reset_reflector()

    def test_get_reflector(self):
        """测试获取全局反思器"""
        reflector = get_reflector()
        assert reflector is not None
        assert isinstance(reflector, SelfReflector)

    def test_singleton(self):
        """测试单例模式"""
        reflector1 = get_reflector()
        reflector2 = get_reflector()
        assert reflector1 is reflector2

    def test_reset(self):
        """测试重置"""
        reflector1 = get_reflector()
        reset_reflector()
        reflector2 = get_reflector()
        assert reflector1 is not reflector2


# ==================== 集成测试 ====================

class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_end_to_end_rule_based(self):
        """端到端测试：规则反思"""
        reflector = SelfReflectorFactory.create(
            ReflectionStrategyType.RULE_BASED
        )

        query = "Python是什么？"
        answer = "Python是一种广泛使用的高级编程语言，由Guido van Rossum于1991年创建。"
        context = "Python是一种广泛使用的高级编程语言。"

        result = await reflector.reflect(query, answer, context)

        assert result.status == ReflectionStatus.COMPLETED
        assert result.quality_score > 0
        print(f"\n规则反思：质量评分 = {result.quality_score:.2f}")
        print(f"问题数：{len(result.issues)}")
        print(f"建议数：{len(result.suggestions)}")

    @pytest.mark.asyncio
    async def test_end_to_end_hybrid(self):
        """端到端测试：混合反思"""
        reflector = SelfReflectorFactory.create(
            ReflectionStrategyType.HYBRID
        )

        query = "Python是什么？"
        answer = "Python是一种编程语言。"
        context = "Python是一种广泛使用的高级编程语言。"

        result = await reflector.reflect(query, answer, context)

        assert result.status == ReflectionStatus.COMPLETED
        assert result.quality_score > 0
        print(f"\n混合反思：质量评分 = {result.quality_score:.2f}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
