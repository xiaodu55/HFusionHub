"""
RAG Data Models - 数据模型定义

包含意图分类、复杂度评估、领域识别等核心数据结构
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


class IntentType(str, Enum):
    """
    意图类型枚举

    用于分类用户查询的意图类型
    """
    FACTUAL = "factual"           # 事实查询：Python是什么？
    COMPARISON = "comparison"     # 比较分析：A和B有什么区别？
    SUMMARY = "summary"           # 总结归纳：总结一下xxx
    OPERATION = "operation"       # 操作指令：帮我创建xxx
    CHITCHAT = "chitchat"         # 闲聊：你好
    UNKNOWN = "unknown"           # 未知意图


class ComplexityLevel(str, Enum):
    """
    复杂度级别枚举

    用于评估查询的复杂程度
    """
    SIMPLE = "simple"     # 简单：单一实体，单一关系
    MEDIUM = "medium"     # 中等：多个实体，单一关系
    COMPLEX = "complex"   # 复杂：多个实体，多个关系，需要推理


class DomainType(str, Enum):
    """
    领域类型枚举

    用于识别查询所属领域
    """
    TECH = "tech"           # 技术领域
    BUSINESS = "business"   # 业务领域
    GENERAL = "general"     # 通用领域


@dataclass
class IntentResult:
    """
    意图分类结果

    包含意图类型、复杂度、领域、置信度等信息
    """
    intent: IntentType
    complexity: ComplexityLevel
    domain: DomainType
    confidence: float  # 0.0 - 1.0
    entities: List[str] = field(default_factory=list)
    reasoning: str = ""
    processing_strategy: str = "simple_retrieval"

    def should_decompose(self) -> bool:
        """是否需要分解问题"""
        return self.complexity == ComplexityLevel.COMPLEX

    def needs_tool(self) -> bool:
        """是否需要使用工具"""
        return self.intent == IntentType.OPERATION

    def is_direct_llm(self) -> bool:
        """是否直接使用 LLM 回复"""
        return self.intent == IntentType.CHITCHAT

    def needs_retrieval(self) -> bool:
        """是否需要检索"""
        return self.intent in [
            IntentType.FACTUAL,
            IntentType.COMPARISON,
            IntentType.SUMMARY
        ]

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "intent": self.intent.value,
            "complexity": self.complexity.value,
            "domain": self.domain.value,
            "confidence": self.confidence,
            "entities": self.entities,
            "reasoning": self.reasoning,
            "processing_strategy": self.processing_strategy
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IntentResult":
        """从字典创建"""
        return cls(
            intent=IntentType(data["intent"]),
            complexity=ComplexityLevel(data["complexity"]),
            domain=DomainType(data["domain"]),
            confidence=float(data["confidence"]),
            entities=data.get("entities", []),
            reasoning=data.get("reasoning", ""),
            processing_strategy=data.get("processing_strategy", "simple_retrieval")
        )

    def __str__(self) -> str:
        """字符串表示"""
        return (
            f"IntentResult("
            f"intent={self.intent.value}, "
            f"complexity={self.complexity.value}, "
            f"domain={self.domain.value}, "
            f"confidence={self.confidence:.2f}"
            f")"
        )
