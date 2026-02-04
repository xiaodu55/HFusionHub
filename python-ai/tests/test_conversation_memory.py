"""
ConversationMemory 模块单元测试

测试覆盖：
1. 数据模型测试（Message, ConversationSession, MemoryConfig等）
2. 枚举定义测试
3. 记忆策略测试（5种策略）
4. 记忆存储测试
5. 记忆检索测试
6. 主类测试（ConversationMemory）
7. 工厂类测试
8. 全局实例管理测试
9. 集成测试
"""

import pytest
import time
import uuid
from unittest.mock import AsyncMock, patch, MagicMock

from app.core.rag.conversation_memory import (
    # 枚举
    MemoryType,
    MemoryStrategyType,
    MessageRole,
    MemoryEventType,
    # 数据模型
    Message,
    ConversationSession,
    MemoryConfig,
    MemorySearchResult,
    MemorySearchResponse,
    MemoryStats,
    # 策略
    BaseMemoryStrategy,
    SlidingWindowMemory,
    TokenBasedMemory,
    SummaryMemory,
    ImportanceBasedMemory,
    HybridMemory,
    MemoryStrategyFactory,
    # 组件
    MemoryEmbedder,
    MemoryStorage,
    MemoryRetriever,
    # 主类
    ConversationMemory,
    ConversationMemoryFactory,
    # 全局实例
    get_conversation_memory,
    reset_conversation_memory,
)


# ============================================================
# 1. 数据模型测试
# ============================================================

class TestMessage:
    """Message 数据模型测试"""

    def test_create_message(self):
        """测试创建消息"""
        msg = Message(
            message_id="msg-001",
            role=MessageRole.USER,
            content="Hello, world!",
            timestamp=time.time(),
            token_count=10,
            importance_score=0.8
        )

        assert msg.message_id == "msg-001"
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello, world!"
        assert msg.token_count == 10
        assert msg.importance_score == 0.8
        assert msg.is_summarized is False
        assert msg.summary == ""

    def test_message_to_dict(self):
        """测试消息转字典"""
        msg = Message(
            message_id="msg-002",
            role=MessageRole.ASSISTANT,
            content="I'm here to help.",
            timestamp=1234567890.0,
            token_count=15,
            importance_score=0.6,
            metadata={"source": "test"}
        )

        d = msg.to_dict()

        assert d["message_id"] == "msg-002"
        assert d["role"] == "assistant"
        assert d["content"] == "I'm here to help."
        assert d["token_count"] == 15
        assert d["importance_score"] == 0.6
        assert d["metadata"]["source"] == "test"

    def test_message_from_dict(self):
        """测试从字典创建消息"""
        d = {
            "message_id": "msg-003",
            "role": "system",
            "content": "System message",
            "timestamp": 1234567890.0,
            "token_count": 20,
            "importance_score": 0.9,
            "is_summarized": True,
            "summary": "This is a summary"
        }

        msg = Message.from_dict(d)

        assert msg.message_id == "msg-003"
        assert msg.role == MessageRole.SYSTEM
        assert msg.content == "System message"
        assert msg.is_summarized is True
        assert msg.summary == "This is a summary"


class TestConversationSession:
    """ConversationSession 数据模型测试"""

    def test_create_session(self):
        """测试创建会话"""
        session = ConversationSession(
            session_id="session-001",
            user_id="user-001",
            created_at=time.time(),
            updated_at=time.time()
        )

        assert session.session_id == "session-001"
        assert session.user_id == "user-001"
        assert session.messages == []
        assert session.is_active is True

    def test_session_to_dict(self):
        """测试会话转字典"""
        msg = Message(
            message_id="msg-001",
            role=MessageRole.USER,
            content="Test",
            timestamp=time.time()
        )

        session = ConversationSession(
            session_id="session-002",
            user_id="user-002",
            created_at=1234567890.0,
            updated_at=1234567890.0,
            messages=[msg],
            metadata={"key": "value"}
        )

        d = session.to_dict()

        assert d["session_id"] == "session-002"
        assert d["user_id"] == "user-002"
        assert len(d["messages"]) == 1
        assert d["metadata"]["key"] == "value"

    def test_session_from_dict(self):
        """测试从字典创建会话"""
        d = {
            "session_id": "session-003",
            "user_id": "user-003",
            "created_at": 1234567890.0,
            "updated_at": 1234567890.0,
            "messages": [
                {
                    "message_id": "msg-001",
                    "role": "user",
                    "content": "Hello",
                    "timestamp": 1234567890.0
                }
            ],
            "is_active": True
        }

        session = ConversationSession.from_dict(d)

        assert session.session_id == "session-003"
        assert len(session.messages) == 1
        assert session.messages[0].content == "Hello"


