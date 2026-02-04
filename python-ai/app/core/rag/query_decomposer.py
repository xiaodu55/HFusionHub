"""
Query Decomposer - 问题分解器

将复杂问题分解为子问题，构建问题依赖树，支持并行执行无依赖的子问题。

设计模式：
- 枚举模式：定义分解策略类型、子问题状态
- 策略模式：支持多种分解策略，运行时可切换
- 工厂模式：统一创建逻辑
- 单例模式：全局唯一实例
- 缓存模式：避免重复分解
"""

import hashlib
import time
from enum import Enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Set, Tuple
from loguru import logger

from .models import IntentResult, ComplexityLevel
from .cache import CacheManager, decomposition_cache
from .base import BaseDecompositionStrategy


class DecompositionStrategyType(str, Enum):
    """分解策略类型"""
    LLM = "llm"           # 基于 LLM 的分解
    RULE = "rule"         # 基于规则的分解
    HYBRID = "hybrid"     # 混合分解


class SubQuestionStatus(str, Enum):
    """子问题状态"""
    PENDING = "pending"       # 待处理
    PROCESSING = "processing" # 处理中
    COMPLETED = "completed"   # 已完成
    FAILED = "failed"         # 失败
    SKIPPED = "skipped"       # 跳过


@dataclass
class SubQuestion:
    """
    子问题数据模型

    Attributes:
        id: 子问题唯一标识
        content: 子问题内容
        parent_id: 父问题ID
        depth: 在问题树中的深度
        priority: 优先级（数字越小越优先）
        dependencies: 依赖的子问题ID列表
        status: 当前状态
        answer: 回答内容
        confidence: 回答置信度
        metadata: 元数据
    """
    id: str
    content: str
    parent_id: Optional[str] = None
    depth: int = 0
    priority: int = 0
    dependencies: List[str] = field(default_factory=list)
    status: SubQuestionStatus = SubQuestionStatus.PENDING
    answer: Optional[str] = None
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def can_execute(self, completed_ids: Set[str]) -> bool:
        """检查是否可以执行（依赖是否已满足）"""
        if self.status != SubQuestionStatus.PENDING:
            return False
        return all(dep_id in completed_ids for dep_id in self.dependencies)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "content": self.content,
            "parent_id": self.parent_id,
            "depth": self.depth,
            "priority": self.priority,
            "dependencies": self.dependencies,
            "status": self.status.value,
            "answer": self.answer,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubQuestion":
        """从字典创建"""
        return cls(
            id=data["id"],
            content=data["content"],
            parent_id=data.get("parent_id"),
            depth=data.get("depth", 0),
            priority=data.get("priority", 0),
            dependencies=data.get("dependencies", []),
            status=SubQuestionStatus(data.get("status", "pending")),
            answer=data.get("answer"),
            confidence=float(data.get("confidence", 0.0)),
            metadata=data.get("metadata", {}),
        )

    def __str__(self) -> str:
        deps = f", deps={self.dependencies}" if self.dependencies else ""
        return f"SubQuestion({self.id}: {self.content[:30]}...{deps})"


@dataclass
class QuestionTreeNode:
    """
    问题树节点

    用于表示子问题间的依赖关系和执行顺序
    """
    question: SubQuestion
    children: List["QuestionTreeNode"] = field(default_factory=list)

    def get_execution_order(self) -> List[List[SubQuestion]]:
        """
        获取执行顺序（层级遍历）

        返回按层级组织的子问题列表，同一层级可以并行执行
        """
        result: List[List[SubQuestion]] = []
        queue: List[Tuple["QuestionTreeNode", int]] = [(self, 0)]

        while queue:
            node, depth = queue.pop(0)

            # 扩展结果列表
            while len(result) <= depth:
                result.append([])

            result[depth].append(node.question)

            for child in node.children:
                queue.append((child, depth + 1))

        return result

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "question": self.question.to_dict(),
            "children": [child.to_dict() for child in self.children],
        }


