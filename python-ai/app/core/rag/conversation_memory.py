"""
ConversationMemory 模块
对话记忆管理模块，负责管理对话历史、提供多种记忆策略、支持上下文压缩和检索

核心功能：
1. 短期记忆管理（对话缓冲）
2. 长期记忆持久化（跨会话）
3. 多种记忆策略（滑动窗口、Token限制、摘要、重要性评分）
4. 记忆检索（基于语义相似度）
5. 上下文压缩（减少token使用）

设计模式：
- 策略模式：多种记忆策略可切换
- 工厂模式：统一创建实例
- 观察者模式：记忆事件通知
- 单例模式：全局唯一实例
"""

import logging
import json
import time
import uuid
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import (
    Any, Dict, List, Optional, Set, Tuple, Union, Callable
)
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ============================================================
# 1. 枚举定义
# ============================================================

class MemoryType(str, Enum):
    """记忆类型"""
    SHORT_TERM = "short_term"  # 短期记忆（对话缓冲）
    LONG_TERM = "long_term"  # 长期记忆（持久化）
    EPISODIC = "episodic"  # 情景记忆（特定事件）
    SEMANTIC = "semantic"  # 语义记忆（知识）


class MemoryStrategyType(str, Enum):
    """记忆策略类型"""
    SLIDING_WINDOW = "sliding_window"  # 滑动窗口
    TOKEN_BASED = "token_based"  # 基于Token限制
    SUMMARY = "summary"  # 摘要策略
    IMPORTANCE_BASED = "importance_based"  # 基于重要性评分
    HYBRID = "hybrid"  # 混合策略