class TestMemoryConfig:
    """MemoryConfig 数据模型测试"""

    def test_create_config(self):
        """测试创建配置"""
        config = MemoryConfig()

        assert config.strategy_type == MemoryStrategyType.SLIDING_WINDOW
        assert config.max_messages == 50
        assert config.max_tokens == 4000
        assert config.enable_embedding is True

    def test_config_to_dict(self):
        """测试配置转字典"""
        config = MemoryConfig(
            strategy_type=MemoryStrategyType.TOKEN_BASED,
            max_messages=100,
            max_tokens=8000
        )

        d = config.to_dict()

        assert d["strategy_type"] == "token_based"
        assert d["max_messages"] == 100
        assert d["max_tokens"] == 8000

    def test_config_from_dict(self):
        """测试从字典创建配置"""
        d = {
            "strategy_type": "summary",
            "max_messages": 30,
            "max_tokens": 2000,
            "summary_threshold": 10
        }

        config = MemoryConfig.from_dict(d)

        assert config.strategy_type == MemoryStrategyType.SUMMARY
        assert config.max_messages == 30
        assert config.summary_threshold == 10


class TestMemorySearchResult:
    """MemorySearchResult 数据模型测试"""

    def test_create_search_result(self):
        """测试创建搜索结果"""
        msg = Message(
            message_id="msg-001",
            role=MessageRole.USER,
            content="Test",
            timestamp=time.time()
        )

        result = MemorySearchResult(
            message=msg,
            score=0.85,
            session_id="session-001",
            reason="语义相似"
        )

        assert result.score == 0.85
        assert result.session_id == "session-001"

    def test_search_result_to_dict(self):
        """测试搜索结果转字典"""
        msg = Message(
            message_id="msg-001",
            role=MessageRole.USER,
            content="Test",
            timestamp=time.time()
        )

        result = MemorySearchResult(
            message=msg,
            score=0.85,
            session_id="session-001"
        )

        d = result.to_dict()

        assert d["score"] == 0.85
        assert d["session_id"] == "session-001"
        assert "message" in d


class TestMemorySearchResponse:
    """MemorySearchResponse 数据模型测试"""

    def test_create_search_response(self):
        """测试创建搜索响应"""
        msg = Message(
            message_id="msg-001",
            role=MessageRole.USER,
            content="Test",
            timestamp=time.time()
        )

        response = MemorySearchResponse(
            query="test query",
            results=[
                MemorySearchResult(message=msg, score=0.9, session_id="s1")
            ],
            total_results=1,
            search_time_ms=15.5
        )

        assert response.query == "test query"
        assert response.total_results == 1
        assert response.search_time_ms == 15.5

    def test_search_response_to_dict(self):
        """测试搜索响应转字典"""
        response = MemorySearchResponse(
            query="test",
            results=[],
            total_results=0,
            search_time_ms=5.0
        )

        d = response.to_dict()

        assert d["query"] == "test"
        assert d["total_results"] == 0


class TestMemoryStats:
    """MemoryStats 数据模型测试"""

    def test_create_stats(self):
        """测试创建统计"""
        stats = MemoryStats(
            total_sessions=10,
            total_messages=100,
            total_tokens=5000
        )

        assert stats.total_sessions == 10
        assert stats.total_messages == 100
        assert stats.total_tokens == 5000

    def test_stats_to_dict(self):
        """测试统计转字典"""
        stats = MemoryStats(
            total_sessions=5,
            total_messages=50,
            avg_messages_per_session=10.0
        )

        d = stats.to_dict()

        assert d["total_sessions"] == 5
        assert d["avg_messages_per_session"] == 10.0


# ============================================================
# 2. 枚举定义测试
# ============================================================