@dataclass
class DecompositionResult:
    """
    分解结果

    Attributes:
        original_query: 原始查询
        sub_questions: 分解后的子问题列表
        execution_plan: 执行计划（按层级组织）
        strategy_used: 使用的分解策略
        confidence: 分解置信度
        reasoning: 分解推理过程
        total_tokens: 总 token 消耗
        decomposition_time: 分解耗时（秒）
    """
    original_query: str
    sub_questions: List[SubQuestion]
    execution_plan: List[List[SubQuestion]]
    strategy_used: str
    confidence: float
    reasoning: str = ""
    total_tokens: int = 0
    decomposition_time: float = 0.0

    @property
    def needs_decomposition(self) -> bool:
        """是否需要分解（子问题数 > 1）"""
        return len(self.sub_questions) > 1

    @property
    def max_depth(self) -> int:
        """最大深度"""
        return len(self.execution_plan) - 1 if self.execution_plan else 0

    @property
    def parallel_groups(self) -> int:
        """可并行执行的组数"""
        return len(self.execution_plan)

    def get_next_batch(self, completed_ids: Set[str]) -> List[SubQuestion]:
        """获取下一批可执行的子问题"""
        for level in self.execution_plan:
            batch = [
                q for q in level
                if q.can_execute(completed_ids) and q.id not in completed_ids
            ]
            if batch:
                return batch
        return []

    def update_status(self, question_id: str, status: SubQuestionStatus, answer: Optional[str] = None):
        """更新子问题状态"""
        for level in self.execution_plan:
            for q in level:
                if q.id == question_id:
                    q.status = status
                    if answer:
                        q.answer = answer
                    return

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "original_query": self.original_query,
            "sub_questions": [q.to_dict() for q in self.sub_questions],
            "execution_plan": [[q.to_dict() for q in level] for level in self.execution_plan],
            "strategy_used": self.strategy_used,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "total_tokens": self.total_tokens,
            "decomposition_time": self.decomposition_time,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DecompositionResult":
        """从字典创建"""
        sub_questions = [SubQuestion.from_dict(q) for q in data["sub_questions"]]
        execution_plan = [
            [SubQuestion.from_dict(q) for q in level]
            for level in data.get("execution_plan", [])
        ]
        return cls(
            original_query=data["original_query"],
            sub_questions=sub_questions,
            execution_plan=execution_plan,
            strategy_used=data.get("strategy_used", ""),
            confidence=float(data.get("confidence", 0.0)),
            reasoning=data.get("reasoning", ""),
            total_tokens=data.get("total_tokens", 0),
            decomposition_time=data.get("decomposition_time", 0.0),
        )


class DecompositionStrategy(BaseDecompositionStrategy):
    """
    分解策略基类

    定义分解策略的通用接口
    """

    @abstractmethod
    async def decompose(
        self,
        query: str,
        intent_result: Optional[IntentResult] = None,
        history: Optional[List[Dict[str, str]]] = None,
        **kwargs,
    ) -> DecompositionResult:
        """
        分解查询

        Args:
            query: 用户查询
            intent_result: 意图分类结果
            history: 对话历史
            **kwargs: 其他参数

        Returns:
            DecompositionResult
        """
        pass