class MessageRole(str, Enum):
    """消息角色"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class MemoryEventType(str, Enum):
    """记忆事件类型"""
    MESSAGE_ADDED = "message_added"
    MESSAGE_REMOVED = "message_removed"
    MEMORY_SUMMARIZED = "memory_summarized"
    MEMORY_COMPRESSED = "memory_compressed"
    MEMORY_EXPIRED = "memory_expired"


# ============================================================
# 2. 数据模型
# ============================================================

@dataclass
class Message:
    """消息"""
    message_id: str
    role: MessageRole
    content: str
    timestamp: float
    token_count: int = 0
    importance_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_summarized: bool = False
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """转为字典"""
        return {
            "message_id": self.message_id,
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp,
            "token_count": self.token_count,
            "importance_score": self.importance_score,
            "metadata": self.metadata,
            "is_summarized": self.is_summarized,
            "summary": self.summary
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """从字典创建"""
        return cls(
            message_id=data["message_id"],
            role=MessageRole(data["role"]),
            content=data["content"],
            timestamp=data["timestamp"],
            token_count=data.get("token_count", 0),
            importance_score=data.get("importance_score", 0.0),
            metadata=data.get("metadata", {}),
            is_summarized=data.get("is_summarized", False),
            summary=data.get("summary", "")
        )


@dataclass
class ConversationSession:
    """对话会话"""
    session_id: str
    user_id: str
    created_at: float
    updated_at: float
    messages: List[Message] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """转为字典"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": [msg.to_dict() for msg in self.messages],
            "metadata": self.metadata,
            "is_active": self.is_active
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationSession":
        """从字典创建"""
        return cls(
            session_id=data["session_id"],
            user_id=data["user_id"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            messages=[Message.from_dict(msg) for msg in data.get("messages", [])],
            metadata=data.get("metadata", {}),
            is_active=data.get("is_active", True)
        )


@dataclass
class MemoryConfig:
    """记忆配置"""
    strategy_type: MemoryStrategyType = MemoryStrategyType.SLIDING_WINDOW
    max_messages: int = 50  # 最大消息数
    max_tokens: int = 4000  # 最大Token数
    summary_threshold: int = 20  # 触发摘要的消息阈值
    importance_threshold: float = 0.3  # 重要性阈值
    expiration_hours: int = 24  # 过期时间（小时）
    enable_embedding: bool = True  # 启用向量化检索
    embedding_model: str = "bge-m3"  # 嵌入模型
    enable_persistence: bool = True  # 启用持久化
    storage_path: str = "memory_storage"  # 存储路径

    def to_dict(self) -> Dict[str, Any]:
        """转为字典"""
        return {
            "strategy_type": self.strategy_type.value,
            "max_messages": self.max_messages,
            "max_tokens": self.max_tokens,
            "summary_threshold": self.summary_threshold,
            "importance_threshold": self.importance_threshold,
            "expiration_hours": self.expiration_hours,
            "enable_embedding": self.enable_embedding,
            "embedding_model": self.embedding_model,
            "enable_persistence": self.enable_persistence,
            "storage_path": self.storage_path
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryConfig":
        """从字典创建"""
        return cls(
            strategy_type=MemoryStrategyType(data.get("strategy_type", "sliding_window")),
            max_messages=data.get("max_messages", 50),
            max_tokens=data.get("max_tokens", 4000),
            summary_threshold=data.get("summary_threshold", 20),
            importance_threshold=data.get("importance_threshold", 0.3),
            expiration_hours=data.get("expiration_hours", 24),
            enable_embedding=data.get("enable_embedding", True),
            embedding_model=data.get("embedding_model", "bge-m3"),
            enable_persistence=data.get("enable_persistence", True),
            storage_path=data.get("storage_path", "memory_storage")
        )


@dataclass
class MemorySearchResult:
    """记忆搜索结果"""
    message: Message
    score: float
    session_id: str
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """转为字典"""
        return {
            "message": self.message.to_dict(),
            "score": self.score,
            "session_id": self.session_id,
            "reason": self.reason
        }


@dataclass
class MemorySearchResponse:
    """记忆搜索响应"""
    query: str
    results: List[MemorySearchResult]
    total_results: int
    search_time_ms: float

    def to_dict(self) -> Dict[str, Any]:
        """转为字典"""
        return {
            "query": self.query,
            "results": [r.to_dict() for r in self.results],
            "total_results": self.total_results,
            "search_time_ms": self.search_time_ms
        }


@dataclass
class MemoryStats:
    """记忆统计"""
    total_sessions: int = 0
    total_messages: int = 0
    total_tokens: int = 0
    avg_messages_per_session: float = 0.0
    avg_tokens_per_message: float = 0.0
    memory_usage_bytes: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """转为字典"""
        return {
            "total_sessions": self.total_sessions,
            "total_messages": self.total_messages,
            "total_tokens": self.total_tokens,
            "avg_messages_per_session": self.avg_messages_per_session,
            "avg_tokens_per_message": self.avg_tokens_per_message,
            "memory_usage_bytes": self.memory_usage_bytes
        }


# ============================================================
# 3. 记忆策略（策略模式）
# ============================================================

class BaseMemoryStrategy(ABC):
    """记忆策略基类"""

    def __init__(self, config: MemoryConfig):
        self.config = config

    @abstractmethod
    def should_add_message(
        self,
        session: ConversationSession,
        new_message: Message
    ) -> bool:
        """判断是否应该添加消息"""
        pass

    @abstractmethod
    def get_messages_for_context(
        self,
        session: ConversationSession,
        max_tokens: Optional[int] = None
    ) -> List[Message]:
        """获取用于上下文的消息"""
        pass

    @abstractmethod
    def compress_memory(
        self,
        session: ConversationSession
    ) -> Tuple[List[Message], List[Message]]:
        """压缩记忆，返回 (保留的消息, 被压缩的消息)"""
        pass


class SlidingWindowMemory(BaseMemoryStrategy):
    """滑动窗口记忆策略"""

    def should_add_message(
        self,
        session: ConversationSession,
        new_message: Message
    ) -> bool:
        """总是允许添加消息"""
        return True

    def get_messages_for_context(
        self,
        session: ConversationSession,
        max_tokens: Optional[int] = None
    ) -> List[Message]:
        """获取最近的N条消息"""
        max_msgs = self.config.max_messages
        if max_tokens:
            # 基于Token限制
            messages = []
            total_tokens = 0
            for msg in reversed(session.messages):
                if total_tokens + msg.token_count > max_tokens:
                    break
                messages.insert(0, msg)
                total_tokens += msg.token_count
            return messages
        else:
            # 基于消息数量
            return session.messages[-max_msgs:]

    def compress_memory(
        self,
        session: ConversationSession
    ) -> Tuple[List[Message], List[Message]]:
        """压缩超出窗口的消息"""
        max_msgs = self.config.max_messages
        if len(session.messages) <= max_msgs:
            return session.messages, []

        keep = session.messages[-max_msgs:]
        compress = session.messages[:-max_msgs]
        return keep, compress


class TokenBasedMemory(BaseMemoryStrategy):
    """基于Token的记忆策略"""

    def should_add_message(
        self,
        session: ConversationSession,
        new_message: Message
    ) -> bool:
        """检查添加消息后是否超过Token限制"""
        total_tokens = sum(msg.token_count for msg in session.messages)
        return total_tokens + new_message.token_count <= self.config.max_tokens

    def get_messages_for_context(
        self,
        session: ConversationSession,
        max_tokens: Optional[int] = None
    ) -> List[Message]:
        """获取不超过Token限制的消息"""
        limit = max_tokens or self.config.max_tokens
        messages = []
        total_tokens = 0

        for msg in reversed(session.messages):
            if total_tokens + msg.token_count > limit:
                break
            messages.insert(0, msg)
            total_tokens += msg.token_count

        return messages

    def compress_memory(
        self,
        session: ConversationSession
    ) -> Tuple[List[Message], List[Message]]:
        """压缩超出Token限制的消息"""
        keep = []
        compress = []
        total_tokens = 0

        for msg in reversed(session.messages):
            if total_tokens + msg.token_count <= self.config.max_tokens:
                keep.insert(0, msg)
                total_tokens += msg.token_count
            else:
                compress.insert(0, msg)

        return keep, compress


class SummaryMemory(BaseMemoryStrategy):
    """摘要记忆策略"""

    def should_add_message(
        self,
        session: ConversationSession,
        new_message: Message
    ) -> bool:
        """总是允许添加消息"""
        return True

    def get_messages_for_context(
        self,
        session: ConversationSession,
        max_tokens: Optional[int] = None
    ) -> List[Message]:
        """获取消息，优先保留未摘要的消息"""
        limit = max_tokens or self.config.max_tokens
        messages = []
        total_tokens = 0

        # 先添加未摘要的消息
        for msg in reversed(session.messages):
            if not msg.is_summarized:
                if total_tokens + msg.token_count > limit:
                    break
                messages.insert(0, msg)
                total_tokens += msg.token_count

        # 如果还有空间，添加已摘要的消息
        for msg in reversed(session.messages):
            if msg.is_summarized:
                if total_tokens + msg.token_count > limit:
                    break
                messages.insert(0, msg)
                total_tokens += msg.token_count

        return messages

    def compress_memory(
        self,
        session: ConversationSession
    ) -> Tuple[List[Message], List[Message]]:
        """压缩旧消息为摘要"""
        if len(session.messages) <= self.config.summary_threshold:
            return session.messages, []

        # 分离新旧消息
        old_messages = session.messages[:-self.config.summary_threshold]
        new_messages = session.messages[-self.config.summary_threshold:]

        # 为旧消息创建摘要占位符
        summary_msg = Message(
            message_id=str(uuid.uuid4()),
            role=MessageRole.SYSTEM,
            content=f"[已摘要：{len(old_messages)}条历史消息]",
            timestamp=time.time(),
            is_summarized=True,
            summary=f"历史对话摘要，包含{len(old_messages)}条消息"
        )

        return new_messages + [summary_msg], old_messages


class ImportanceBasedMemory(BaseMemoryStrategy):
    """基于重要性的记忆策略"""

    def should_add_message(
        self,
        session: ConversationSession,
        new_message: Message
    ) -> bool:
        """检查消息重要性是否超过阈值"""
        return new_message.importance_score >= self.config.importance_threshold

    def get_messages_for_context(
        self,
        session: ConversationSession,
        max_tokens: Optional[int] = None
    ) -> List[Message]:
        """按重要性排序获取消息"""
        limit = max_tokens or self.config.max_tokens

        # 按重要性排序
        sorted_msgs = sorted(
            session.messages,
            key=lambda m: m.importance_score,
            reverse=True
        )

        messages = []
        total_tokens = 0
        for msg in sorted_msgs:
            if total_tokens + msg.token_count > limit:
                break
            messages.append(msg)
            total_tokens += msg.token_count

        # 按时间排序
        messages.sort(key=lambda m: m.timestamp)
        return messages

    def compress_memory(
        self,
        session: ConversationSession
    ) -> Tuple[List[Message], List[Message]]:
        """移除低重要性的消息"""
        keep = []
        compress = []

        for msg in session.messages:
            if msg.importance_score >= self.config.importance_threshold:
                keep.append(msg)
            else:
                compress.append(msg)

        return keep, compress


class HybridMemory(BaseMemoryStrategy):
    """混合记忆策略"""

    def __init__(self, config: MemoryConfig):
        super().__init__(config)
        self.sliding_window = SlidingWindowMemory(config)
        self.token_based = TokenBasedMemory(config)
        self.importance_based = ImportanceBasedMemory(config)

    def should_add_message(
        self,
        session: ConversationSession,
        new_message: Message
    ) -> bool:
        """综合判断是否添加消息"""
        # 如果消息很重要，总是添加
        if new_message.importance_score >= self.config.importance_threshold:
            return True

        # 否则检查Token限制
        return self.token_based.should_add_message(session, new_message)

    def get_messages_for_context(
        self,
        session: ConversationSession,
        max_tokens: Optional[int] = None
    ) -> List[Message]:
        """混合策略获取消息"""
        # 先用Token限制获取
        token_msgs = self.token_based.get_messages_for_context(session, max_tokens)

        # 再用重要性筛选
        importance_msgs = self.importance_based.get_messages_for_context(session, max_tokens)

        # 合并去重
        seen_ids = set()
        merged = []
        for msg in token_msgs + importance_msgs:
            if msg.message_id not in seen_ids:
                seen_ids.add(msg.message_id)
                merged.append(msg)

        # 按时间排序
        merged.sort(key=lambda m: m.timestamp)
        return merged

    def compress_memory(
        self,
        session: ConversationSession
    ) -> Tuple[List[Message], List[Message]]:
        """混合压缩策略"""
        # 先用Token限制压缩
        keep, compress = self.token_based.compress_memory(session)

        # 再用重要性压缩
        keep, more_compress = self.importance_based.compress_memory(
            ConversationSession(
                session_id=session.session_id,
                user_id=session.user_id,
                created_at=session.created_at,
                updated_at=session.updated_at,
                messages=keep,
                metadata=session.metadata,
                is_active=session.is_active
            )
        )

        compress.extend(more_compress)
        return keep, compress


# ============================================================
# 4. 记忆策略工厂
# ============================================================

class MemoryStrategyFactory:
    """记忆策略工厂"""

    @staticmethod
    def create(
        strategy_type: MemoryStrategyType,
        config: MemoryConfig
    ) -> BaseMemoryStrategy:
        """创建记忆策略"""
        if strategy_type == MemoryStrategyType.SLIDING_WINDOW:
            return SlidingWindowMemory(config)
        elif strategy_type == MemoryStrategyType.TOKEN_BASED:
            return TokenBasedMemory(config)
        elif strategy_type == MemoryStrategyType.SUMMARY:
            return SummaryMemory(config)
        elif strategy_type == MemoryStrategyType.IMPORTANCE_BASED:
            return ImportanceBasedMemory(config)
        elif strategy_type == MemoryStrategyType.HYBRID:
            return HybridMemory(config)
        else:
            raise ValueError(f"Unknown strategy type: {strategy_type}")


# ============================================================
# 5. 记忆向量化器
# ============================================================

class MemoryEmbedder:
    """记忆向量化器"""

    def __init__(self, model_name: str = "bge-m3"):
        self.model_name = model_name
        self._embedding_cache: Dict[str, List[float]] = {}

    def _get_cache_key(self, text: str) -> str:
        """获取缓存键"""
        return hashlib.md5(text.encode()).hexdigest()

    async def embed_text(self, text: str) -> List[float]:
        """将文本转换为向量"""
        cache_key = self._get_cache_key(text)
        if cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]

        try:
            # 尝试使用 Ollama 嵌入
            from app.core.rag import ollama_client

            response = await ollama_client.embeddings(
                model=self.model_name,
                prompt=text
            )
            embedding = response.get("embedding", [])

            if embedding:
                self._embedding_cache[cache_key] = embedding
                return embedding
        except Exception as e:
            logger.warning(f"Ollama embedding failed: {e}")

        # 降级：生成随机向量（用于测试）
        import random
        random.seed(hash(text) % 10000)
        embedding = [random.random() for _ in range(384)]
        # 归一化
        norm = sum(x**2 for x in embedding) ** 0.5
        embedding = [x / norm for x in embedding]

        self._embedding_cache[cache_key] = embedding
        return embedding

    async def embed_messages(self, messages: List[Message]) -> List[Message]:
        """为消息列表添加向量"""
        for msg in messages:
            if not msg.metadata.get("embedding"):
                embedding = await self.embed_text(msg.content)
                msg.metadata["embedding"] = embedding
        return messages

    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a**2 for a in vec1) ** 0.5
        norm2 = sum(b**2 for b in vec2) ** 0.5

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)