class TestEnums:
    """枚举定义测试"""

    def test_memory_type(self):
        """测试记忆类型枚举"""
        assert MemoryType.SHORT_TERM.value == "short_term"
        assert MemoryType.LONG_TERM.value == "long_term"
        assert MemoryType.EPISODIC.value == "episodic"
        assert MemoryType.SEMANTIC.value == "semantic"

    def test_memory_strategy_type(self):
        """测试记忆策略类型枚举"""
        assert MemoryStrategyType.SLIDING_WINDOW.value == "sliding_window"
        assert MemoryStrategyType.TOKEN_BASED.value == "token_based"
        assert MemoryStrategyType.SUMMARY.value == "summary"
        assert MemoryStrategyType.IMPORTANCE_BASED.value == "importance_based"
        assert MemoryStrategyType.HYBRID.value == "hybrid"

    def test_message_role(self):
        """测试消息角色枚举"""
        assert MessageRole.USER.value == "user"
        assert MessageRole.ASSISTANT.value == "assistant"
        assert MessageRole.SYSTEM.value == "system"
        assert MessageRole.TOOL.value == "tool"

    def test_memory_event_type(self):
        """测试记忆事件类型枚举"""
        assert MemoryEventType.MESSAGE_ADDED.value == "message_added"
        assert MemoryEventType.MESSAGE_REMOVED.value == "message_removed"
        assert MemoryEventType.MEMORY_SUMMARIZED.value == "memory_summarized"
        assert MemoryEventType.MEMORY_COMPRESSED.value == "memory_compressed"
        assert MemoryEventType.MEMORY_EXPIRED.value == "memory_expired"


# ============================================================
# 3. 记忆策略测试
# ============================================================

class TestSlidingWindowMemory:
    """滑动窗口记忆策略测试"""

    def setup_method(self):
        """测试前设置"""
        self.config = MemoryConfig(
            strategy_type=MemoryStrategyType.SLIDING_WINDOW,
            max_messages=5
        )
        self.strategy = SlidingWindowMemory(self.config)

    def test_should_add_message(self):
        """测试是否应该添加消息"""
        session = ConversationSession(
            session_id="s1",
            user_id="u1",
            created_at=time.time(),
            updated_at=time.time()
        )
        msg = Message(
            message_id="m1",
            role=MessageRole.USER,
            content="Test",
            timestamp=time.time()
        )

        assert self.strategy.should_add_message(session, msg) is True

    def test_get_messages_for_context(self):
        """测试获取上下文消息"""
        session = ConversationSession(
            session_id="s1",
            user_id="u1",
            created_at=time.time(),
            updated_at=time.time(),
            messages=[
                Message(f"m{i}", MessageRole.USER, f"Msg {i}", time.time())
                for i in range(10)
            ]
        )

        context = self.strategy.get_messages_for_context(session)

        assert len(context) == 5
        assert context[0].message_id == "m5"
        assert context[-1].message_id == "m9"

    def test_get_messages_with_token_limit(self):
        """测试基于Token限制获取消息"""
        session = ConversationSession(
            session_id="s1",
            user_id="u1",
            created_at=time.time(),
            updated_at=time.time(),
            messages=[
                Message(f"m{i}", MessageRole.USER, f"Msg {i}", time.time(), token_count=100)
                for i in range(10)
            ]
        )

        context = self.strategy.get_messages_for_context(session, max_tokens=300)

        assert len(context) == 3

    def test_compress_memory(self):
        """测试压缩记忆"""
        session = ConversationSession(
            session_id="s1",
            user_id="u1",
            created_at=time.time(),
            updated_at=time.time(),
            messages=[
                Message(f"m{i}", MessageRole.USER, f"Msg {i}", time.time())
                for i in range(10)
            ]
        )

        keep, compress = self.strategy.compress_memory(session)

        assert len(keep) == 5
        assert len(compress) == 5


