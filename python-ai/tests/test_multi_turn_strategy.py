# Copyright (c) 2026 HFusionHub. All rights reserved.
"""
MultiTurnStrategy 模块单元测试

覆盖：
- 数据模型验证
- 对话状态管理
- 话题和实体提取
- 多种检索策略
- 工厂类
- 全局实例管理
"""

import pytest
from datetime import datetime
from app.core.rag.multi_turn_strategy import (
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
    MultiTurnManager,
    MultiTurnStrategyFactory,
    get_manager,
    reset_manager,
)


# =============================================================================
# 数据模型测试
# =============================================================================

class TestConversationTurn:
    """ConversationTurn 数据模型测试"""

    def test_create_conversation_turn(self):
        """测试创建对话轮次"""
        turn = ConversationTurn(
            role=TurnRole.USER,
            content="你好",
            metadata={"source": "test"}
        )
        assert turn.role == TurnRole.USER
        assert turn.content == "你好"
        assert turn.metadata == {"source": "test"}

    def test_conversation_turn_to_dict(self):
        """测试转换为字典"""
        turn = ConversationTurn(
            role=TurnRole.ASSISTANT,
            content="你好！有什么可以帮助你的？"
        )
        data = turn.to_dict()
        assert data["role"] == "assistant"
        assert data["content"] == "你好！有什么可以帮助你的？"
        assert "timestamp" in data


class TestConversationContext:
    """ConversationContext 数据模型测试"""

    def test_create_conversation_context(self):
        """测试创建对话上下文"""
        context = ConversationContext(
            conversation_id="test-123",
            state=ConversationState.INIT,
        )
        assert context.conversation_id == "test-123"
        assert context.state == ConversationState.INIT
        assert context.turn_count == 0

    def test_add_turn(self):
        """测试添加轮次"""
        context = ConversationContext(conversation_id="test-123")
        context.add_turn(TurnRole.USER, "你好")
        context.add_turn(TurnRole.ASSISTANT, "你好！")

        assert context.turn_count == 2
        assert context.last_user_turn.content == "你好"
        assert context.last_assistant_turn.content == "你好！"

    def test_get_recent_turns(self):
        """测试获取最近轮次"""
        context = ConversationContext(conversation_id="test-123")
        for i in range(5):
            context.add_turn(TurnRole.USER, f"问题{i}")

        recent = context.get_recent_turns(3)
        assert len(recent) == 3
        assert recent[0].content == "问题2"
        assert recent[2].content == "问题4"

    def test_get_context_window(self):
        """测试获取上下文窗口"""
        context = ConversationContext(conversation_id="test-123")
        context.add_turn(TurnRole.USER, "你好")
        context.add_turn(TurnRole.ASSISTANT, "你好！")
        context.add_turn(TurnRole.USER, "什么是Python？")

        window = context.get_context_window(max_tokens=1000)
        assert "user: 你好" in window
        assert "assistant: 你好！" in window

    def test_last_user_turn(self):
        """测试获取最后一个用户轮次"""
        context = ConversationContext(conversation_id="test-123")
        context.add_turn(TurnRole.ASSISTANT, "你好！")
        context.add_turn(TurnRole.USER, "什么是Python？")

        assert context.last_user_turn.content == "什么是Python？"

    def test_last_assistant_turn(self):
        """测试获取最后一个助手轮次"""
        context = ConversationContext(conversation_id="test-123")
        context.add_turn(TurnRole.USER, "你好")
        context.add_turn(TurnRole.ASSISTANT, "你好！")

        assert context.last_assistant_turn.content == "你好！"


class TestStrategyConfig:
    """StrategyConfig 数据模型测试"""

    def test_create_strategy_config(self):
        """测试创建策略配置"""
        config = StrategyConfig(
            strategy_type=StrategyType.CONTEXTUAL,
            context_window_size=10,
            topic_detection_enabled=True,
            entity_tracking_enabled=True,
            adaptive_threshold=0.8,
        )
        assert config.strategy_type == StrategyType.CONTEXTUAL
        assert config.context_window_size == 10

    def test_strategy_config_default_values(self):
        """测试默认值"""
        config = StrategyConfig(strategy_type=StrategyType.ADAPTIVE)
        assert config.context_window_size == 5
        assert config.topic_detection_enabled is True
        assert config.entity_tracking_enabled is True
        assert config.adaptive_threshold == 0.7