class LLMDecompositionStrategy(DecompositionStrategy):
    """
    基于 LLM 的分解策略

    使用大语言模型理解查询并分解为子问题
    """

    def __init__(self, llm=None):
        self.llm = llm

    async def _get_llm(self):
        """获取 LLM 实例"""
        if self.llm is None:
            from ..llm import get_llm
            self.llm = get_llm()
        return self.llm

    async def decompose(
        self,
        query: str,
        intent_result: Optional[IntentResult] = None,
        history: Optional[List[Dict[str, str]]] = None,
        **kwargs,
    ) -> DecompositionResult:
        """使用 LLM 分解查询"""
        start_time = time.time()

        # 构建分解提示
        decomposition_prompt = self._build_decomposition_prompt(query, intent_result, history)

        # 调用 LLM
        llm = await self._get_llm()
        response = await llm.ainvoke(decomposition_prompt)

        # 解析响应
        sub_questions = self._parse_llm_response(response.content, query)

        # 构建执行计划
        execution_plan = self._build_execution_plan(sub_questions)

        return DecompositionResult(
            original_query=query,
            sub_questions=sub_questions,
            execution_plan=execution_plan,
            strategy_used="llm",
            confidence=0.85,  # LLM 分解的默认置信度
            reasoning="基于 LLM 理解的分解",
            total_tokens=getattr(response, "usage", {}).get("total_tokens", 0),
            decomposition_time=time.time() - start_time,
        )

    def _build_decomposition_prompt(
        self,
        query: str,
        intent_result: Optional[IntentResult],
        history: Optional[List[Dict[str, str]]],
    ) -> str:
        """构建分解提示"""
        context_parts = []

        if intent_result:
            context_parts.append(f"查询意图: {intent_result.intent.value}")
            context_parts.append(f"复杂度: {intent_result.complexity.value}")

        if history:
            history_str = "\n".join(
                [f"{h['role']}: {h['content']}" for h in history[-3:]]  # 最近3轮
            )
            context_parts.append(f"对话历史:\n{history_str}")

        context = "\n".join(context_parts) if context_parts else "无"

        return f"""请将以下复杂问题分解为多个子问题，以便更好地回答。

## 上下文信息
{context}

## 原始查询
{query}

## 任务要求
1. 分析查询是否真的需要分解（简单问题不需要分解）
2. 如果需要分解，将查询拆分为多个独立或有依赖关系的子问题
3. 为每个子问题分配优先级和依赖关系

## 输出格式（JSON）
```json
{{
  "needs_decomposition": true/false,
  "reason": "分解/不分解的原因",
  "sub_questions": [
    {{
      "id": "q1",
      "content": "子问题内容",
      "priority": 1,
      "dependencies": []
    }},
    {{
      "id": "q2",
      "content": "子问题内容",
      "priority": 2,
      "dependencies": ["q1"]
    }}
  ]
}}
```

## 注意事项
- 每个子问题应该是独立可回答的
- 尽量减少子问题间的依赖
- 子问题数量建议在 2-5 个之间
- 如果查询不需要分解，返回 needs_decomposition: false
"""

    def _parse_llm_response(self, response: str, original_query: str) -> List[SubQuestion]:
        """解析 LLM 响应"""
        try:
            import json
            import re

            # 尝试提取 JSON（支持 ```json...``` 格式）
            json_match = re.search(r'```(?:json)?\s*\{[\s\S]*?\}\s*```', response)
            if json_match:
                # 提取 ```json 和 ``` 之间的内容
                json_str = re.search(r'\{[\s\S]*\}', json_match.group())
                if json_str:
                    data = json.loads(json_str.group())
                else:
                    data = None
            else:
                # 尝试直接提取 JSON
                json_match = re.search(r'\{[\s\S]*\}', response)
                if json_match:
                    data = json.loads(json_match.group())
                else:
                    data = json.loads(response)

            if data is None:
                raise ValueError("无法解析 JSON")

            if not data.get("needs_decomposition", False):
                # 不需要分解，返回原始查询
                return [SubQuestion(
                    id="q1",
                    content=original_query,
                    depth=0,
                    priority=0,
                )]

            sub_questions = []
            for i, q_data in enumerate(data.get("sub_questions", [])):
                sub_questions.append(SubQuestion(
                    id=q_data.get("id", f"q{i+1}"),
                    content=q_data.get("content", ""),
                    depth=0,
                    priority=q_data.get("priority", i),
                    dependencies=q_data.get("dependencies", []),
                ))

            return sub_questions if sub_questions else [SubQuestion(
                id="q1",
                content=original_query,
                depth=0,
                priority=0,
            )]

        except Exception as e:
            logger.warning(f"解析 LLM 分解响应失败: {e}")
            # 返回原始查询作为单个子问题
            return [SubQuestion(
                id="q1",
                content=original_query,
                depth=0,
                priority=0,
            )]

    def _build_execution_plan(self, sub_questions: List[SubQuestion]) -> List[List[SubQuestion]]:
        """构建执行计划"""
        if not sub_questions:
            return []

        # 按深度和优先级排序
        sorted_questions = sorted(sub_questions, key=lambda q: (q.depth, q.priority))

        # 构建层级执行计划
        levels: List[List[SubQuestion]] = []
        remaining = set(q.id for q in sorted_questions)
        completed = set()

        while remaining:
            level = []
            for q in sorted_questions:
                if q.id in remaining:
                    # 检查依赖是否已满足
                    deps = set(q.dependencies)
                    if deps.issubset(completed):
                        level.append(q)
                        remaining.discard(q.id)

            if not level:
                # 避免无限循环：添加剩余的所有问题
                for q_id in list(remaining):
                    q = next(q for q in sorted_questions if q.id == q_id)
                    level.append(q)
                    remaining.discard(q_id)

            # 标记当前层级为已完成
            for q in level:
                completed.add(q.id)

            levels.append(level)

        return levels


