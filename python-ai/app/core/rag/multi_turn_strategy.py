# Copyright (c) 2026 HFusionHub. All rights reserved.
"""
多轮检索策略模块 - 根据对话历史动态调整检索策略

参考项目：
- Ragent: 多轮检索策略、对话上下文理解
- LangGraph: 状态机、对话历史管理
- LlamaIndex: 上下文窗口、对话记忆

设计模式：
- 枚举模式: ConversationState, StrategyType - 类型安全的枚举定义
- 策略模式: 多种检索策略，运行时可切换
- 工厂模式: MultiTurnStrategyFactory - 统一策略创建
- 单例模式: 全局唯一策略实例
- 观察者模式: 对话状态变化通知
- 状态机模式: 对话状态转换
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# 枚举定义
# =============================================================================

class ConversationState(str, Enum):
    """对话状态"""
    INIT = "init"                    # 初始状态
    GREETING = "greeting"            # 问候
    TOPIC_DETECTION = "topic_detection"  # 话题检测
    DEEP_DIVE = "deep_dive"          # 深入探讨
    CLARIFICATION = "clarification"  # 澄清问题
    SUMMARY = "summary"              # 总结
    END = "end"                      # 结束


class StrategyType(str, Enum):
    """检索策略类型"""
    CONTEXTUAL = "contextual"        # 上下文感知
    TOPIC_FOCUSED = "topic_focused"  # 话题聚焦
    EXPANSIVE = "expansive"          # 扩展检索
    ADAPTIVE = "adaptive"            # 自适应
    HISTORY_BASED = "history_based"  # 基于历史


class TurnRole(str, Enum):
    """对话轮次角色"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# =============================================================================
# 数据模型
# =============================================================================

@dataclass
class ConversationTurn:
    """对话轮次"""
    role: TurnRole
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class ConversationContext:
    """对话上下文"""
    conversation_id: str
    turns: list[ConversationTurn] = field(default_factory=list)
    state: ConversationState = ConversationState.INIT
    topics: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def turn_count(self) -> int:
        """对话轮次数"""
        return len(self.turns)

    @property
    def last_user_turn(self) -> ConversationTurn | None:
        """最后一个用户轮次"""
        for turn in reversed(self.turns):
            if turn.role == TurnRole.USER:
                return turn
        return None

    @property
    def last_assistant_turn(self) -> ConversationTurn | None:
        """最后一个助手轮次"""
        for turn in reversed(self.turns):
            if turn.role == TurnRole.ASSISTANT:
                return turn
        return None

    def add_turn(self, role: TurnRole, content: str, **metadata):
        """添加对话轮次"""
        turn = ConversationTurn(
            role=role,
            content=content,
            metadata=metadata,
        )
        self.turns.append(turn)
        return turn

    def get_recent_turns(self, n: int = 5) -> list[ConversationTurn]:
        """获取最近 n 轮对话"""
        return self.turns[-n:] if len(self.turns) >= n else self.turns

    def get_context_window(self, max_tokens: int = 4000) -> str:
        """获取上下文窗口"""
        context_parts = []
        current_tokens = 0

        for turn in reversed(self.turns):
            turn_text = f"{turn.role.value}: {turn.content}"
            turn_tokens = len(turn_text) // 2  # 简单估算

            if current_tokens + turn_tokens > max_tokens:
                break

            context_parts.insert(0, turn_text)
            current_tokens += turn_tokens

        return "\n".join(context_parts)


@dataclass
class StrategyConfig:
    """策略配置"""
    strategy_type: StrategyType
    context_window_size: int = 5
    topic_detection_enabled: bool = True
    entity_tracking_enabled: bool = True
    adaptive_threshold: float = 0.7
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalAdjustment:
    """检索调整"""
    strategy_type: StrategyType
    query_modifications: list[str] = field(default_factory=list)
    context_additions: list[str] = field(default_factory=list)
    weight_adjustments: dict[str, float] = field(default_factory=dict)
    reasoning: str = ""
    confidence: float = 0.0


# =============================================================================
# 对话状态管理器
# =============================================================================

