"""
RAG Configuration - RAG 配置管理

提供统一的配置管理，整合所有 RAG 模块的配置。

功能：
- 统一配置管理
- 支持配置文件加载
- 支持环境变量覆盖
- 配置验证

设计模式：
- 单例模式：全局唯一配置实例
- 建构器模式：支持链式配置

作者：Claude
日期：2026-07-22
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CacheConfig:
    """
    缓存配置

    Attributes:
        enabled: 是否启用缓存
        ttl: 缓存过期时间（秒）
        max_size: 最大缓存容量
    """
    enabled: bool = True
    ttl: int = 3600
    max_size: int = 1000

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "enabled": self.enabled,
            "ttl": self.ttl,
            "max_size": self.max_size,
        }


@dataclass
class CompressionConfig:
    """
    压缩配置

    Attributes:
        strategy: 压缩策略类型
        target_ratio: 目标压缩率
        max_tokens: 最大 token 数
        preserve_keywords: 保留的关键词
        language: 语言
        min_sentence_length: 最小句子长度
    """
    strategy: str = "extractive"
    target_ratio: float = 0.5
    max_tokens: int | None = None
    preserve_keywords: list[str] | None = None
    language: str = "zh"
    min_sentence_length: int = 10

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "strategy": self.strategy,
            "target_ratio": self.target_ratio,
            "max_tokens": self.max_tokens,
            "preserve_keywords": self.preserve_keywords,
            "language": self.language,
            "min_sentence_length": self.min_sentence_length,
        }


@dataclass
class ReflectionConfig:
    """
    反思配置

    Attributes:
        strategy: 反思策略类型
        quality_threshold: 质量阈值
        max_retries: 最大重试次数
        dimensions: 评估维度权重
        confidence_threshold: 置信度阈值
    """
    strategy: str = "hybrid"
    quality_threshold: float = 0.7
    max_retries: int = 3
    dimensions: dict[str, float] | None = None
    confidence_threshold: float = 0.6

    def __post_init__(self):
        """初始化默认值"""
        if self.dimensions is None:
            self.dimensions = {
                "completeness": 0.3,
                "accuracy": 0.3,
                "relevance": 0.2,
                "clarity": 0.2,
            }

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "strategy": self.strategy,
            "quality_threshold": self.quality_threshold,
            "max_retries": self.max_retries,
            "dimensions": self.dimensions,
            "confidence_threshold": self.confidence_threshold,
        }


@dataclass
class DecompositionConfig:
    """
    分解配置

    Attributes:
        strategy: 分解策略类型
        max_sub_questions: 最大子问题数
        max_depth: 最大递归深度
        parallel_threshold: 并行执行阈值
        merge_strategy: 合并策略
    """
    strategy: str = "hybrid"
    max_sub_questions: int = 5
    max_depth: int = 3
    parallel_threshold: float = 0.7
    merge_strategy: str = "concatenation"

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "strategy": self.strategy,
            "max_sub_questions": self.max_sub_questions,
            "max_depth": self.max_depth,
            "parallel_threshold": self.parallel_threshold,
            "merge_strategy": self.merge_strategy,
        }


@dataclass
class RoutingConfig:
    """
    路由配置

    Attributes:
        strategy: 路由策略类型
        confidence_threshold: 置信度阈值
        fallback_channel: 回退通道
        enable_multi_channel: 是否启用多通道
    """
    strategy: str = "adaptive"
    confidence_threshold: float = 0.7
    fallback_channel: str = "vector"
    enable_multi_channel: bool = True

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "strategy": self.strategy,
            "confidence_threshold": self.confidence_threshold,
            "fallback_channel": self.fallback_channel,
            "enable_multi_channel": self.enable_multi_channel,
        }


@dataclass
class MemoryConfig:
    """
    记忆配置

    Attributes:
        strategy: 记忆策略类型
        max_messages: 最大消息数
        max_tokens: 最大 token 数
        summary_threshold: 摘要阈值
        importance_threshold: 重要性阈值
    """
    strategy: str = "hybrid"
    max_messages: int = 100
    max_tokens: int = 4000
    summary_threshold: int = 50
    importance_threshold: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "strategy": self.strategy,
            "max_messages": self.max_messages,
            "max_tokens": self.max_tokens,
            "summary_threshold": self.summary_threshold,
            "importance_threshold": self.importance_threshold,
        }


@dataclass
class EvaluatorConfig:
    """
    评估配置

    Attributes:
        strategy: 评估策略类型
        faithfulness_threshold: 忠实度阈值
        relevancy_threshold: 相关性阈值
        correctness_threshold: 正确性阈值
        dimensions: 评估维度权重
    """
    strategy: str = "hybrid"
    faithfulness_threshold: float = 0.7
    relevancy_threshold: float = 0.7
    correctness_threshold: float = 0.7
    dimensions: dict[str, float] | None = None

    def __post_init__(self):
        """初始化默认值"""
        if self.dimensions is None:
            self.dimensions = {
                "faithfulness": 0.3,
                "relevancy": 0.3,
                "correctness": 0.2,
                "completeness": 0.2,
            }

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "strategy": self.strategy,
            "faithfulness_threshold": self.faithfulness_threshold,
            "relevancy_threshold": self.relevancy_threshold,
            "correctness_threshold": self.correctness_threshold,
            "dimensions": self.dimensions,
        }


@dataclass
class WorkflowConfig:
    """
    工作流配置

    Attributes:
        max_concurrent_nodes: 最大并发节点数
        node_timeout: 节点超时时间（秒）
        workflow_timeout: 工作流超时时间（秒）
        enable_checkpoint: 是否启用检查点
    """
    max_concurrent_nodes: int = 10
    node_timeout: int = 300
    workflow_timeout: int = 3600
    enable_checkpoint: bool = True

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "max_concurrent_nodes": self.max_concurrent_nodes,
            "node_timeout": self.node_timeout,
            "workflow_timeout": self.workflow_timeout,
            "enable_checkpoint": self.enable_checkpoint,
        }


@dataclass
class RAGConfig:
    """
    RAG 统一配置

    整合所有 RAG 模块的配置，支持统一管理。

    使用示例：
        # 使用默认配置
        config = RAGConfig()

        # 自定义配置
        config = RAGConfig(
            cache=CacheConfig(ttl=7200),
            compression=CompressionConfig(target_ratio=0.3),
        )

        # 从文件加载
        config = RAGConfig.from_file("config.yaml")

        # 从环境变量加载
        config = RAGConfig.from_env()
    """
    # 缓存配置
    cache: CacheConfig = field(default_factory=CacheConfig)

    # 压缩配置
    compression: CompressionConfig = field(default_factory=CompressionConfig)

    # 反思配置
    reflection: ReflectionConfig = field(default_factory=ReflectionConfig)

    # 分解配置
    decomposition: DecompositionConfig = field(default_factory=DecompositionConfig)

    # 路由配置
    routing: RoutingConfig = field(default_factory=RoutingConfig)

    # 记忆配置
    memory: MemoryConfig = field(default_factory=MemoryConfig)

    # 评估配置
    evaluator: EvaluatorConfig = field(default_factory=EvaluatorConfig)

    # 工作流配置
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "cache": self.cache.to_dict(),
            "compression": self.compression.to_dict(),
            "reflection": self.reflection.to_dict(),
            "decomposition": self.decomposition.to_dict(),
            "routing": self.routing.to_dict(),
            "memory": self.memory.to_dict(),
            "evaluator": self.evaluator.to_dict(),
            "workflow": self.workflow.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'RAGConfig':
        """从字典创建配置"""
        return cls(
            cache=CacheConfig(**data.get("cache", {})),
            compression=CompressionConfig(**data.get("compression", {})),
            reflection=ReflectionConfig(**data.get("reflection", {})),
            decomposition=DecompositionConfig(**data.get("decomposition", {})),
            routing=RoutingConfig(**data.get("routing", {})),
            memory=MemoryConfig(**data.get("memory", {})),
            evaluator=EvaluatorConfig(**data.get("evaluator", {})),
            workflow=WorkflowConfig(**data.get("workflow", {})),
        )

    @classmethod
    def from_file(cls, file_path: str) -> 'RAGConfig':
        """
        从配置文件加载

        Args:
            file_path: 配置文件路径（支持 JSON 和 YAML）

        Returns:
            RAGConfig 实例
        """
        path = Path(file_path)

        if not path.exists():
            logger.warning(f"Config file not found: {file_path}, using defaults")
            return cls()

        with open(path, encoding="utf-8") as f:
            if path.suffix == ".json":
                data = json.load(f)
            elif path.suffix in [".yaml", ".yml"]:
                try:
                    import yaml
                    data = yaml.safe_load(f)
                except ImportError:
                    logger.warning("PyYAML not installed, using JSON parser")
                    data = json.load(f)
            else:
                raise ValueError(f"Unsupported config file format: {path.suffix}")

        return cls.from_dict(data)

    @classmethod
    def from_env(cls) -> 'RAGConfig':
        """
        从环境变量加载

        环境变量格式：
            RAG_CACHE_ENABLED=true
            RAG_CACHE_TTL=7200
            RAG_COMPRESSION_TARGET_RATIO=0.3

        Returns:
            RAGConfig 实例
        """
        config = cls()

        # 缓存配置
        if os.getenv("RAG_CACHE_ENABLED"):
            config.cache.enabled = os.getenv("RAG_CACHE_ENABLED").lower() == "true"
        if os.getenv("RAG_CACHE_TTL"):
            config.cache.ttl = int(os.getenv("RAG_CACHE_TTL"))
        if os.getenv("RAG_CACHE_MAX_SIZE"):
            config.cache.max_size = int(os.getenv("RAG_CACHE_MAX_SIZE"))

        # 压缩配置
        if os.getenv("RAG_COMPRESSION_TARGET_RATIO"):
            config.compression.target_ratio = float(os.getenv("RAG_COMPRESSION_TARGET_RATIO"))
        if os.getenv("RAG_COMPRESSION_LANGUAGE"):
            config.compression.language = os.getenv("RAG_COMPRESSION_LANGUAGE")

        # 反思配置
        if os.getenv("RAG_REFLECTION_QUALITY_THRESHOLD"):
            config.reflection.quality_threshold = float(os.getenv("RAG_REFLECTION_QUALITY_THRESHOLD"))
        if os.getenv("RAG_REFLECTION_CONFIDENCE_THRESHOLD"):
            # A4：groundedness 守卫的词汇支持分阈值（此前全仓库无消费方）
            config.reflection.confidence_threshold = float(os.getenv("RAG_REFLECTION_CONFIDENCE_THRESHOLD"))
        if os.getenv("RAG_REFLECTION_MAX_RETRIES"):
            config.reflection.max_retries = int(os.getenv("RAG_REFLECTION_MAX_RETRIES"))

        # 路由配置
        if os.getenv("RAG_ROUTING_CONFIDENCE_THRESHOLD"):
            config.routing.confidence_threshold = float(os.getenv("RAG_ROUTING_CONFIDENCE_THRESHOLD"))

        # 记忆配置
        if os.getenv("RAG_MEMORY_MAX_MESSAGES"):
            config.memory.max_messages = int(os.getenv("RAG_MEMORY_MAX_MESSAGES"))
        if os.getenv("RAG_MEMORY_MAX_TOKENS"):
            config.memory.max_tokens = int(os.getenv("RAG_MEMORY_MAX_TOKENS"))

        return config

    def save(self, file_path: str):
        """
        保存配置到文件

        Args:
            file_path: 配置文件路径
        """
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

        logger.info(f"Config saved to: {file_path}")


# ==================== 全局配置实例 ====================

_global_config: RAGConfig | None = None


def get_config() -> RAGConfig:
    """
    获取全局配置

    Returns:
        RAGConfig 实例
    """
    global _global_config
    if _global_config is None:
        _global_config = RAGConfig()
    return _global_config


def set_config(config: RAGConfig):
    """
    设置全局配置

    Args:
        config: RAGConfig 实例
    """
    global _global_config
    _global_config = config


def reset_config():
    """重置全局配置"""
    global _global_config
    _global_config = None