class TestRetrievalAdjustment:
    """RetrievalAdjustment 数据模型测试"""

    def test_create_retrieval_adjustment(self):
        """测试创建检索调整"""
        adjustment = RetrievalAdjustment(
            strategy_type=StrategyType.CONTEXTUAL,
            query_modifications=["添加话题关键词"],
            context_additions=["对话上下文"],
            weight_adjustments={"context_weight": 0.8},
            reasoning="基于对话上下文调整",
            confidence=0.75,
        )
        assert adjustment.strategy_type == StrategyType.CONTEXTUAL
        assert len(adjustment.query_modifications) == 1
        assert adjustment.confidence == 0.75

    def test_retrieval_adjustment_default_values(self):
        """测试默认值"""
        adjustment = RetrievalAdjustment(
            strategy_type=StrategyType.ADAPTIVE
        )
        assert adjustment.query_modifications == []
        assert adjustment.context_additions == []
        assert adjustment.weight_adjustments == {}
        assert adjustment.reasoning == ""
        assert adjustment.confidence == 0.0


# =============================================================================
# 对话状态管理器测试
# =============================================================================

class TestConversationStateManager:
    """ConversationStateManager 测试"""

    def setup_method(self):
        """每个测试前重置"""
        self.manager = ConversationStateManager()

    def test_detect_state_init(self):
        """测试检测初始状态"""
        context = ConversationContext(conversation_id="test-123")
        state = self.manager.detect_state(context)
        assert state == ConversationState.INIT

    def test_detect_state_greeting(self):
        """测试检测问候状态"""
        context = ConversationContext(conversation_id="test-123")
        context.add_turn(TurnRole.USER, "你好")
        state = self.manager.detect_state(context)
        assert state == ConversationState.GREETING

    def test_detect_state_summary(self):
        """测试检测总结状态"""
        context = ConversationContext(conversation_id="test-123")
        context.add_turn(TurnRole.USER, "总结一下Python的特点")
        state = self.manager.detect_state(context)
        assert state == ConversationState.SUMMARY

    def test_detect_state_clarification(self):
        """测试检测澄清状态"""
        context = ConversationContext(conversation_id="test-123")
        context.add_turn(TurnRole.USER, "什么意思？")
        state = self.manager.detect_state(context)
        assert state == ConversationState.CLARIFICATION

    def test_detect_state_deep_dive(self):
        """测试检测深入探讨状态"""
        context = ConversationContext(conversation_id="test-123")
        for i in range(4):
            context.add_turn(TurnRole.USER, f"问题{i}")
        state = self.manager.detect_state(context)
        assert state == ConversationState.DEEP_DIVE

    def test_can_transition(self):
        """测试状态转换检查"""
        assert self.manager.can_transition(
            ConversationState.INIT,
            ConversationState.GREETING
        )
        assert self.manager.can_transition(
            ConversationState.INIT,
            ConversationState.TOPIC_DETECTION
        )
        assert not self.manager.can_transition(
            ConversationState.INIT,
            ConversationState.END
        )

    def test_get_next_states(self):
        """测试获取下一状态"""
        next_states = self.manager.get_next_states(ConversationState.INIT)
        assert ConversationState.GREETING in next_states
        assert ConversationState.TOPIC_DETECTION in next_states


# =============================================================================
# 话题和实体提取器测试
# =============================================================================

class TestTopicEntityExtractor:
    """TopicEntityExtractor 测试"""

    def setup_method(self):
        """每个测试前重置"""
        self.extractor = TopicEntityExtractor()

    def test_extract_topics(self):
        """测试提取话题"""
        context = ConversationContext(conversation_id="test-123")
        context.add_turn(TurnRole.USER, "Python 编程语言 学习")
        context.add_turn(TurnRole.USER, "Java 编程 开发")

        topics = self.extractor.extract_topics(context)
        assert len(topics) > 0
        assert "Python" in topics or "Java" in topics

    def test_extract_entities(self):
        """测试提取实体"""
        context = ConversationContext(conversation_id="test-123")
        context.add_turn(TurnRole.USER, '我说的是"Python"语言')
        context.add_turn(TurnRole.USER, "还有 Java")

        entities = self.extractor.extract_entities(context)
        assert len(entities) > 0

    def test_extract_entities_empty(self):
        """测试空实体提取"""
        context = ConversationContext(conversation_id="test-123")
        context.add_turn(TurnRole.USER, "你好")

        entities = self.extractor.extract_entities(context)
        assert len(entities) == 0


# =============================================================================
# 检索策略测试
# =============================================================================

class TestContextualStrategy:
    """ContextualStrategy 测试"""

    @pytest.mark.asyncio
    async def test_adjust_retrieval(self):
        """测试上下文感知策略"""
        strategy = ContextualStrategy()
        context = ConversationContext(conversation_id="test-123")
        context.add_turn(TurnRole.USER, "什么是Python？")
        context.add_turn(TurnRole.ASSISTANT, "Python是一种编程语言")
        context.add_turn(TurnRole.USER, "它的特点是什么？")

        adjustment = await strategy.adjust_retrieval(
            query="它的特点是什么？",
            context=context
        )

        assert adjustment.strategy_type == StrategyType.CONTEXTUAL
        assert adjustment.confidence > 0