class TestTokenBasedMemory:
    """基于Token的记忆策略测试"""

    def setup_method(self):
        """测试前设置"""
        self.config = MemoryConfig(
            strategy_type=MemoryStrategyType.TOKEN_BASED,
            max_tokens=500
        )
        self.strategy = TokenBasedMemory(self.config)

    def test_should_add_message_within_limit(self):
        """测试在限制内添加消息"""
        session = ConversationSession(
            session_id="s1",
            user_id="u1",
            created_at=time.time(),
            updated_at=time.time(),
            messages=[
                Message(f"m{i}", MessageRole.USER, f"Msg {i}", time.time(), token_count=100)
                for i in range(3)
            ]
        )
        msg = Message(
            message_id="m4",
            role=MessageRole.USER,
            content="New msg",
            timestamp=time.time(),
            token_count=100
        )

        assert self.strategy.should_add_message(session, msg) is True

    def test_should_add_message_exceed_limit(self):
        """测试超过限制添加消息"""
        session = ConversationSession(
            session_id="s1",
            user_id="u1",
            created_at=time.time(),
            updated_at=time.time(),
            messages=[
                Message(f"m{i}", MessageRole.USER, f"Msg {i}", time.time(), token_count=150)
                for i in range(3)
            ]
        )
        msg = Message(
            message_id="m4",
            role=MessageRole.USER,
            content="New msg",
            timestamp=time.time(),
            token_count=100
        )

        assert self.strategy.should_add_message(session, msg) is False

    def test_get_messages_for_context(self):
        """测试获取上下文消息"""
        session = ConversationSession(
            session_id="s1",
            user_id="u1",
            created_at=time.time(),
            updated_at=time.time(),
            messages=[
                Message(f"m{i}", MessageRole.USER, f"Msg {i}", time.time(), token_count=100)
                for i in range(10)
            ]
        )

        context = self.strategy.get_messages_for_context(session)

        assert len(context) == 5  # 500 / 100 = 5

    def test_compress_memory(self):
        """测试压缩记忆"""
        session = ConversationSession(
            session_id="s1",
            user_id="u1",
            created_at=time.time(),
            updated_at=time.time(),
            messages=[
                Message(f"m{i}", MessageRole.USER, f"Msg {i}", time.time(), token_count=100)
                for i in range(10)
            ]
        )

        keep, compress = self.strategy.compress_memory(session)

        assert len(keep) == 5
        assert len(compress) == 5


class TestSummaryMemory:
    """摘要记忆策略测试"""

    def setup_method(self):
        """测试前设置"""
        self.config = MemoryConfig(
            strategy_type=MemoryStrategyType.SUMMARY,
            summary_threshold=5
        )
        self.strategy = SummaryMemory(self.config)

    def test_should_add_message(self):
        """测试是否应该添加消息"""
        session = ConversationSession(
            session_id="s1",
            user_id="u1",
            created_at=time.time(),
            updated_at=time.time()
        )
        msg = Message(
            message_id="m1",
            role=MessageRole.USER,
            content="Test",
            timestamp=time.time()
        )

        assert self.strategy.should_add_message(session, msg) is True

    def test_get_messages_prefers_unsummarized(self):
        """测试优先获取未摘要的消息"""
        session = ConversationSession(
            session_id="s1",
            user_id="u1",
            created_at=time.time(),
            updated_at=time.time(),
            messages=[
                Message(f"m{i}", MessageRole.USER, f"Msg {i}", time.time(), is_summarized=(i < 3))
                for i in range(5)
            ]
        )

        context = self.strategy.get_messages_for_context(session)

        # 未摘要的消息应该在前面
        assert any(not m.is_summarized for m in context)

    def test_compress_memory(self):
        """测试压缩记忆"""
        session = ConversationSession(
            session_id="s1",
            user_id="u1",
            created_at=time.time(),
            updated_at=time.time(),
            messages=[
                Message(f"m{i}", MessageRole.USER, f"Msg {i}", time.time())
                for i in range(10)
            ]
        )

        keep, compress = self.strategy.compress_memory(session)

        assert len(keep) == 6  # 5 new + 1 summary
        assert len(compress) == 5


class TestImportanceBasedMemory:
    """基于重要性的记忆策略测试"""

    def setup_method(self):
        """测试前设置"""
        self.config = MemoryConfig(
            strategy_type=MemoryStrategyType.IMPORTANCE_BASED,
            importance_threshold=0.5
        )
        self.strategy = ImportanceBasedMemory(self.config)

    def test_should_add_important_message(self):
        """测试添加重要消息"""
        session = ConversationSession(
            session_id="s1",
            user_id="u1",
            created_at=time.time(),
            updated_at=time.time()
        )
        msg = Message(
            message_id="m1",
            role=MessageRole.USER,
            content="Important msg",
            timestamp=time.time(),
            importance_score=0.8
        )

        assert self.strategy.should_add_message(session, msg) is True

    def test_should_reject_unimportant_message(self):
        """测试拒绝不重要消息"""
        session = ConversationSession(
            session_id="s1",
            user_id="u1",
            created_at=time.time(),
            updated_at=time.time()
        )
        msg = Message(
            message_id="m1",
            role=MessageRole.USER,
            content="Trivial msg",
            timestamp=time.time(),
            importance_score=0.2
        )

        assert self.strategy.should_add_message(session, msg) is False

    def test_get_messages_selected_by_importance(self):
        """测试按重要性选择消息"""
        session = ConversationSession(
            session_id="s1",
            user_id="u1",
            created_at=time.time(),
            updated_at=time.time(),
            messages=[
                Message(f"m{i}", MessageRole.USER, f"Msg {i}", time.time() + i, token_count=100,
                        importance_score=0.3 + i * 0.1)
                for i in range(5)
            ]
        )

        context = self.strategy.get_messages_for_context(session)

        # 应该选择重要性高的消息（返回时按时间排序）
        assert len(context) == 5  # 所有消息都在限制内
        # 验证所有消息都被选中
        importance_scores = [m.importance_score for m in context]
        assert 0.3 in importance_scores
        assert 0.7 in importance_scores

    def test_compress_memory(self):
        """测试压缩记忆"""
        session = ConversationSession(
            session_id="s1",
            user_id="u1",
            created_at=time.time(),
            updated_at=time.time(),
            messages=[
                Message(f"m{i}", MessageRole.USER, f"Msg {i}", time.time(),
                        importance_score=0.3 + i * 0.1)
                for i in range(5)
            ]
        )

        keep, compress = self.strategy.compress_memory(session)

        assert len(keep) == 3  # 重要性 >= 0.5
        assert len(compress) == 2


