"""
Intent Classifier - 意图分类器

包含工厂类和主类，提供完整的意图分类功能

设计模式：
- 策略模式：支持多种分类策略
- 工厂模式：统一创建分类器实例
- 缓存模式：减少重复分类计算

作者：Claude
日期：2026-07-22
"""

import logging
import threading
from enum import Enum
from typing import Any

from ..llm import BaseLLM
from .cache import CacheManager
from .models import IntentResult
from .strategies import (
    ClassificationStrategy,
    HybridClassificationStrategy,
    LLMClassificationStrategy,
    RuleClassificationStrategy,
)

logger = logging.getLogger(__name__)


class ClassificationStrategyType(Enum):
    """分类策略类型"""
    LLM = "llm"
    RULE = "rule"
    HYBRID = "hybrid"


class IntentClassifierFactory:
    """
    意图分类器工厂

    用于创建不同策略的分类器实例
    """

    _strategies = {
        ClassificationStrategyType.LLM: LLMClassificationStrategy,
        ClassificationStrategyType.RULE: RuleClassificationStrategy,
        ClassificationStrategyType.HYBRID: HybridClassificationStrategy,
    }

    @classmethod
    def create(
        cls,
        strategy_type: ClassificationStrategyType = ClassificationStrategyType.HYBRID,
        llm: BaseLLM | None = None,
        **kwargs
    ) -> ClassificationStrategy:
        """
        创建分类器实例

        Args:
            strategy_type: 策略类型
            llm: LLM 实例（可选）

        Returns:
            ClassificationStrategy 实例

        Raises:
            ValueError: 未知的策略类型
        """
        strategy_class = cls._strategies.get(strategy_type)

        if strategy_class is None:
            raise ValueError(f"Unknown strategy type: {strategy_type}")

        # 注入依赖
        if strategy_type in [
            ClassificationStrategyType.LLM,
            ClassificationStrategyType.HYBRID
        ]:
            return strategy_class(llm=llm)

        return strategy_class()

    @classmethod
    def register(
        cls,
        strategy_type: ClassificationStrategyType,
        strategy_class: type
    ):
        """注册新的策略类"""
        cls._strategies[strategy_type] = strategy_class
        logger.info(f"Registered strategy: {strategy_type.value}")

    @classmethod
    def get_available_strategies(cls) -> list[str]:
        """获取可用的策略列表"""
        return [st.value for st in cls._strategies.keys()]


# M13: classify_sync 使用的共享线程池 — 每次调用新建 ThreadPoolExecutor 会泄漏线程
_classify_executor = None
_classify_executor_lock = threading.Lock()


def _get_classify_executor():
    """返回进程级共享的同步分类线程池（有界：4 workers）。"""
    global _classify_executor
    if _classify_executor is None:
        with _classify_executor_lock:
            if _classify_executor is None:
                import concurrent.futures
                _classify_executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=4, thread_name_prefix="intent-classify"
                )
    return _classify_executor


class IntentClassifier:
    """
    意图分类器主类

    提供完整的意图分类功能，支持缓存和日志

    使用示例：
        # 使用默认配置
        classifier = IntentClassifier()

        # 自定义配置
        classifier = IntentClassifier(
            strategy=IntentClassifierFactory.create(ClassificationStrategyType.LLM),
            cache_enabled=True,
            cache_ttl=7200
        )

        # 分类查询
        result = await classifier.classify("什么是RAG？")
    """

    def __init__(
        self,
        strategy: ClassificationStrategy | None = None,
        cache_enabled: bool = True,
        cache_ttl: int = 3600,
        cache: CacheManager | None = None
    ):
        """
        初始化意图分类器

        Args:
            strategy: 分类策略（默认使用混合策略）
            cache_enabled: 是否启用缓存
            cache_ttl: 缓存过期时间（秒）
            cache: 缓存管理器实例（可选）
        """
        self.strategy = strategy or IntentClassifierFactory.create(
            ClassificationStrategyType.HYBRID
        )

        # 使用提供的缓存管理器或创建新的
        if cache is not None:
            self._cache_manager = cache
        else:
            self._cache_manager = CacheManager(
                enabled=cache_enabled,
                ttl=cache_ttl,
                max_size=500,
                name="intent_classifier"
            )

        # 保持向后兼容
        self.cache_enabled = self._cache_manager.enabled
        self.cache_ttl = self._cache_manager.ttl

    async def classify(
        self,
        query: str,
        history: list[dict[str, str]] | None = None,
        **kwargs
    ) -> IntentResult:
        """
        分类用户查询

        Args:
            query: 用户查询
            history: 对话历史 [{"role": "user/assistant", "content": "..."}]

        Returns:
            IntentResult 分类结果
        """

        # 检查缓存
        cache_key = self._get_cache_key(query, history)
        cached_result = self._cache_manager.get(cache_key)
        if cached_result is not None:
            logger.debug(f"Cache hit for query: {query[:30]}...")
            return cached_result

        # 执行分类
        result = await self.strategy.classify(query, history, **kwargs)

        # 更新缓存
        self._cache_manager.set(cache_key, result)

        # 记录日志
        self._log_classification(query, result)

        return result

    def classify_sync(
        self,
        query: str,
        history: list[dict[str, str]] | None = None,
        **kwargs
    ) -> IntentResult:
        """
        同步分类（用于测试）

        Args:
            query: 用户查询
            history: 对话历史

        Returns:
            IntentResult 分类结果
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果事件循环正在运行，使用共享线程池
                # （M13: 不再每次调用新建 ThreadPoolExecutor 造成线程泄漏）
                return _get_classify_executor().submit(
                    asyncio.run,
                    self.classify(query, history, **kwargs)
                ).result()
            else:
                return loop.run_until_complete(
                    self.classify(query, history, **kwargs)
                )
        except RuntimeError:
            return asyncio.run(self.classify(query, history, **kwargs))

    def _get_cache_key(
        self,
        query: str,
        history: list[dict[str, str]] | None
    ) -> str:
        """生成缓存键"""
        import hashlib
        import json

        key_data = {
            "query": query,
            "history": history[-3:] if history else []
        }
        return hashlib.md5(
            json.dumps(key_data, ensure_ascii=False).encode()
        ).hexdigest()

    def _log_classification(self, query: str, result: IntentResult):
        """记录分类日志"""
        logger.info(
            f"Intent classified: "
            f"intent={result.intent.value}, "
            f"complexity={result.complexity.value}, "
            f"confidence={result.confidence:.2f}, "
            f"strategy={result.processing_strategy}, "
            f"query='{query[:50]}...'"
        )

    def clear_cache(self):
        """清空缓存"""
        self._cache_manager.clear()
        logger.debug("Intent classifier cache cleared")

    def get_cache_stats(self) -> dict[str, Any]:
        """获取缓存统计"""
        return self._cache_manager.get_stats().to_dict()

    def get_strategy_name(self) -> str:
        """获取当前策略名称"""
        return self.strategy.get_strategy_name()