class ConversationStateManager:
    """对话状态管理器"""

    # 状态转换规则
    _transitions: dict[ConversationState, list[ConversationState]] = {
        ConversationState.INIT: [
            ConversationState.GREETING,
            ConversationState.TOPIC_DETECTION,
        ],
        ConversationState.GREETING: [
            ConversationState.TOPIC_DETECTION,
            ConversationState.END,
        ],
        ConversationState.TOPIC_DETECTION: [
            ConversationState.DEEP_DIVE,
            ConversationState.CLARIFICATION,
            ConversationState.SUMMARY,
        ],
        ConversationState.DEEP_DIVE: [
            ConversationState.DEEP_DIVE,
            ConversationState.CLARIFICATION,
            ConversationState.SUMMARY,
        ],
        ConversationState.CLARIFICATION: [
            ConversationState.DEEP_DIVE,
            ConversationState.SUMMARY,
        ],
        ConversationState.SUMMARY: [
            ConversationState.END,
            ConversationState.TOPIC_DETECTION,
        ],
        ConversationState.END: [
            ConversationState.INIT,
        ],
    }

    def detect_state(self, context: ConversationContext) -> ConversationState:
        """
        检测对话状态

        根据对话历史和当前轮次判断状态
        """
        if context.turn_count == 0:
            return ConversationState.INIT

        last_user_turn = context.last_user_turn
        if not last_user_turn:
            return ConversationState.INIT

        content = last_user_turn.content.lower()

        # 问候检测
        greeting_keywords = ["你好", "您好", "hi", "hello", "嗨"]
        if any(kw in content for kw in greeting_keywords):
            return ConversationState.GREETING

        # 总结检测
        summary_keywords = ["总结", "概括", "归纳", "综上所述"]
        if any(kw in content for kw in summary_keywords):
            return ConversationState.SUMMARY

        # 澄清检测
        clarification_keywords = ["什么意思", "解释一下", "能详细说说", "不太明白"]
        if any(kw in content for kw in clarification_keywords):
            return ConversationState.CLARIFICATION

        # 深入探讨检测（有多轮对话且话题相关）
        if context.turn_count >= 3:
            return ConversationState.DEEP_DIVE

        return ConversationState.TOPIC_DETECTION

    def can_transition(
        self,
        current: ConversationState,
        next_state: ConversationState
    ) -> bool:
        """检查状态转换是否允许"""
        allowed = self._transitions.get(current, [])
        return next_state in allowed

    def get_next_states(self, current: ConversationState) -> list[ConversationState]:
        """获取当前状态可以转换到的下一状态"""
        return self._transitions.get(current, [])


# =============================================================================
# 话题和实体提取器
# =============================================================================

class TopicEntityExtractor:
    """话题和实体提取器"""

    def extract_topics(self, context: ConversationContext) -> list[str]:
        """
        提取对话话题

        使用简单规则提取话题关键词
        """
        topics = set()

        for turn in context.turns:
            if turn.role == TurnRole.USER:
                # 简单分词（实际应用中应使用 jieba）
                words = turn.content.split()
                # 过滤停用词
                stop_words = {"的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好", "自己", "这"}
                content_words = [w for w in words if w not in stop_words and len(w) > 1]
                topics.update(content_words[:3])  # 取前3个关键词

        return list(topics)[:5]  # 最多5个话题

    def extract_entities(self, context: ConversationContext) -> list[str]:
        """
        提取实体

        使用简单规则提取实体
        """
        entities = set()

        for turn in context.turns:
            if turn.role == TurnRole.USER:
                # 简单实体提取（实际应用中应使用 NER）
                # 提取引号内的内容
                import re
                quoted = re.findall(r'[""「」](.*?)[""「」]', turn.content)
                entities.update(quoted)

                # 提取大写字母开头的词（英文实体）
                capitalized = re.findall(r'\b[A-Z][a-z]+\b', turn.content)
                entities.update(capitalized)

        return list(entities)[:10]  # 最多10个实体


# =============================================================================
# 多轮检索策略
# =============================================================================