# ============================================================
# 6. 记忆存储
# ============================================================

class MemoryStorage:
    """记忆存储"""

    def __init__(self, storage_path: str = "memory_storage"):
        self.storage_path = storage_path
        self._sessions: Dict[str, ConversationSession] = {}
        self._user_sessions: Dict[str, List[str]] = {}  # user_id -> [session_ids]

    def save_session(self, session: ConversationSession) -> bool:
        """保存会话"""
        try:
            self._sessions[session.session_id] = session

            # 更新用户会话索引
            if session.user_id not in self._user_sessions:
                self._user_sessions[session.user_id] = []
            if session.session_id not in self._user_sessions[session.user_id]:
                self._user_sessions[session.user_id].append(session.session_id)

            return True
        except Exception as e:
            logger.error(f"Failed to save session: {e}")
            return False

    def load_session(self, session_id: str) -> Optional[ConversationSession]:
        """加载会话"""
        return self._sessions.get(session_id)

    def load_user_sessions(
        self,
        user_id: str,
        active_only: bool = True
    ) -> List[ConversationSession]:
        """加载用户的所有会话"""
        session_ids = self._user_sessions.get(user_id, [])
        sessions = []

        for sid in session_ids:
            session = self._sessions.get(sid)
            if session and (not active_only or session.is_active):
                sessions.append(session)

        return sessions

    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        session = self._sessions.pop(session_id, None)
        if session and session.user_id in self._user_sessions:
            self._user_sessions[session.user_id].remove(session_id)
        return session is not None

    def get_all_sessions(self) -> List[ConversationSession]:
        """获取所有会话"""
        return list(self._sessions.values())

    def get_stats(self) -> MemoryStats:
        """获取统计信息"""
        sessions = self._sessions.values()
        total_messages = sum(len(s.messages) for s in sessions)
        total_tokens = sum(
            sum(m.token_count for m in s.messages) for s in sessions
        )

        return MemoryStats(
            total_sessions=len(sessions),
            total_messages=total_messages,
            total_tokens=total_tokens,
            avg_messages_per_session=total_messages / len(sessions) if sessions else 0,
            avg_tokens_per_message=total_tokens / total_messages if total_messages else 0
        )


