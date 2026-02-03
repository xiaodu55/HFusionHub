"""
QueryDecomposer 单元测试

测试问题分解器的各种功能
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.core.rag.models import IntentResult, IntentType, ComplexityLevel, DomainType
from app.core.rag.query_decomposer import (
    SubQuestion,
    SubQuestionStatus,
    DecompositionResult,
    QuestionTreeNode,
    LLMDecompositionStrategy,
    RuleDecompositionStrategy,
    HybridDecompositionStrategy,
    QueryDecomposer,
    QueryDecomposerFactory,
    DecompositionStrategyType,
)


# ============================================================================
# 测试数据模型
# ============================================================================

class TestSubQuestion:
    """测试 SubQuestion 数据模型"""

    def test_creation(self):
        """测试创建子问题"""
        q = SubQuestion(
            id="q1",
            content="Python是什么？",
            priority=0,
        )
        assert q.id == "q1"
        assert q.content == "Python是什么？"
        assert q.status == SubQuestionStatus.PENDING
        assert q.dependencies == []

    def test_can_execute_no_deps(self):
        """测试无依赖的子问题可以执行"""
        q = SubQuestion(id="q1", content="test", dependencies=[])
        assert q.can_execute(set()) is True

    def test_can_execute_with_deps_met(self):
        """测试依赖已满足时可以执行"""
        q = SubQuestion(id="q2", content="test", dependencies=["q1"])
        assert q.can_execute({"q1"}) is True

    def test_can_execute_with_deps_not_met(self):
        """测试依赖未满足时不能执行"""
        q = SubQuestion(id="q2", content="test", dependencies=["q1"])
        assert q.can_execute(set()) is False

    def test_can_execute_already_completed(self):
        """测试已完成的子问题不能再次执行"""
        q = SubQuestion(id="q1", content="test", status=SubQuestionStatus.COMPLETED)
        assert q.can_execute(set()) is False

    def test_to_dict(self):
        """测试转换为字典"""
        q = SubQuestion(
            id="q1",
            content="test",
            priority=1,
            dependencies=["q0"],
        )
        d = q.to_dict()
        assert d["id"] == "q1"
        assert d["content"] == "test"
        assert d["priority"] == 1
        assert d["dependencies"] == ["q0"]

    def test_from_dict(self):
        """测试从字典创建"""
        d = {
            "id": "q1",
            "content": "test",
            "priority": 1,
            "dependencies": ["q0"],
            "status": "pending",
        }
        q = SubQuestion.from_dict(d)
        assert q.id == "q1"
        assert q.content == "test"
        assert q.priority == 1
        assert q.dependencies == ["q0"]

    def test_str(self):
        """测试字符串表示"""
        q = SubQuestion(id="q1", content="这是一个很长的问题内容", dependencies=["q0"])
        s = str(q)
        assert "q1" in s
        assert "deps=" in s


class TestDecompositionResult:
    """测试 DecompositionResult 数据模型"""

    def test_creation(self):
        """测试创建分解结果"""
        q1 = SubQuestion(id="q1", content="问题1")
        q2 = SubQuestion(id="q2", content="问题2")

        result = DecompositionResult(
            original_query="原始问题",
            sub_questions=[q1, q2],
            execution_plan=[[q1, q2]],
            strategy_used="rule",
            confidence=0.8,
        )
        assert result.original_query == "原始问题"
        assert len(result.sub_questions) == 2
        assert result.needs_decomposition is True

    def test_single_question_no_decomposition(self):
        """测试单个问题不需要分解"""
        q1 = SubQuestion(id="q1", content="问题1")
        result = DecompositionResult(
            original_query="问题1",
            sub_questions=[q1],
            execution_plan=[[q1]],
            strategy_used="rule",
            confidence=0.9,
        )
        assert result.needs_decomposition is False

    def test_get_next_batch(self):
        """测试获取下一批可执行的子问题"""
        q1 = SubQuestion(id="q1", content="问题1")
        q2 = SubQuestion(id="q2", content="问题2", dependencies=["q1"])
        q3 = SubQuestion(id="q3", content="问题3")

        result = DecompositionResult(
            original_query="test",
            sub_questions=[q1, q2, q3],
            execution_plan=[[q1, q3], [q2]],
            strategy_used="rule",
            confidence=0.8,
        )

        # 第一批：q1 和 q3 可以执行
        batch = result.get_next_batch(set())
        batch_ids = {q.id for q in batch}
        assert "q1" in batch_ids or "q3" in batch_ids

        # 第二批：q2 可以执行
        batch = result.get_next_batch({"q1", "q3"})
        assert len(batch) == 1
        assert batch[0].id == "q2"

    def test_update_status(self):
        """测试更新状态"""
        q1 = SubQuestion(id="q1", content="问题1")
        result = DecompositionResult(
            original_query="test",
            sub_questions=[q1],
            execution_plan=[[q1]],
            strategy_used="rule",
            confidence=0.8,
        )

        result.update_status("q1", SubQuestionStatus.COMPLETED, "答案")
        assert q1.status == SubQuestionStatus.COMPLETED
        assert q1.answer == "答案"


class TestQuestionTreeNode:
    """测试 QuestionTreeNode"""

    def test_get_execution_order(self):
        """测试获取执行顺序"""
        q1 = SubQuestion(id="q1", content="问题1")
        q2 = SubQuestion(id="q2", content="问题2")
        q3 = SubQuestion(id="q3", content="问题3")

        node1 = QuestionTreeNode(question=q1)
        node2 = QuestionTreeNode(question=q2)
        node3 = QuestionTreeNode(question=q3)

        node1.children = [node2, node3]

        order = node1.get_execution_order()
        assert len(order) == 2
        assert order[0][0].id == "q1"
        assert len(order[1]) == 2


# ============================================================================
# 测试分解策略
# ============================================================================

class TestRuleDecompositionStrategy:
    """测试规则分解策略"""

    @pytest.mark.asyncio
    async def test_simple_query_no_decomposition(self):
        """测试简单查询不分解"""
        strategy = RuleDecompositionStrategy()
        result = await strategy.decompose("Python是什么？")
        assert result.needs_decomposition is False

    @pytest.mark.asyncio
    async def test_comparison_query_decompose(self):
        """测试比较查询分解"""
        strategy = RuleDecompositionStrategy()
        result = await strategy.decompose("Python和Java有什么区别？")
        assert result.needs_decomposition is True
        assert len(result.sub_questions) == 2

    @pytest.mark.asyncio
    async def test_multiple_triggers(self):
        """测试多个触发词"""
        strategy = RuleDecompositionStrategy()
        result = await strategy.decompose("Python和Java以及C++的区别")
        assert result.needs_decomposition is True

    @pytest.mark.asyncio
    async def test_strategy_used(self):
        """测试策略标识"""
        strategy = RuleDecompositionStrategy()
        result = await strategy.decompose("test")
        assert result.strategy_used == "rule"


class TestLLMDecompositionStrategy:
    """测试 LLM 分解策略"""

    @pytest.mark.asyncio
    async def test_decompose_with_mock_llm(self):
        """测试使用模拟 LLM 分解"""
        # 创建模拟 LLM
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '''
        {
            "needs_decomposition": true,
            "reason": "复杂查询需要分解",
            "sub_questions": [
                {"id": "q1", "content": "子问题1", "priority": 1, "dependencies": []},
                {"id": "q2", "content": "子问题2", "priority": 2, "dependencies": ["q1"]}
            ]
        }
        '''
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        strategy = LLMDecompositionStrategy(llm=mock_llm)
        result = await strategy.decompose("复杂问题")

        assert result.needs_decomposition is True
        assert len(result.sub_questions) == 2
        assert result.strategy_used == "llm"

    @pytest.mark.asyncio
    async def test_decompose_no_decomposition_needed(self):
        """测试不需要分解的情况"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '''
        {
            "needs_decomposition": false,
            "reason": "简单查询"
        }
        '''
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        strategy = LLMDecompositionStrategy(llm=mock_llm)
        result = await strategy.decompose("简单问题")

        assert result.needs_decomposition is False
        assert len(result.sub_questions) == 1

    @pytest.mark.asyncio
    async def test_parse_invalid_json(self):
        """测试解析无效 JSON"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "invalid json"
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        strategy = LLMDecompositionStrategy(llm=mock_llm)
        result = await strategy.decompose("test")

        # 应该返回原始查询
        assert len(result.sub_questions) == 1


class TestHybridDecompositionStrategy:
    """测试混合分解策略"""

    @pytest.mark.asyncio
    async def test_simple_query_skip(self):
        """测试简单查询直接返回"""
        intent = IntentResult(
            intent=IntentType.FACTUAL,
            complexity=ComplexityLevel.SIMPLE,
            domain=DomainType.GENERAL,
            confidence=0.9,
        )
        strategy = HybridDecompositionStrategy()
        result = await strategy.decompose("Python是什么？", intent_result=intent)

        assert result.needs_decomposition is False
        assert result.strategy_used == "hybrid"

    @pytest.mark.asyncio
    async def test_complex_query_uses_llm(self):
        """测试复杂查询使用 LLM"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '''
        {
            "needs_decomposition": true,
            "reason": "复杂查询",
            "sub_questions": [
                {"id": "q1", "content": "子问题1", "priority": 1, "dependencies": []},
                {"id": "q2", "content": "子问题2", "priority": 2, "dependencies": []}
            ]
        }
        '''
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        intent = IntentResult(
            intent=IntentType.COMPARISON,
            complexity=ComplexityLevel.COMPLEX,
            domain=DomainType.GENERAL,
            confidence=0.8,
        )
        strategy = HybridDecompositionStrategy(llm=mock_llm)
        result = await strategy.decompose("复杂比较问题", intent_result=intent)

        assert result.needs_decomposition is True
        assert "hybrid" in result.strategy_used


# ============================================================================
# 测试主类和工厂
# ============================================================================

class TestQueryDecomposer:
    """测试 QueryDecomposer 主类"""

    def test_creation(self):
        """测试创建分解器"""
        decomposer = QueryDecomposer()
        assert decomposer.cache_enabled is True
        assert decomposer.cache_ttl == 3600

    @pytest.mark.asyncio
    async def test_decompose_simple(self):
        """测试分解简单查询"""
        # 使用规则策略避免调用真实 LLM
        strategy = RuleDecompositionStrategy()
        decomposer = QueryDecomposer(strategy=strategy)
        result = await decomposer.decompose("Python是什么？")

        assert result.original_query == "Python是什么？"
        assert len(result.sub_questions) == 1

    @pytest.mark.asyncio
    async def test_cache(self):
        """测试缓存功能"""
        strategy = RuleDecompositionStrategy()
        decomposer = QueryDecomposer(strategy=strategy, cache_enabled=True)

        # 第一次调用
        result1 = await decomposer.decompose("test query")

        # 第二次调用应该使用缓存
        result2 = await decomposer.decompose("test query")

        assert result1 is result2

    @pytest.mark.asyncio
    async def test_clear_cache(self):
        """测试清空缓存"""
        strategy = RuleDecompositionStrategy()
        decomposer = QueryDecomposer(strategy=strategy, cache_enabled=True)
        await decomposer.decompose("test query")
        decomposer.clear_cache()
        assert len(decomposer._cache) == 0


class TestQueryDecomposerFactory:
    """测试 QueryDecomposerFactory"""

    def test_create_hybrid(self):
        """测试创建混合策略分解器"""
        decomposer = QueryDecomposerFactory.create(DecompositionStrategyType.HYBRID)
        assert isinstance(decomposer, QueryDecomposer)
        assert isinstance(decomposer.strategy, HybridDecompositionStrategy)

    def test_create_rule(self):
        """测试创建规则策略分解器"""
        decomposer = QueryDecomposerFactory.create(DecompositionStrategyType.RULE)
        assert isinstance(decomposer.strategy, RuleDecompositionStrategy)

    def test_create_llm(self):
        """测试创建 LLM 策略分解器"""
        decomposer = QueryDecomposerFactory.create(DecompositionStrategyType.LLM)
        assert isinstance(decomposer.strategy, LLMDecompositionStrategy)

    def test_create_invalid_type(self):
        """测试创建无效策略类型"""
        with pytest.raises(ValueError):
            QueryDecomposerFactory.create("invalid_type")


# ============================================================================
# 测试全局实例
# ============================================================================

class TestGlobalInstance:
    """测试全局实例"""

    def setup_method(self):
        """重置全局实例"""
        from app.core.rag import reset_query_decomposer
        reset_query_decomposer()

    def test_get_query_decomposer(self):
        """测试获取全局分解器"""
        from app.core.rag import get_query_decomposer
        decomposer = get_query_decomposer()
        assert isinstance(decomposer, QueryDecomposer)

    def test_singleton(self):
        """测试单例模式"""
        from app.core.rag import get_query_decomposer
        d1 = get_query_decomposer()
        d2 = get_query_decomposer()
        assert d1 is d2


# ============================================================================
# 测试集成
# ============================================================================

class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_end_to_end_simple(self):
        """测试端到端流程：简单查询"""
        # 使用规则策略避免调用真实 LLM
        strategy = RuleDecompositionStrategy()
        decomposer = QueryDecomposer(strategy=strategy)

        result = await decomposer.decompose("Python是什么？")
        assert result.original_query == "Python是什么？"
        assert isinstance(result.sub_questions, list)

    @pytest.mark.asyncio
    async def test_end_to_end_comparison(self):
        """测试端到端流程：比较查询"""
        strategy = RuleDecompositionStrategy()
        decomposer = QueryDecomposer(strategy=strategy)

        result = await decomposer.decompose("Python和Java有什么区别？")
        assert result.needs_decomposition is True
        assert len(result.sub_questions) == 2

    @pytest.mark.asyncio
    async def test_execution_plan(self):
        """测试执行计划生成"""
        q1 = SubQuestion(id="q1", content="问题1")
        q2 = SubQuestion(id="q2", content="问题2", dependencies=["q1"])

        result = DecompositionResult(
            original_query="test",
            sub_questions=[q1, q2],
            execution_plan=[[q1], [q2]],
            strategy_used="test",
            confidence=0.8,
        )

        assert len(result.execution_plan) == 2
        assert result.max_depth == 1
        assert result.parallel_groups == 2