class TestTopicFocusedStrategy:
    """TopicFocusedStrategy 测试"""

    @pytest.mark.asyncio
    async def test_adjust_retrieval(self):
        """测试话题聚焦策略"""
        strategy = TopicFocusedStrategy()
        context = ConversationContext(conversation_id="test-123")
        context.add_turn(TurnRole.USER, "Python 编程语言")
        context.topics = ["Python", "编程", "语言"]

        adjustment = await strategy.adjust_retrieval(
            query="Python的特点",
            context=context
        )

        assert adjustment.strategy_type == StrategyType.TOPIC_FOCUSED
        assert len(adjustment.query_modifications) > 0


class TestExpansiveStrategy:
    """ExpansiveStrategy 测试"""

    @pytest.mark.asyncio
    async def test_adjust_retrieval(self):
        """测试扩展检索策略"""
        strategy = ExpansiveStrategy()
        context = ConversationContext(conversation_id="test-123")
        context.add_turn(TurnRole.USER, "Python")
        context.topics = ["Python"]

        adjustment = await strategy.adjust_retrieval(
            query="Python介绍",
            context=context
        )

        assert adjustment.strategy_type == StrategyType.EXPANSIVE
        assert "vector_weight" in adjustment.weight_adjustments


class TestHistoryBasedStrategy:
    """HistoryBasedStrategy 测试"""

    @pytest.mark.asyncio
    async def test_adjust_retrieval(self):
        """测试基于历史策略"""
        strategy = HistoryBasedStrategy()
        context = ConversationContext(conversation_id="test-123")
        context.add_turn(TurnRole.USER, "问题1")
        context.add_turn(TurnRole.ASSISTANT, "回答1")
        context.add_turn(TurnRole.USER, "问题2")

        adjustment = await strategy.adjust_retrieval(
            query="问题2",
            context=context
        )

        assert adjustment.strategy_type == StrategyType.HISTORY_BASED
        assert len(adjustment.context_additions) > 0


class TestAdaptiveMultiTurnStrategy:
    """AdaptiveMultiTurnStrategy 测试"""

    @pytest.mark.asyncio
    async def test_adjust_retrieval(self):
        """测试自适应策略"""
        strategy = AdaptiveMultiTurnStrategy()
        context = ConversationContext(conversation_id="test-123")
        context.add_turn(TurnRole.USER, "Python是什么？")

        adjustment = await strategy.adjust_retrieval(
            query="Python是什么？",
            context=context
        )

        assert adjustment.strategy_type in [
            StrategyType.CONTEXTUAL,
            StrategyType.TOPIC_FOCUSED,
            StrategyType.EXPANSIVE,
            StrategyType.HISTORY_BASED,
        ]
        assert adjustment.confidence > 0


# =============================================================================
# MultiTurnManager 测试
# =============================================================================

class TestMultiTurnManager:
    """MultiTurnManager 测试"""

    def setup_method(self):
        """每个测试前重置"""
        self.manager = MultiTurnManager()

    def test_get_or_create_context(self):
        """测试获取或创建上下文"""
        context = self.manager.get_or_create_context("test-123")
        assert context.conversation_id == "test-123"
        assert context.turn_count == 0

    def test_add_user_turn(self):
        """测试添加用户轮次"""
        context = self.manager.add_user_turn("test-123", "你好")
        assert context.turn_count == 1
        assert context.last_user_turn.content == "你好"

    def test_add_assistant_turn(self):
        """测试添加助手轮次"""
        self.manager.add_user_turn("test-123", "你好")
        context = self.manager.add_assistant_turn("test-123", "你好！")
        assert context.turn_count == 2
        assert context.last_assistant_turn.content == "你好！"

    @pytest.mark.asyncio
    async def test_adjust_retrieval(self):
        """测试调整检索策略"""
        self.manager.add_user_turn("test-123", "Python是什么？")
        self.manager.add_assistant_turn("test-123", "Python是一种编程语言")
        self.manager.add_user_turn("test-123", "它的特点是什么？")

        adjustment = await self.manager.adjust_retrieval(
            conversation_id="test-123",
            query="它的特点是什么？"
        )

        assert isinstance(adjustment, RetrievalAdjustment)
        assert adjustment.confidence > 0

    def test_get_context_window(self):
        """测试获取上下文窗口"""
        self.manager.add_user_turn("test-123", "你好")
        self.manager.add_assistant_turn("test-123", "你好！")

        window = self.manager.get_context_window("test-123")
        assert "user: 你好" in window

    def test_clear_context(self):
        """测试清除上下文"""
        self.manager.add_user_turn("test-123", "你好")
        self.manager.clear_context("test-123")

        context = self.manager.get_or_create_context("test-123")
        assert context.turn_count == 0

    def test_get_stats(self):
        """测试获取统计信息"""
        self.manager.add_user_turn("test-123", "你好")
        stats = self.manager.get_stats()

        assert "active_conversations" in stats
        assert "strategy_type" in stats
        assert stats["active_conversations"] == 1