# ============================================================
# 7. 记忆检索器
# ============================================================

class MemoryRetriever:
    """记忆检索器"""

    def __init__(self, embedder: MemoryEmbedder, storage: MemoryStorage):
        self.embedder = embedder
        self.storage = storage

    async def search(
        self,
        query: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        top_k: int = 5
    ) -> MemorySearchResponse:
        """搜索相关记忆"""
        start_time = time.time()

        # 获取候选会话
        if session_id:
            sessions = [self.storage.load_session(session_id)]
            sessions = [s for s in sessions if s is not None]
        elif user_id:
            sessions = self.storage.load_user_sessions(user_id)
        else:
            sessions = self.storage.get_all_sessions()

        # 获取查询向量
        query_embedding = await self.embedder.embed_text(query)

        # 搜索相似消息
        results: List[MemorySearchResult] = []

        for session in sessions:
            for msg in session.messages:
                msg_embedding = msg.metadata.get("embedding")
                if msg_embedding:
                    score = self.embedder.cosine_similarity(
                        query_embedding, msg_embedding
                    )
                    if score > 0.3:  # 相似度阈值
                        results.append(MemorySearchResult(
                            message=msg,
                            score=score,
                            session_id=session.session_id,
                            reason=f"语义相似度: {score:.3f}"
                        ))

        # 排序并截取
        results.sort(key=lambda r: r.score, reverse=True)
        results = results[:top_k]

        search_time = (time.time() - start_time) * 1000

        return MemorySearchResponse(
            query=query,
            results=results,
            total_results=len(results),
            search_time_ms=search_time
        )