class MultiTurnStrategy:
    """多轮检索策略基类"""

    def __init__(self, config: StrategyConfig | None = None):
        self.config = config or StrategyConfig(strategy_type=StrategyType.ADAPTIVE)

    async def adjust_retrieval(
        self,
        query: str,
        context: ConversationContext,
        **kwargs
    ) -> RetrievalAdjustment:
        """调整检索策略"""
        raise NotImplementedError


class ContextualStrategy(MultiTurnStrategy):
    """上下文感知策略"""

    def __init__(self, config: StrategyConfig | None = None):
        super().__init__(config)
        self.config.strategy_type = StrategyType.CONTEXTUAL

    async def adjust_retrieval(
        self,
        query: str,
        context: ConversationContext,
        **kwargs
    ) -> RetrievalAdjustment:
        """基于上下文调整检索"""
        modifications = []
        context_additions = []
        weight_adjustments = {}

        # 1. 获取上下文窗口
        context_window = context.get_context_window(max_tokens=2000)
        if context_window:
            context_additions.append(f"对话上下文:\n{context_window}")

        # 2. 根据对话轮次调整
        if context.turn_count > 3:
            # 多轮对话，增加上下文权重
            weight_adjustments["context_weight"] = 0.8
            modifications.append("增加上下文权重")

        # 3. 根据话题调整
        if context.topics:
            modifications.append(f"添加话题关键词: {context.topics[:3]}")

        return RetrievalAdjustment(
            strategy_type=StrategyType.CONTEXTUAL,
            query_modifications=modifications,
            context_additions=context_additions,
            weight_adjustments=weight_adjustments,
            reasoning="基于对话上下文调整检索策略",
            confidence=0.7,
        )


class TopicFocusedStrategy(MultiTurnStrategy):
    """话题聚焦策略"""

    def __init__(self, config: StrategyConfig | None = None):
        super().__init__(config)
        self.config.strategy_type = StrategyType.TOPIC_FOCUSED

    async def adjust_retrieval(
        self,
        query: str,
        context: ConversationContext,
        **kwargs
    ) -> RetrievalAdjustment:
        """基于话题聚焦调整检索"""
        modifications = []
        context_additions = []

        # 1. 提取当前话题
        topics = context.topics
        if topics:
            # 将话题添加到查询
            modifications.append(f"聚焦话题: {topics}")

        # 2. 提取实体
        entities = context.entities
        if entities:
            modifications.append(f"关注实体: {entities}")

        # 3. 生成话题查询
        if topics:
            topic_query = f"{' '.join(topics)} {query}"
            context_additions.append(f"话题增强查询: {topic_query}")

        return RetrievalAdjustment(
            strategy_type=StrategyType.TOPIC_FOCUSED,
            query_modifications=modifications,
            context_additions=context_additions,
            reasoning="基于话题聚焦调整检索策略",
            confidence=0.75,
        )


class ExpansiveStrategy(MultiTurnStrategy):
    """扩展检索策略"""

    def __init__(self, config: StrategyConfig | None = None):
        super().__init__(config)
        self.config.strategy_type = StrategyType.EXPANSIVE

    async def adjust_retrieval(
        self,
        query: str,
        context: ConversationContext,
        **kwargs
    ) -> RetrievalAdjustment:
        """扩展检索范围"""
        modifications = []
        context_additions = []

        # 1. 扩展查询
        if context.topics:
            expanded_query = f"{query} 相关 知识 介绍"
            modifications.append(f"扩展查询: {expanded_query}")

        # 2. 增加上下文
        if context.turn_count > 0:
            context_additions.append("包含相关领域知识")

        # 3. 调整权重
        weight_adjustments = {
            "vector_weight": 0.9,
            "keyword_weight": 0.3,
            "graph_weight": 0.2,
        }

        return RetrievalAdjustment(
            strategy_type=StrategyType.EXPANSIVE,
            query_modifications=modifications,
            context_additions=context_additions,
            weight_adjustments=weight_adjustments,
            reasoning="扩展检索范围以获取更多信息",
            confidence=0.6,
        )