class RuleDecompositionStrategy(DecompositionStrategy):
    """
    基于规则的分解策略

    使用预定义规则分解简单查询
    """

    def __init__(self):
        # 分解触发词
        self.decomposition_triggers = {
            "和": 2,
            "与": 2,
            "比较": 2,
            "对比": 2,
            "区别": 2,
            "以及": 2,
            "同时": 2,
        }

    async def decompose(
        self,
        query: str,
        intent_result: Optional[IntentResult] = None,
        history: Optional[List[Dict[str, str]]] = None,
        **kwargs,
    ) -> DecompositionResult:
        """使用规则分解查询"""
        start_time = time.time()

        sub_questions = self._rule_based_decompose(query)
        execution_plan = self._build_execution_plan(sub_questions)

        return DecompositionResult(
            original_query=query,
            sub_questions=sub_questions,
            execution_plan=execution_plan,
            strategy_used="rule",
            confidence=0.6,  # 规则分解的置信度较低
            reasoning="基于规则的分解",
            total_tokens=0,
            decomposition_time=time.time() - start_time,
        )

    def _rule_based_decompose(self, query: str) -> List[SubQuestion]:
        """基于规则分解"""
        sub_questions = []

        # 检查是否包含分解触发词
        for trigger, _ in self.decomposition_triggers.items():
            if trigger in query:
                # 尝试按触发词分割
                parts = query.split(trigger)
                if len(parts) > 1:
                    for i, part in enumerate(parts):
                        part = part.strip()
                        if part:
                            sub_questions.append(SubQuestion(
                                id=f"q{i+1}",
                                content=part,
                                depth=0,
                                priority=i,
                            ))
                    break

        # 如果没有分解，返回原始查询
        if not sub_questions:
            sub_questions = [SubQuestion(
                id="q1",
                content=query,
                depth=0,
                priority=0,
            )]

        return sub_questions

    def _build_execution_plan(self, sub_questions: List[SubQuestion]) -> List[List[SubQuestion]]:
        """构建执行计划"""
        return [sub_questions]  # 规则分解通常没有依赖，可以并行执行


class HybridDecompositionStrategy(DecompositionStrategy):
    """
    混合分解策略

    先规则，复杂查询再用 LLM
    """

    def __init__(self, llm=None):
        self.rule_strategy = RuleDecompositionStrategy()
        self.llm_strategy = LLMDecompositionStrategy(llm)
        self.complexity_threshold = ComplexityLevel.MEDIUM

    async def decompose(
        self,
        query: str,
        intent_result: Optional[IntentResult] = None,
        history: Optional[List[Dict[str, str]]] = None,
        **kwargs,
    ) -> DecompositionResult:
        """使用混合策略分解"""
        # 简单查询直接返回
        if intent_result and intent_result.complexity == ComplexityLevel.SIMPLE:
            return DecompositionResult(
                original_query=query,
                sub_questions=[SubQuestion(
                    id="q1",
                    content=query,
                    depth=0,
                    priority=0,
                )],
                execution_plan=[[SubQuestion(
                    id="q1",
                    content=query,
                    depth=0,
                    priority=0,
                )]],
                strategy_used="hybrid",
                confidence=0.9,
                reasoning="简单查询，无需分解",
                total_tokens=0,
                decomposition_time=0.0,
            )

        # 尝试规则分解
        rule_result = await self.rule_strategy.decompose(query, intent_result, history)

        # 如果规则分解有效（子问题 > 1），返回
        if rule_result.needs_decomposition and rule_result.confidence >= 0.7:
            rule_result.strategy_used = "hybrid_rule"
            return rule_result

        # 否则使用 LLM 分解
        llm_result = await self.llm_strategy.decompose(query, intent_result, history)
        llm_result.strategy_used = "hybrid_llm"

        return llm_result