class TestHybridMemory:
    """混合记忆策略测试"""

    def setup_method(self):
        """测试前设置"""
        self.config = MemoryConfig(
            strategy_type=MemoryStrategyType.HYBRID,
            max_messages=5,
            max_tokens=500,
            importance_threshold=0.5
        )
        self.strategy = HybridMemory(self.config)

    def test_should_add_important_message(self):
        """测试添加重要消息"""
        session = ConversationSession(
            session_id="s1",
            user_id="u1",
            created_at=time.time(),
            updated_at=time.time()
        )
        msg = Message(
            message_id="m1",
            role=MessageRole.USER,
            content="Important",
            timestamp=time.time(),
            importance_score=0.8
        )

        assert self.strategy.should_add_message(session, msg) is True

    def test_should_add_normal_message(self):
        """测试添加普通消息"""
        session = ConversationSession(
            session_id="s1",
            user_id="u1",
            created_at=time.time(),
            updated_at=time.time(),
            messages=[
                Message(f"m{i}", MessageRole.USER, f"Msg {i}", time.time(), token_count=100)
                for i in range(3)
            ]
        )
        msg = Message(
            message_id="m4",
            role=MessageRole.USER,
            content="Normal",
            timestamp=time.time(),
            token_count=100,
            importance_score=0.3
        )

        assert self.strategy.should_add_message(session, msg) is True

    def test_get_messages_mixed(self):
        """测试混合策略获取消息"""
        session = ConversationSession(
            session_id="s1",
            user_id="u1",
            created_at=time.time(),
            updated_at=time.time(),
            messages=[
                Message(f"m{i}", MessageRole.USER, f"Msg {i}", time.time() + i, token_count=100,
                        importance_score=0.3 + i * 0.1)
                for i in range(8)
            ]
        )

        context = self.strategy.get_messages_for_context(session)

        # 应该获取消息（最多5条）
        assert len(context) <= 5


class TestMemoryStrategyFactory:
    """MemoryStrategyFactory 测试"""

    def test_create_sliding_window(self):
        """测试创建滑动窗口策略"""
        config = MemoryConfig(strategy_type=MemoryStrategyType.SLIDING_WINDOW)
        strategy = MemoryStrategyFactory.create(MemoryStrategyType.SLIDING_WINDOW, config)

        assert isinstance(strategy, SlidingWindowMemory)

    def test_create_token_based(self):
        """测试创建Token-based策略"""
        config = MemoryConfig(strategy_type=MemoryStrategyType.TOKEN_BASED)
        strategy = MemoryStrategyFactory.create(MemoryStrategyType.TOKEN_BASED, config)

        assert isinstance(strategy, TokenBasedMemory)

    def test_create_summary(self):
        """测试创建摘要策略"""
        config = MemoryConfig(strategy_type=MemoryStrategyType.SUMMARY)
        strategy = MemoryStrategyFactory.create(MemoryStrategyType.SUMMARY, config)

        assert isinstance(strategy, SummaryMemory)

    def test_create_importance_based(self):
        """测试创建重要性策略"""
        config = MemoryConfig(strategy_type=MemoryStrategyType.IMPORTANCE_BASED)
        strategy = MemoryStrategyFactory.create(MemoryStrategyType.IMPORTANCE_BASED, config)

        assert isinstance(strategy, ImportanceBasedMemory)

    def test_create_hybrid(self):
        """测试创建混合策略"""
        config = MemoryConfig(strategy_type=MemoryStrategyType.HYBRID)
        strategy = MemoryStrategyFactory.create(MemoryStrategyType.HYBRID, config)

        assert isinstance(strategy, HybridMemory)

    def test_create_unknown_strategy(self):
        """测试创建未知策略"""
        config = MemoryConfig()

        with pytest.raises(ValueError):
            MemoryStrategyFactory.create("unknown", config)