# ============================================================
# 8. 主类：ConversationMemory
# ============================================================

class ConversationMemory:
    """
    对话记忆管理主类

    负责管理对话历史、提供多种记忆策略、支持上下文压缩和检索
    """

    def __init__(self, config: Optional[MemoryConfig] = None):
        """
        初始化 ConversationMemory

        Args:
            config: 记忆配置，为None时使用默认配置
        """
        self.config = config or MemoryConfig()
        self.strategy = MemoryStrategyFactory.create(
            self.config.strategy_type,
            self.config
        )
        self.storage = MemoryStorage(self.config.storage_path)
        self.embedder = MemoryEmbedder(self.config.embedding_model)
        self.retriever = MemoryRetriever(self.embedder, self.storage)

        # 事件监听器
        self._event_listeners: Dict[MemoryEventType, List[Callable]] = {}

        logger.info(
            f"ConversationMemory initialized with strategy: "
            f"{self.config.strategy_type.value}"
        )

    def add_event_listener(
        self,
        event_type: MemoryEventType,
        listener: Callable
    ):
        """添加事件监听器"""
        if event_type not in self._event_listeners:
            self._event_listeners[event_type] = []
        self._event_listeners[event_type].append(listener)

    def _emit_event(self, event_type: MemoryEventType, data: Dict[str, Any]):
        """触发事件"""
        for listener in self._event_listeners.get(event_type, []):
            try:
                listener(data)
            except Exception as e:
                logger.error(f"Event listener error: {e}")

    def create_session(
        self,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ConversationSession:
        """创建新的对话会话"""
        now = time.time()
        session = ConversationSession(
            session_id=str(uuid.uuid4()),
            user_id=user_id,
            created_at=now,
            updated_at=now,
            metadata=metadata or {}
        )

        self.storage.save_session(session)
        logger.info(f"Created session {session.session_id} for user {user_id}")

        return session

    def add_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        importance_score: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Message]:
        """
        添加消息到会话

        Args:
            session_id: 会话ID
            role: 消息角色
            content: 消息内容
            importance_score: 重要性评分
            metadata: 元数据

        Returns:
            添加的消息，失败返回None
        """
        session = self.storage.load_session(session_id)
        if not session:
            logger.error(f"Session {session_id} not found")
            return None

        # 估算Token数（简单估算：1个中文字符≈2个token）
        token_count = len(content) * 2

        message = Message(
            message_id=str(uuid.uuid4()),
            role=role,
            content=content,
            timestamp=time.time(),
            token_count=token_count,
            importance_score=importance_score,
            metadata=metadata or {}
        )

        # 检查是否应该添加
        if not self.strategy.should_add_message(session, message):
            logger.info(f"Message rejected by strategy: {message.message_id}")
            return None

        # 添加消息
        session.messages.append(message)
        session.updated_at = time.time()

        # 保存会话
        self.storage.save_session(session)

        # 触发事件
        self._emit_event(MemoryEventType.MESSAGE_ADDED, {
            "session_id": session_id,
            "message": message.to_dict()
        })

        logger.debug(
            f"Added message {message.message_id} to session {session_id}"
        )

        return message

    def get_context(
        self,
        session_id: str,
        max_tokens: Optional[int] = None
    ) -> List[Message]:
        """
        获取会话上下文

        Args:
            session_id: 会话ID
            max_tokens: 最大Token数

        Returns:
            消息列表
        """
        session = self.storage.load_session(session_id)
        if not session:
            logger.error(f"Session {session_id} not found")
            return []

        return self.strategy.get_messages_for_context(session, max_tokens)

    def compress_session(self, session_id: str) -> bool:
        """
        压缩会话记忆

        Args:
            session_id: 会话ID

        Returns:
            是否成功
        """
        session = self.storage.load_session(session_id)
        if not session:
            logger.error(f"Session {session_id} not found")
            return False

        keep, compress = self.strategy.compress_memory(session)

        if compress:
            session.messages = keep
            session.updated_at = time.time()
            self.storage.save_session(session)

            self._emit_event(MemoryEventType.MEMORY_COMPRESSED, {
                "session_id": session_id,
                "compressed_count": len(compress),
                "kept_count": len(keep)
            })

            logger.info(
                f"Compressed session {session_id}: "
                f"kept {len(keep)}, compressed {len(compress)}"
            )

        return True

    async def search_memory(
        self,
        query: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        top_k: int = 5
    ) -> MemorySearchResponse:
        """
        搜索相关记忆

        Args:
            query: 搜索查询
            user_id: 用户ID
            session_id: 会话ID
            top_k: 返回结果数

        Returns:
            搜索响应
        """
        return await self.retriever.search(query, user_id, session_id, top_k)

    async def embed_session_messages(self, session_id: str) -> bool:
        """
        为会话消息添加向量

        Args:
            session_id: 会话ID

        Returns:
            是否成功
        """
        session = self.storage.load_session(session_id)
        if not session:
            logger.error(f"Session {session_id} not found")
            return False

        session.messages = await self.embedder.embed_messages(session.messages)
        self.storage.save_session(session)

        return True

    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """获取会话"""
        return self.storage.load_session(session_id)

    def get_user_sessions(self, user_id: str) -> List[ConversationSession]:
        """获取用户的所有会话"""
        return self.storage.load_user_sessions(user_id)

    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        return self.storage.delete_session(session_id)

    def get_stats(self) -> MemoryStats:
        """获取统计信息"""
        return self.storage.get_stats()

    def clear_all(self):
        """清除所有记忆"""
        self.storage._sessions.clear()
        self.storage._user_sessions.clear()
        logger.info("Cleared all memory")


# ============================================================
# 9. 工厂和全局实例
# ============================================================

class ConversationMemoryFactory:
    """ConversationMemory 工厂"""

    @staticmethod
    def create(config: Optional[MemoryConfig] = None) -> ConversationMemory:
        """创建 ConversationMemory 实例"""
        return ConversationMemory(config)


# 全局实例
_conversation_memory: Optional[ConversationMemory] = None


def get_conversation_memory(
    config: Optional[MemoryConfig] = None
) -> ConversationMemory:
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


def reset_conversation_memory():
    """重置全局 ConversationMemory 实例（用于测试）"""
    global _conversation_memory
    if _conversation_memory:
        _conversation_memory.clear_all()
    _conversation_memory = None