# =============================================================================
# 工厂类测试
# =============================================================================

class TestMultiTurnStrategyFactory:
    """MultiTurnStrategyFactory 测试"""

    def test_create_contextual(self):
        """测试创建上下文感知策略"""
        strategy = MultiTurnStrategyFactory.create(StrategyType.CONTEXTUAL)
        assert isinstance(strategy, ContextualStrategy)

    def test_create_topic_focused(self):
        """测试创建话题聚焦策略"""
        strategy = MultiTurnStrategyFactory.create(StrategyType.TOPIC_FOCUSED)
        assert isinstance(strategy, TopicFocusedStrategy)

    def test_create_expansive(self):
        """测试创建扩展策略"""
        strategy = MultiTurnStrategyFactory.create(StrategyType.EXPANSIVE)
        assert isinstance(strategy, ExpansiveStrategy)

    def test_create_history_based(self):
        """测试创建基于历史策略"""
        strategy = MultiTurnStrategyFactory.create(StrategyType.HISTORY_BASED)
        assert isinstance(strategy, HistoryBasedStrategy)

    def test_create_adaptive(self):
        """测试创建自适应策略"""
        strategy = MultiTurnStrategyFactory.create(StrategyType.ADAPTIVE)
        assert isinstance(strategy, AdaptiveMultiTurnStrategy)

    def test_create_manager(self):
        """测试创建管理器"""
        manager = MultiTurnStrategyFactory.create_manager()
        assert isinstance(manager, MultiTurnManager)


# =============================================================================
# 全局实例测试
# =============================================================================

class TestGlobalInstance:
    """全局实例管理测试"""

    def setup_method(self):
        """每个测试前重置"""
        reset_manager()

    def teardown_method(self):
        """每个测试后重置"""
        reset_manager()

    def test_get_manager_singleton(self):
        """测试单例模式"""
        manager1 = get_manager()
        manager2 = get_manager()
        assert manager1 is manager2

    def test_reset_manager(self):
        """测试重置实例"""
        manager1 = get_manager()
        reset_manager()
        manager2 = get_manager()
        assert manager1 is not manager2


# =============================================================================
# 集成测试
# =============================================================================

class TestIntegration:
    """集成测试"""

    def test_full_workflow(self):
        """测试完整工作流"""
        # 1. 创建管理器
        manager = MultiTurnStrategyFactory.create_manager()

        # 2. 模拟对话
        manager.add_user_turn("test-123", "你好")
        manager.add_assistant_turn("test-123", "你好！有什么可以帮助你的？")
        manager.add_user_turn("test-123", "Python是什么？")
        manager.add_assistant_turn("test-123", "Python是一种编程语言")
        manager.add_user_turn("test-123", "它的特点是什么？")

        # 3. 获取上下文
        context = manager.get_or_create_context("test-123")
        assert context.turn_count == 5
        assert context.state == ConversationState.DEEP_DIVE

        # 4. 调整检索策略
        import asyncio
        adjustment = asyncio.run(manager.adjust_retrieval(
            conversation_id="test-123",
            query="它的特点是什么？"
        ))
        assert isinstance(adjustment, RetrievalAdjustment)

    def test_conversation_flow(self):
        """测试对话流程"""
        manager = MultiTurnManager()

        # 初始状态
        context = manager.add_user_turn("conv-1", "你好")
        assert context.state == ConversationState.GREETING

        # 话题检测
        context = manager.add_user_turn("conv-1", "Python是什么？")
        assert context.state == ConversationState.TOPIC_DETECTION

        # 深入探讨
        for i in range(3):
            context = manager.add_user_turn("conv-1", f"问题{i}")
        assert context.state == ConversationState.DEEP_DIVE

    def test_multiple_conversations(self):
        """测试多对话管理"""
        manager = MultiTurnManager()

        # 两个不同的对话
        manager.add_user_turn("conv-1", "对话1的问题")
        manager.add_user_turn("conv-2", "对话2的问题")

        stats = manager.get_stats()
        assert stats["active_conversations"] == 2

        # 清除一个对话
        manager.clear_context("conv-1")
        stats = manager.get_stats()
        assert stats["active_conversations"] == 1