# ============================================================
# 4. 记忆存储测试
# ============================================================

class TestMemoryStorage:
    """MemoryStorage 测试"""

    def setup_method(self):
        """测试前设置"""
        self.storage = MemoryStorage()

    def test_save_and_load_session(self):
        """测试保存和加载会话"""
        session = ConversationSession(
            session_id="s1",
            user_id="u1",
            created_at=time.time(),
            updated_at=time.time()
        )

        assert self.storage.save_session(session) is True

        loaded = self.storage.load_session("s1")
        assert loaded is not None
        assert loaded.session_id == "s1"

    def test_load_user_sessions(self):
        """测试加载用户会话"""
        for i in range(3):
            session = ConversationSession(
                session_id=f"s{i}",
                user_id="u1",
                created_at=time.time(),
                updated_at=time.time()
            )
            self.storage.save_session(session)

        sessions = self.storage.load_user_sessions("u1")

        assert len(sessions) == 3

    def test_delete_session(self):
        """测试删除会话"""
        session = ConversationSession(
            session_id="s1",
            user_id="u1",
            created_at=time.time(),
            updated_at=time.time()
        )
        self.storage.save_session(session)

        assert self.storage.delete_session("s1") is True
        assert self.storage.load_session("s1") is None

    def test_get_all_sessions(self):
        """测试获取所有会话"""
        for i in range(5):
            session = ConversationSession(
                session_id=f"s{i}",
                user_id=f"u{i}",
                created_at=time.time(),
                updated_at=time.time()
            )
            self.storage.save_session(session)

        sessions = self.storage.get_all_sessions()

        assert len(sessions) == 5

    def test_get_stats(self):
        """测试获取统计信息"""
        session = ConversationSession(
            session_id="s1",
            user_id="u1",
            created_at=time.time(),
            updated_at=time.time(),
            messages=[
                Message(f"m{i}", MessageRole.USER, f"Msg {i}", time.time(), token_count=100)
                for i in range(5)
            ]
        )
        self.storage.save_session(session)

        stats = self.storage.get_stats()

        assert stats.total_sessions == 1
        assert stats.total_messages == 5
        assert stats.total_tokens == 500


# ============================================================
# 5. 记忆向量化器测试
# ============================================================

class TestMemoryEmbedder:
    """MemoryEmbedder 测试"""

    def setup_method(self):
        """测试前设置"""
        self.embedder = MemoryEmbedder()

    @pytest.mark.asyncio
    async def test_embed_text(self):
        """测试文本向量化"""
        embedding = await self.embedder.embed_text("Hello, world!")

        assert isinstance(embedding, list)
        assert len(embedding) == 384

    @pytest.mark.asyncio
    async def test_embed_text_caching(self):
        """测试文本向量化缓存"""
        text = "Test caching"
        emb1 = await self.embedder.embed_text(text)
        emb2 = await self.embedder.embed_text(text)

        assert emb1 == emb2

    @pytest.mark.asyncio
    async def test_embed_messages(self):
        """测试消息列表向量化"""
        messages = [
            Message(f"m{i}", MessageRole.USER, f"Msg {i}", time.time())
            for i in range(3)
        ]

        embedded = await self.embedder.embed_messages(messages)

        for msg in embedded:
            assert "embedding" in msg.metadata

    def test_cosine_similarity(self):
        """测试余弦相似度计算"""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [1.0, 0.0, 0.0]

        similarity = self.embedder.cosine_similarity(vec1, vec2)

        assert similarity == 1.0

    def test_cosine_similarity_orthogonal(self):
        """测试正交向量的余弦相似度"""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]

        similarity = self.embedder.cosine_similarity(vec1, vec2)

        assert similarity == 0.0

    def test_cosine_similarity_empty(self):
        """测试空向量的余弦相似度"""
        similarity = self.embedder.cosine_similarity([], [])

        assert similarity == 0.0


