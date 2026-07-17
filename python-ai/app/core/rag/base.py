"""
Base Classes - 策略基类

定义 RAG 模块的策略基类接口，提供统一的规范。

功能：
- 定义策略基类接口
- 提供通用方法实现
- 增强类型检查
- 便于单元测试

设计模式：
- 模板方法模式：定义算法骨架
- 策略模式：统一策略接口

作者：Claude
日期：2026-07-22
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any


class BaseStrategy(ABC):
    """
    策略基类

    所有策略类的抽象基类，定义统一的接口规范。
    """

    @abstractmethod
    def get_strategy_name(self) -> str:
        """获取策略名称"""
        pass

    @abstractmethod
    def get_strategy_type(self) -> Enum:
        """获取策略类型"""
        pass


class BaseCompressionStrategy(BaseStrategy):
    """
    压缩策略基类

    定义文本压缩策略的接口规范。
    """

    @abstractmethod
    async def compress(
        self,
        text: str,
        config: Any,
        **kwargs
    ) -> Any:
        """
        压缩文本

        Args:
            text: 原始文本
            config: 压缩配置

        Returns:
            压缩结果
        """
        pass

    @abstractmethod
    def estimate_tokens(self, text: str) -> int:
        """
        估算 token 数

        Args:
            text: 文本

        Returns:
            估算的 token 数
        """
        pass


class BaseReflectionStrategy(BaseStrategy):
    """
    反思策略基类

    定义答案反思策略的接口规范。
    """

    @abstractmethod
    async def reflect(
        self,
        query: str,
        answer: str,
        context: str,
        config: Any,
        **kwargs
    ) -> Any:
        """
        反思答案质量

        Args:
            query: 原始查询
            answer: 生成的答案
            context: 检索的上下文
            config: 反思配置

        Returns:
            反思结果
        """
        pass


class BaseDecompositionStrategy(BaseStrategy):
    """
    分解策略基类

    定义问题分解策略的接口规范。
    """

    @abstractmethod
    async def decompose(
        self,
        query: str,
        intent: Any,
        config: Any,
        **kwargs
    ) -> Any:
        """
        分解问题

        Args:
            query: 原始问题
            intent: 意图分析结果
            config: 分解配置

        Returns:
            分解结果
        """
        pass


class BaseRoutingStrategy(BaseStrategy):
    """
    路由策略基类

    定义查询路由策略的接口规范。
    """

    @abstractmethod
    async def route(
        self,
        query: str,
        intent: Any,
        config: Any,
        **kwargs
    ) -> Any:
        """
        路由查询

        Args:
            query: 用户查询
            intent: 意图分析结果
            config: 路由配置

        Returns:
            路由结果
        """
        pass


class BaseEvaluationStrategy(BaseStrategy):
    """
    评估策略基类

    定义答案评估策略的接口规范。
    """

    @abstractmethod
    async def evaluate(
        self,
        query: str,
        answer: str,
        context: str,
        config: Any,
        **kwargs
    ) -> Any:
        """
        评估答案质量

        Args:
            query: 原始查询
            answer: 生成的答案
            context: 检索的上下文
            config: 评估配置

        Returns:
            评估结果
        """
        pass


class BaseMemoryStrategy(BaseStrategy):
    """
    记忆策略基类

    定义对话记忆策略的接口规范。
    """

    @abstractmethod
    async def add_message(
        self,
        message: dict[str, Any],
        **kwargs
    ) -> None:
        """
        添加消息到记忆

        Args:
            message: 消息内容
        """
        pass

    @abstractmethod
    async def get_context(
        self,
        query: str,
        max_tokens: int | None = None,
        **kwargs
    ) -> list[dict[str, Any]]:
        """
        获取相关上下文

        Args:
            query: 当前查询
            max_tokens: 最大 token 数

        Returns:
            相关消息列表
        """
        pass

    @abstractmethod
    def clear(self) -> None:
        """清空记忆"""
        pass


class BaseWorkflowNode(ABC):
    """
    工作流节点基类

    定义工作流节点的接口规范。
    """

    @abstractmethod
    async def execute(
        self,
        context: dict[str, Any],
        **kwargs
    ) -> dict[str, Any]:
        """
        执行节点

        Args:
            context: 执行上下文

        Returns:
            执行结果
        """
        pass

    @abstractmethod
    def get_node_type(self) -> str:
        """获取节点类型"""
        pass

    @abstractmethod
    def validate(self) -> bool:
        """验证节点配置"""
        pass