class HistoryBasedStrategy(MultiTurnStrategy):
    """基于历史策略"""

    def __init__(self, config: StrategyConfig | None = None):
        super().__init__(config)
        self.config.strategy_type = StrategyType.HISTORY_BASED

    async def adjust_retrieval(
        self,
        query: str,
        context: ConversationContext,
        **kwargs
    ) -> RetrievalAdjustment:
        """基于对话历史调整检索"""
        modifications = []
        context_additions = []

        # 1. 分析历史对话
        if context.turn_count >= 2:
            # 获取最近的对话
            recent_turns = context.get_recent_turns(3)
            history_context = "\n".join([
                f"{turn.role.value}: {turn.content}"
                for turn in recent_turns
            ])
            context_additions.append(f"历史对话:\n{history_context}")

        # 2. 检测重复查询
        if context.turn_count >= 2:
            last_user_turns = [
                turn.content for turn in context.turns[-4:]
                if turn.role == TurnRole.USER
            ]
            if len(set(last_user_turns)) < len(last_user_turns):
                modifications.append("检测到重复查询，调整策略")

        # 3. 调整检索深度
        weight_adjustments = {
            "retrieval_depth": 15 if context.turn_count > 3 else 10,
        }

        return RetrievalAdjustment(
            strategy_type=StrategyType.HISTORY_BASED,
            query_modifications=modifications,
            context_additions=context_additions,
            weight_adjustments=weight_adjustments,
            reasoning="基于对话历史调整检索策略",
            confidence=0.65,
        )


class AdaptiveMultiTurnStrategy(MultiTurnStrategy):
    """自适应多轮策略"""

    def __init__(self, config: StrategyConfig | None = None):
        super().__init__(config)
        self.config.strategy_type = StrategyType.ADAPTIVE

        # 子策略
        self._strategies: dict[StrategyType, MultiTurnStrategy] = {
            StrategyType.CONTEXTUAL: ContextualStrategy(config),
            StrategyType.TOPIC_FOCUSED: TopicFocusedStrategy(config),
            StrategyType.EXPANSIVE: ExpansiveStrategy(config),
            StrategyType.HISTORY_BASED: HistoryBasedStrategy(config),
        }

    async def adjust_retrieval(
        self,
        query: str,
        context: ConversationContext,
        **kwargs
    ) -> RetrievalAdjustment:
        """自适应选择策略"""
        # 1. 根据对话状态选择策略
        state_manager = ConversationStateManager()
        current_state = state_manager.detect_state(context)

        # 2. 选择最佳策略
        strategy_type = self._select_strategy(current_state, context)

        # 3. 执行策略
        strategy = self._strategies.get(strategy_type)
        if strategy:
            return await strategy.adjust_retrieval(query, context, **kwargs)

        # 默认策略
        return RetrievalAdjustment(
            strategy_type=StrategyType.ADAPTIVE,
            reasoning="使用默认自适应策略",
            confidence=0.5,
        )

    def _select_strategy(
        self,
        state: ConversationState,
        context: ConversationContext
    ) -> StrategyType:
        """根据状态选择策略"""
        if state == ConversationState.INIT:
            return StrategyType.EXPANSIVE

        if state == ConversationState.TOPIC_DETECTION:
            return StrategyType.CONTEXTUAL

        if state == ConversationState.DEEP_DIVE:
            return StrategyType.TOPIC_FOCUSED

        if state == ConversationState.CLARIFICATION:
            return StrategyType.HISTORY_BASED

        if state == ConversationState.SUMMARY:
            return StrategyType.CONTEXTUAL

        return StrategyType.ADAPTIVE


# =============================================================================
# 多轮检索管理器
# =============================================================================