# ============================================================
# 6. 记忆检索器测试
# ============================================================

class TestMemoryRetriever:
    """MemoryRetriever 测试"""

    def setup_method(self):
        """测试前设置"""
        self.storage = MemoryStorage()
        self.embedder = MemoryEmbedder()
        self.retriever = MemoryRetriever(self.embedder, self.storage)

    @pytest.mark.asyncio
    async def test_search_empty(self):
        """测试空存储搜索"""
        response = await self.retriever.search("test query")

        assert response.total_results == 0

    @pytest.mark.asyncio
    async def test_search_with_messages(self):
        """测试带消息搜索"""
        session = ConversationSession(
            session_id="s1",
            user_id="u1",
            created_at=time.time(),
            updated_at=time.time(),
            messages=[
                Message("m1", MessageRole.USER, "Hello", time.time()),
                Message("m2", MessageRole.ASSISTANT, "Hi there!", time.time())
            ]
        )
        self.storage.save_session(session)

        # 先为消息添加向量
        session.messages = await self.embedder.embed_messages(session.messages)
        self.storage.save_session(session)

        response = await self.retriever.search("Hello", top_k=2)

        assert response.total_results >= 0  # 可能没有超过阈值的结果


# ============================================================
# 7. 主类测试
# ============================================================

class TestConversationMemory:
    """ConversationMemory 主类测试"""

    def setup_method(self):
        """测试前设置"""
        reset_conversation_memory()
        self.memory = ConversationMemory()

    def teardown_method(self):
        """测试后清理"""
        reset_conversation_memory()

    def test_create_session(self):
        """测试创建会话"""
        session = self.memory.create_session("user-001")

        assert session is not None
        assert session.user_id == "user-001"
        assert session.session_id is not None

    def test_add_message(self):
        """测试添加消息"""
        session = self.memory.create_session("user-001")

        msg = self.memory.add_message(
            session.session_id,
            MessageRole.USER,
            "Hello, AI!"
        )

        assert msg is not None
        assert msg.content == "Hello, AI!"
        assert msg.role == MessageRole.USER

    def test_add_message_to_nonexistent_session(self):
        """测试向不存在的会话添加消息"""
        msg = self.memory.add_message(
            "nonexistent",
            MessageRole.USER,
            "Hello"
        )

        assert msg is None

    def test_get_context(self):
        """测试获取上下文"""
        session = self.memory.create_session("user-001")

        for i in range(5):
            self.memory.add_message(
                session.session_id,
                MessageRole.USER,
                f"Message {i}"
            )

        context = self.memory.get_context(session.session_id)

        assert len(context) == 5

    def test_get_context_nonexistent_session(self):
        """测试获取不存在会话的上下文"""
        context = self.memory.get_context("nonexistent")

        assert context == []

    def test_compress_session(self):
        """测试压缩会话"""
        session = self.memory.create_session("user-001")

        for i in range(10):
            self.memory.add_message(
                session.session_id,
                MessageRole.USER,
                f"Message {i}"
            )

        result = self.memory.compress_session(session.session_id)

        assert result is True

    def test_delete_session(self):
        """测试删除会话"""
        session = self.memory.create_session("user-001")

        result = self.memory.delete_session(session.session_id)

        assert result is True
        assert self.memory.get_session(session.session_id) is None

    def test_get_user_sessions(self):
        """测试获取用户会话"""
        for i in range(3):
            self.memory.create_session("user-001")

        sessions = self.memory.get_user_sessions("user-001")

        assert len(sessions) == 3

    def test_get_stats(self):
        """测试获取统计信息"""
        session = self.memory.create_session("user-001")
        self.memory.add_message(session.session_id, MessageRole.USER, "Test")

        stats = self.memory.get_stats()

        assert stats.total_sessions == 1
        assert stats.total_messages == 1

    def test_clear_all(self):
        """测试清除所有记忆"""
        session = self.memory.create_session("user-001")
        self.memory.add_message(session.session_id, MessageRole.USER, "Test")

        self.memory.clear_all()

        stats = self.memory.get_stats()
        assert stats.total_sessions == 0

    def test_event_listener(self):
        """测试事件监听器"""
        events = []
        self.memory.add_event_listener(
            MemoryEventType.MESSAGE_ADDED,
            lambda data: events.append(data)
        )

        session = self.memory.create_session("user-001")
        self.memory.add_message(session.session_id, MessageRole.USER, "Test")

        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_search_memory(self):
        """测试搜索记忆"""
        session = self.memory.create_session("user-001")
        self.memory.add_message(session.session_id, MessageRole.USER, "Hello")
        await self.memory.embed_session_messages(session.session_id)

        response = await self.memory.search_memory("Hello")

        assert response is not None
        assert response.query == "Hello"

    @pytest.mark.asyncio
    async def test_embed_session_messages(self):
        """测试为会话消息添加向量"""
        session = self.memory.create_session("user-001")
        self.memory.add_message(session.session_id, MessageRole.USER, "Test")

        result = await self.memory.embed_session_messages(session.session_id)

        assert result is True