class QueryDecomposer:
    """
    问题分解器主类

    负责将复杂问题分解为子问题，并管理分解过程
    """

    def __init__(
        self,
        strategy: Optional[DecompositionStrategy] = None,
        cache_enabled: bool = True,
        cache_ttl: int = 3600,
    ):
        """
        初始化问题分解器

        Args:
            strategy: 分解策略（默认混合策略）
            cache_enabled: 是否启用缓存
            cache_ttl: 缓存过期时间（秒）
        """
        self.strategy = strategy or HybridDecompositionStrategy()
        self.cache_enabled = cache_enabled
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, Tuple[DecompositionResult, float]] = {}

    def _get_cache_key(self, query: str, history: Optional[List[Dict[str, str]]]) -> str:
        """生成缓存键"""
        content = query
        if history:
            # 只使用最近3轮对话
            recent = history[-3:] if len(history) > 3 else history
            content += str(recent)

        return hashlib.md5(content.encode()).hexdigest()

    async def decompose(
        self,
        query: str,
        intent_result: Optional[IntentResult] = None,
        history: Optional[List[Dict[str, str]]] = None,
        **kwargs,
    ) -> DecompositionResult:
        """
        分解查询

        Args:
            query: 用户查询
            intent_result: 意图分类结果
            history: 对话历史
            **kwargs: 其他参数

        Returns:
            DecompositionResult
        """
        # 检查缓存
        if self.cache_enabled:
            cache_key = self._get_cache_key(query, history)
            if cache_key in self._cache:
                result, timestamp = self._cache[cache_key]
                if time.time() - timestamp < self.cache_ttl:
                    logger.debug(f"使用缓存: {query[:30]}...")
                    return result

        # 执行分解
        result = await self.strategy.decompose(query, intent_result, history, **kwargs)

        # 缓存结果
        if self.cache_enabled:
            cache_key = self._get_cache_key(query, history)
            self._cache[cache_key] = (result, time.time())

        logger.info(
            f"分解完成: {result.original_query[:30]}... -> "
            f"{len(result.sub_questions)} 个子问题, "
            f"策略: {result.strategy_used}, "
            f"耗时: {result.decomposition_time:.3f}s"
        )

        return result

    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()


class QueryDecomposerFactory:
    """
    QueryDecomposer 工厂类

    使用工厂模式统一创建逻辑
    """

    _strategies = {
        DecompositionStrategyType.LLM: LLMDecompositionStrategy,
        DecompositionStrategyType.RULE: RuleDecompositionStrategy,
        DecompositionStrategyType.HYBRID: HybridDecompositionStrategy,
    }

    @classmethod
    def create(
        cls,
        strategy_type: DecompositionStrategyType = DecompositionStrategyType.HYBRID,
        llm=None,
        **kwargs,
    ) -> QueryDecomposer:
        """
        创建 QueryDecomposer 实例

        Args:
            strategy_type: 策略类型
            llm: LLM 实例（可选）
            **kwargs: 其他参数

        Returns:
            QueryDecomposer 实例
        """
        strategy_class = cls._strategies.get(strategy_type)

        if strategy_class is None:
            raise ValueError(f"未知的策略类型: {strategy_type}")

        # LLM 和 Hybrid 策略需要 LLM 实例
        if strategy_type in [DecompositionStrategyType.LLM, DecompositionStrategyType.HYBRID]:
            strategy = strategy_class(llm=llm)
        else:
            strategy = strategy_class()

        return QueryDecomposer(strategy=strategy, **kwargs)

    @classmethod
    def register_strategy(cls, strategy_type: str, strategy_class: type):
        """注册新的策略"""
        cls._strategies[strategy_type] = strategy_class