class MultiTurnManager:
    """多轮检索管理器"""

    def __init__(
        self,
        strategy: MultiTurnStrategy | None = None,
        max_context_tokens: int = 4000,
    ):
        self.strategy = strategy or AdaptiveMultiTurnStrategy()
        self.max_context_tokens = max_context_tokens
        self.state_manager = ConversationStateManager()
        self.extractor = TopicEntityExtractor()

        # 对话上下文缓存
        self._contexts: dict[str, ConversationContext] = {}

    def get_or_create_context(self, conversation_id: str) -> ConversationContext:
        """获取或创建对话上下文"""
        if conversation_id not in self._contexts:
            self._contexts[conversation_id] = ConversationContext(
                conversation_id=conversation_id,
            )
        return self._contexts[conversation_id]

    def add_user_turn(self, conversation_id: str, content: str) -> ConversationContext:
        """添加用户轮次"""
        context = self.get_or_create_context(conversation_id)
        context.add_turn(TurnRole.USER, content)

        # 更新状态
        context.state = self.state_manager.detect_state(context)

        # 更新话题和实体
        if self.strategy.config.topic_detection_enabled:
            context.topics = self.extractor.extract_topics(context)

        if self.strategy.config.entity_tracking_enabled:
            context.entities = self.extractor.extract_entities(context)

        return context

    def add_assistant_turn(self, conversation_id: str, content: str) -> ConversationContext:
        """添加助手轮次"""
        context = self.get_or_create_context(conversation_id)
        context.add_turn(TurnRole.ASSISTANT, content)
        return context

    async def adjust_retrieval(
        self,
        conversation_id: str,
        query: str,
        **kwargs
    ) -> RetrievalAdjustment:
        """调整检索策略"""
        context = self.get_or_create_context(conversation_id)

        # 执行策略调整
        adjustment = await self.strategy.adjust_retrieval(
            query=query,
            context=context,
            **kwargs,
        )

        logger.info(
            f"Retrieval adjustment for conversation {conversation_id}: "
            f"strategy={adjustment.strategy_type.value}, "
            f"confidence={adjustment.confidence:.2f}"
        )

        return adjustment

    def get_context_window(self, conversation_id: str) -> str:
        """获取上下文窗口"""
        context = self.get_or_create_context(conversation_id)
        return context.get_context_window(self.max_context_tokens)

    def clear_context(self, conversation_id: str):
        """清除对话上下文"""
        if conversation_id in self._contexts:
            del self._contexts[conversation_id]

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        return {
            "active_conversations": len(self._contexts),
            "strategy_type": self.strategy.config.strategy_type.value,
            "max_context_tokens": self.max_context_tokens,
        }


# =============================================================================
# 工厂类
# =============================================================================

class MultiTurnStrategyFactory:
    """MultiTurnStrategy 工厂类"""

    @staticmethod
    def create(
        strategy_type: StrategyType = StrategyType.ADAPTIVE,
        config: StrategyConfig | None = None,
        **kwargs
    ) -> MultiTurnStrategy:
        """创建 MultiTurnStrategy 实例"""
        if strategy_type == StrategyType.CONTEXTUAL:
            return ContextualStrategy(config, **kwargs)
        elif strategy_type == StrategyType.TOPIC_FOCUSED:
            return TopicFocusedStrategy(config, **kwargs)
        elif strategy_type == StrategyType.EXPANSIVE:
            return ExpansiveStrategy(config, **kwargs)
        elif strategy_type == StrategyType.HISTORY_BASED:
            return HistoryBasedStrategy(config, **kwargs)
        elif strategy_type == StrategyType.ADAPTIVE:
            return AdaptiveMultiTurnStrategy(config, **kwargs)
        else:
            return AdaptiveMultiTurnStrategy(config, **kwargs)

    @staticmethod
    def create_manager(
        strategy_type: StrategyType = StrategyType.ADAPTIVE,
        config: StrategyConfig | None = None,
        **kwargs
    ) -> MultiTurnManager:
        """创建 MultiTurnManager 实例"""
        strategy = MultiTurnStrategyFactory.create(strategy_type, config, **kwargs)
        return MultiTurnManager(strategy=strategy, **kwargs)


# =============================================================================
# 全局实例
# =============================================================================

_global_manager: MultiTurnManager | None = None


def get_manager() -> MultiTurnManager:
    """获取全局 MultiTurnManager 实例"""
    global _global_manager
    if _global_manager is None:
        _global_manager = MultiTurnStrategyFactory.create_manager()
    return _global_manager


def reset_manager():
    """重置全局 MultiTurnManager 实例"""
    global _global_manager
    _global_manager = None