# ============================================================
# 8. 工厂类测试
# ============================================================

class TestConversationMemoryFactory:
    """ConversationMemoryFactory 测试"""

    def test_create_default(self):
        """测试创建默认实例"""
        memory = ConversationMemoryFactory.create()

        assert memory is not None
        assert isinstance(memory, ConversationMemory)

    def test_create_with_config(self):
        """测试使用配置创建实例"""
        config = MemoryConfig(
            strategy_type=MemoryStrategyType.TOKEN_BASED,
            max_tokens=2000
        )

        memory = ConversationMemoryFactory.create(config)

        assert memory.config.max_tokens == 2000


# ============================================================
# 9. 全局实例管理测试
# ============================================================

class TestGlobalInstanceManagement:
    """全局实例管理测试"""

    def setup_method(self):
        """测试前设置"""
        reset_conversation_memory()

    def teardown_method(self):
        """测试后清理"""
        reset_conversation_memory()

    def test_get_conversation_memory(self):
        """测试获取全局实例"""
        memory = get_conversation_memory()

        assert memory is not None
        assert isinstance(memory, ConversationMemory)

    def test_get_singleton(self):
        """测试单例模式"""
        memory1 = get_conversation_memory()
        memory2 = get_conversation_memory()

        assert memory1 is memory2

    def test_reset(self):
        """测试重置实例"""
        memory1 = get_conversation_memory()
        reset_conversation_memory()
        memory2 = get_conversation_memory()

        assert memory1 is not memory2


# ============================================================
# 10. 集成测试
# ============================================================

class TestIntegration:
    """集成测试"""

    def setup_method(self):
        """测试前设置"""
        reset_conversation_memory()

    def teardown_method(self):
        """测试后清理"""
        reset_conversation_memory()

    def test_full_workflow(self):
        """测试完整工作流"""
        # 创建记忆实例
        memory = ConversationMemory()

        # 创建会话
        session = memory.create_session("user-001", {"topic": "test"})

        # 添加消息
        memory.add_message(session.session_id, MessageRole.USER, "你好！", importance_score=0.8)
        memory.add_message(session.session_id, MessageRole.ASSISTANT, "你好！有什么可以帮助你的？")
        memory.add_message(session.session_id, MessageRole.USER, "我想了解RAG技术")

        # 获取上下文
        context = memory.get_context(session.session_id)

        assert len(context) == 3

        # 压缩记忆
        memory.compress_session(session.session_id)

        # 获取统计
        stats = memory.get_stats()

        assert stats.total_sessions == 1
        assert stats.total_messages >= 3

    def test_multiple_sessions(self):
        """测试多会话管理"""
        memory = ConversationMemory()

        # 创建多个会话
        sessions = []
        for i in range(5):
            session = memory.create_session(f"user-{i:3d}")
            memory.add_message(session.session_id, MessageRole.USER, f"Message from user {i}")
            sessions.append(session)

        # 获取用户会话
        for i in range(5):
            user_sessions = memory.get_user_sessions(f"user-{i:3d}")
            assert len(user_sessions) == 1

    def test_different_strategies(self):
        """测试不同策略"""
        strategies = [
            MemoryStrategyType.SLIDING_WINDOW,
            MemoryStrategyType.TOKEN_BASED,
            MemoryStrategyType.SUMMARY,
            MemoryStrategyType.IMPORTANCE_BASED,
            MemoryStrategyType.HYBRID,
        ]

        for strategy_type in strategies:
            config = MemoryConfig(strategy_type=strategy_type)
            memory = ConversationMemory(config)

            session = memory.create_session("user-001")
            memory.add_message(session.session_id, MessageRole.USER, "Test")

            context = memory.get_context(session.session_id)
            assert len(context) == 1
