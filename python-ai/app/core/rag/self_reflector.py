"""
自我反思器模块

提供多种反思策略，用于评估答案质量，自动重试或补充检索：
- LLMReflectionStrategy: LLM 反思策略（使用 LLM 评估和优化答案）
- RuleBasedReflectionStrategy: 规则反思策略（基于规则评估答案质量）
- HybridReflectionStrategy: 混合反思策略（结合 LLM 和规则）

设计模式：
- 枚举模式：ReflectionStrategyType - 类型安全的策略选择
- 策略模式：多种反思策略，运行时可切换
- 工厂模式：SelfReflectorFactory - 统一创建反思器实例
- 缓存模式：减少重复反思计算
- 单例模式：全局唯一反思器实例
- 责任链模式：质量评估标准链

作者：Claude
日期：2026-07-22
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
import time
import hashlib
import asyncio
import re

from .utils import (
    DEFAULT_QUALITY_THRESHOLD,
    DEFAULT_MAX_RETRIES,
    CONFIDENCE_BASE_SCORE,
    calculate_text_similarity,
    truncate_text,
)
from .cache import CacheManager, reflection_cache
from .base import BaseReflectionStrategy


# ==================== 枚举定义 ====================

class ReflectionStrategyType(str, Enum):
    """反思策略类型枚举"""
    LLM = "llm"
    RULE_BASED = "rule_based"
    HYBRID = "hybrid"


class ReflectionStatus(str, Enum):
    """反思状态枚举"""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class QualityDimension(str, Enum):
    """质量评估维度枚举"""
    COMPLETENESS = "completeness"
    ACCURACY = "accuracy"
    RELEVANCE = "relevance"
    CLARITY = "clarity"


# ==================== 数据模型 ====================

@dataclass
class QualityCriteria:
    """
    质量评估标准

    Attributes:
        completeness: 完整性权重 (0-1)
        accuracy: 准确性权重 (0-1)
        relevance: 相关性权重 (0-1)
        clarity: 清晰度权重 (0-1)
    """
    completeness: float = 0.3
    accuracy: float = 0.3
    relevance: float = 0.2
    clarity: float = 0.2

    def to_dict(self) -> Dict[str, float]:
        """转换为字典"""
        return {
            "completeness": self.completeness,
            "accuracy": self.accuracy,
            "relevance": self.relevance,
            "clarity": self.clarity,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> 'QualityCriteria':
        """从字典创建"""
        return cls(
            completeness=data.get("completeness", 0.3),
            accuracy=data.get("accuracy", 0.3),
            relevance=data.get("relevance", 0.2),
            clarity=data.get("clarity", 0.2),
        )


@dataclass
class ReflectionResult:
    """
    反思结果

    Attributes:
        original_answer: 原始答案
        reflected_answer: 反思后答案
        quality_score: 质量评分 (0-1)
        dimension_scores: 各维度评分
        issues: 发现的问题
        suggestions: 改进建议
        retry_count: 重试次数
        strategy_used: 使用的策略
        status: 状态
        error_message: 错误信息（如果失败）
    """
    original_answer: str
    reflected_answer: str
    quality_score: float
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    retry_count: int = 0
    strategy_used: str = ""
    status: ReflectionStatus = ReflectionStatus.COMPLETED
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "original_answer": truncate_text(self.original_answer, 100),
            "reflected_answer": self.reflected_answer,
            "quality_score": self.quality_score,
            "dimension_scores": self.dimension_scores,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "retry_count": self.retry_count,
            "strategy_used": self.strategy_used,
            "status": self.status.value,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ReflectionResult':
        """从字典创建"""
        return cls(
            original_answer=data.get("original_answer", ""),
            reflected_answer=data.get("reflected_answer", ""),
            quality_score=data.get("quality_score", 0.0),
            dimension_scores=data.get("dimension_scores", {}),
            issues=data.get("issues", []),
            suggestions=data.get("suggestions", []),
            retry_count=data.get("retry_count", 0),
            strategy_used=data.get("strategy_used", ""),
            status=ReflectionStatus(data.get("status", "completed")),
            error_message=data.get("error_message"),
        )


@dataclass
class ReflectionConfig:
    """
    反思配置

    Attributes:
        strategy: 反思策略类型
        quality_threshold: 质量阈值 (0-1)
        max_retries: 最大重试次数
        enable_supplement: 是否启用补充检索
        language: 语言（zh/en）
        criteria: 质量评估标准
    """
    strategy: ReflectionStrategyType = ReflectionStrategyType.LLM
    quality_threshold: float = DEFAULT_QUALITY_THRESHOLD
    max_retries: int = DEFAULT_MAX_RETRIES
    enable_supplement: bool = True
    language: str = "zh"
    criteria: QualityCriteria = field(default_factory=QualityCriteria)


# ==================== LLM 反思策略 ====================

class LLMReflectionStrategy(BaseReflectionStrategy):
    """
    LLM 反思策略

    使用 LLM 评估和优化答案。

    优点：
    - 评估更准确
    - 可以优化答案

    缺点：
    - 需要 LLM，成本较高
    - 速度较慢
    """

    def __init__(self, llm=None, **kwargs):
        """初始化"""
        self.llm = llm
        self.name = "llm"

    def get_strategy_name(self) -> str:
        """获取策略名称"""
        return self.name

    def get_strategy_type(self) -> ReflectionStrategyType:
        """获取策略类型"""
        return ReflectionStrategyType.LLM

    async def reflect(
        self,
        query: str,
        answer: str,
        context: str,
        config: Optional[ReflectionConfig] = None,
        **kwargs
    ) -> ReflectionResult:
        """
        执行反思

        Args:
            query: 原始查询
            answer: 原始答案
            context: 检索上下文
            config: 反思配置

        Returns:
            反思结果
        """
        if config is None:
            config = ReflectionConfig()

        # 检查是否有 LLM
        if self.llm is None:
            # 降级到规则反思
            fallback = RuleBasedReflectionStrategy()
            return await fallback.reflect(query, answer, context, config, **kwargs)

        try:
            # 1. 构建评估提示
            evaluation_prompt = self._build_evaluation_prompt(query, answer, context, config)

            # 2. 调用 LLM 评估
            if hasattr(self.llm, 'ainvoke'):
                response = await self.llm.ainvoke(evaluation_prompt)
                evaluation_text = response.content if hasattr(response, 'content') else str(response)
            else:
                # 降级到规则反思
                fallback = RuleBasedReflectionStrategy()
                return await fallback.reflect(query, answer, context, config, **kwargs)

            # 3. 解析评估结果
            quality_score, dimension_scores, issues, suggestions = self._parse_evaluation(
                evaluation_text, config.criteria
            )

            # 4. 如果质量低于阈值，生成优化后的答案
            reflected_answer = answer
            if quality_score < config.quality_threshold:
                optimization_prompt = self._build_optimization_prompt(
                    query, answer, context, issues, suggestions, config
                )

                if hasattr(self.llm, 'ainvoke'):
                    response = await self.llm.ainvoke(optimization_prompt)
                    reflected_answer = response.content if hasattr(response, 'content') else str(response)

            return ReflectionResult(
                original_answer=answer,
                reflected_answer=reflected_answer,
                quality_score=quality_score,
                dimension_scores=dimension_scores,
                issues=issues,
                suggestions=suggestions,
                strategy_used=self.name,
                status=ReflectionStatus.COMPLETED,
            )

        except Exception as e:
            # 降级到规则反思
            fallback = RuleBasedReflectionStrategy()
            return await fallback.reflect(query, answer, context, config, **kwargs)

    def _build_evaluation_prompt(
        self,
        query: str,
        answer: str,
        context: str,
        config: ReflectionConfig
    ) -> str:
        """构建评估提示"""
        if config.language == "zh":
            return f"""请评估以下答案的质量。

问题：
{query}

参考资料：
{context}

答案：
{answer}

请从以下维度评估：
1. 完整性 (0-1)：答案是否完整回答了问题
2. 准确性 (0-1)：答案是否准确
3. 相关性 (0-1)：答案是否与问题相关
4. 清晰度 (0-1)：答案是否清晰易懂

请返回 JSON 格式：
{{
    "quality_score": 0.8,
    "dimension_scores": {{
        "completeness": 0.9,
        "accuracy": 0.8,
        "relevance": 0.9,
        "clarity": 0.7
    }},
    "issues": ["问题1", "问题2"],
    "suggestions": ["建议1", "建议2"]
}}"""
        else:
            return f"""Please evaluate the quality of the following answer.

Question:
{query}

Reference context:
{context}

Answer:
{answer}

Please evaluate from the following dimensions:
1. Completeness (0-1): Does the answer fully address the question?
2. Accuracy (0-1): Is the answer accurate?
3. Relevance (0-1): Is the answer relevant to the question?
4. Clarity (0-1): Is the answer clear and easy to understand?

Please return in JSON format:
{{
    "quality_score": 0.8,
    "dimension_scores": {{
        "completeness": 0.9,
        "accuracy": 0.8,
        "relevance": 0.9,
        "clarity": 0.7
    }},
    "issues": ["issue1", "issue2"],
    "suggestions": ["suggestion1", "suggestion2"]
}}"""

    def _build_optimization_prompt(
        self,
        query: str,
        answer: str,
        context: str,
        issues: List[str],
        suggestions: List[str],
        config: ReflectionConfig
    ) -> str:
        """构建优化提示"""
        issues_text = "\n".join([f"- {issue}" for issue in issues])
        suggestions_text = "\n".join([f"- {suggestion}" for suggestion in suggestions])

        if config.language == "zh":
            return f"""请优化以下答案，解决发现的问题。

问题：
{query}

参考资料：
{context}

原始答案：
{answer}

发现的问题：
{issues_text}

改进建议：
{suggestions_text}

请提供优化后的答案，确保：
1. 解决所有发现的问题
2. 采纳所有改进建议
3. 保持答案准确性和完整性

优化后答案："""
        else:
            return f"""Please optimize the following answer, resolving the identified issues.

Question:
{query}

Reference context:
{context}

Original answer:
{answer}

Issues found:
{issues_text}

Suggestions:
{suggestions_text}

Please provide an optimized answer that:
1. Resolves all identified issues
2. Incorporates all suggestions
3. Maintains accuracy and completeness

Optimized answer:"""

    def _parse_evaluation(
        self,
        evaluation_text: str,
        criteria: QualityCriteria
    ) -> Tuple[float, Dict[str, float], List[str], List[str]]:
        """解析评估结果"""
        try:
            # 尝试解析 JSON
            import json
            # 提取 JSON 部分
            json_match = re.search(r'\{.*\}', evaluation_text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                quality_score = data.get("quality_score", 0.5)
                dimension_scores = data.get("dimension_scores", {})
                issues = data.get("issues", [])
                suggestions = data.get("suggestions", [])
                return quality_score, dimension_scores, issues, suggestions
        except:
            pass

        # 如果解析失败，使用简单评估
        return self._simple_evaluate(evaluation_text, criteria)

    def _simple_evaluate(
        self,
        text: str,
        criteria: QualityCriteria
    ) -> Tuple[float, Dict[str, float], List[str], List[str]]:
        """简单评估"""
        # 基于文本长度和关键词评估
        length_score = min(len(text) / 200, 1.0)
        keyword_score = 0.5

        # 检查关键词
        keywords = ["答案", "回答", "问题", "准确", "完整"]
        for keyword in keywords:
            if keyword in text:
                keyword_score += 0.1

        keyword_score = min(keyword_score, 1.0)

        # 综合得分
        quality_score = (length_score + keyword_score) / 2

        dimension_scores = {
            "completeness": length_score,
            "accuracy": keyword_score,
            "relevance": 0.7,
            "clarity": 0.8,
        }

        issues = []
        suggestions = []

        if length_score < 0.5:
            issues.append("答案过短")
            suggestions.append("请提供更详细的回答")

        return quality_score, dimension_scores, issues, suggestions


# ==================== 规则反思策略 ====================

class RuleBasedReflectionStrategy(BaseReflectionStrategy):
    """
    规则反思策略

    基于规则评估答案质量。

    优点：
    - 快速，无需 LLM
    - 可解释性强

    缺点：
    - 评估可能不够准确
    """

    def __init__(self, **kwargs):
        """初始化"""
        self.name = "rule_based"

    def get_strategy_name(self) -> str:
        """获取策略名称"""
        return self.name

    def get_strategy_type(self) -> ReflectionStrategyType:
        """获取策略类型"""
        return ReflectionStrategyType.RULE_BASED

    async def reflect(
        self,
        query: str,
        answer: str,
        context: str,
        config: Optional[ReflectionConfig] = None,
        **kwargs
    ) -> ReflectionResult:
        """执行反思"""
        if config is None:
            config = ReflectionConfig()

        # 评估各维度
        dimension_scores = {}
        issues = []
        suggestions = []

        # 1. 完整性评估
        completeness_score, completeness_issues, completeness_suggestions = self._evaluate_completeness(
            query, answer, config
        )
        dimension_scores["completeness"] = completeness_score
        issues.extend(completeness_issues)
        suggestions.extend(completeness_suggestions)

        # 2. 准确性评估
        accuracy_score, accuracy_issues, accuracy_suggestions = self._evaluate_accuracy(
            answer, context, config
        )
        dimension_scores["accuracy"] = accuracy_score
        issues.extend(accuracy_issues)
        suggestions.extend(accuracy_suggestions)

        # 3. 相关性评估
        relevance_score, relevance_issues, relevance_suggestions = self._evaluate_relevance(
            query, answer, config
        )
        dimension_scores["relevance"] = relevance_score
        issues.extend(relevance_issues)
        suggestions.extend(relevance_suggestions)

        # 4. 清晰度评估
        clarity_score, clarity_issues, clarity_suggestions = self._evaluate_clarity(
            answer, config
        )
        dimension_scores["clarity"] = clarity_score
        issues.extend(clarity_issues)
        suggestions.extend(clarity_suggestions)

        # 计算综合得分
        quality_score = (
            completeness_score * config.criteria.completeness +
            accuracy_score * config.criteria.accuracy +
            relevance_score * config.criteria.relevance +
            clarity_score * config.criteria.clarity
        )

        return ReflectionResult(
            original_answer=answer,
            reflected_answer=answer,  # 规则策略不修改答案
            quality_score=quality_score,
            dimension_scores=dimension_scores,
            issues=issues,
            suggestions=suggestions,
            strategy_used=self.name,
            status=ReflectionStatus.COMPLETED,
        )

    def _evaluate_completeness(
        self,
        query: str,
        answer: str,
        config: ReflectionConfig
    ) -> Tuple[float, List[str], List[str]]:
        """评估完整性"""
        score = 1.0
        issues = []
        suggestions = []

        # 检查答案长度
        if len(answer) < 10:
            score -= 0.3
            issues.append("答案过短")
            suggestions.append("请提供更详细的回答")

        # 检查是否包含关键词
        query_keywords = set(re.findall(r'[\w一-鿿]+', query))
        answer_keywords = set(re.findall(r'[\w一-鿿]+', answer))
        keyword_coverage = len(query_keywords.intersection(answer_keywords)) / len(query_keywords) if query_keywords else 0

        if keyword_coverage < 0.3:
            score -= 0.2
            issues.append("答案缺少关键信息")
            suggestions.append("请包含更多问题中的关键词")

        return max(0, score), issues, suggestions

    def _evaluate_accuracy(
        self,
        answer: str,
        context: str,
        config: ReflectionConfig
    ) -> Tuple[float, List[str], List[str]]:
        """评估准确性"""
        score = 1.0
        issues = []
        suggestions = []

        # 检查是否包含否定词
        negation_words = ["不", "没有", "无法", "不可能", "错误"]
        negation_count = sum(1 for word in negation_words if word in answer)
        if negation_count > 2:
            score -= 0.2
            issues.append("答案包含较多否定表述")
            suggestions.append("请提供更积极的回答")

        # 检查是否与上下文一致
        if context:
            overlap = calculate_text_similarity(context, answer)

            if overlap < 0.2:
                score -= 0.2
                issues.append("答案与参考资料关联度低")
                suggestions.append("请基于参考资料回答")

        return max(0, score), issues, suggestions

    def _evaluate_relevance(
        self,
        query: str,
        answer: str,
        config: ReflectionConfig
    ) -> Tuple[float, List[str], List[str]]:
        """评估相关性"""
        score = 1.0
        issues = []
        suggestions = []

        # 检查答案是否回答了问题
        overlap = calculate_text_similarity(query, answer)

        if overlap < 0.3:
            score -= 0.3
            issues.append("答案与问题关联度低")
            suggestions.append("请直接回答问题")

        return max(0, score), issues, suggestions

    def _evaluate_clarity(
        self,
        answer: str,
        config: ReflectionConfig
    ) -> Tuple[float, List[str], List[str]]:
        """评估清晰度"""
        score = 1.0
        issues = []
        suggestions = []

        # 检查句子长度
        sentences = re.split(r'[。！？.!?]', answer)
        long_sentences = [s for s in sentences if len(s) > 50]
        if len(long_sentences) > 2:
            score -= 0.2
            issues.append("存在较长的句子")
            suggestions.append("请将长句拆分为短句")

        # 检查是否有段落
        if len(answer) > 100 and '\n' not in answer:
            score -= 0.1
            issues.append("答案缺少段落结构")
            suggestions.append("请添加适当的段落分隔")

        return max(0, score), issues, suggestions


# ==================== 混合反思策略 ====================

class HybridReflectionStrategy(BaseReflectionStrategy):
    """
    混合反思策略

    结合 LLM 和规则：
    1. 先用规则评估
    2. 如果规则评估不确定，使用 LLM
    3. 综合两者结果

    优点：
    - 平衡速度和准确性
    """

    def __init__(self, llm=None, **kwargs):
        """初始化"""
        self.llm = llm
        self.rule_based = RuleBasedReflectionStrategy()
        self.llm_strategy = LLMReflectionStrategy(llm=llm)
        self.name = "hybrid"

    def get_strategy_name(self) -> str:
        """获取策略名称"""
        return self.name

    def get_strategy_type(self) -> ReflectionStrategyType:
        """获取策略类型"""
        return ReflectionStrategyType.HYBRID

    async def reflect(
        self,
        query: str,
        answer: str,
        context: str,
        config: Optional[ReflectionConfig] = None,
        **kwargs
    ) -> ReflectionResult:
        """执行反思"""
        if config is None:
            config = ReflectionConfig()

        # 1. 先用规则评估
        rule_result = await self.rule_based.reflect(query, answer, context, config)

        # 2. 如果规则评估结果明确，直接返回
        if rule_result.quality_score >= config.quality_threshold or self.llm is None:
            return rule_result

        # 3. 如果规则评估不确定，使用 LLM
        llm_result = await self.llm_strategy.reflect(query, answer, context, config)

        # 4. 综合两者结果
        combined_score = (rule_result.quality_score + llm_result.quality_score) / 2
        combined_issues = list(set(rule_result.issues + llm_result.issues))
        combined_suggestions = list(set(rule_result.suggestions + llm_result.suggestions))

        return ReflectionResult(
            original_answer=answer,
            reflected_answer=llm_result.reflected_answer,
            quality_score=combined_score,
            dimension_scores=llm_result.dimension_scores,
            issues=combined_issues,
            suggestions=combined_suggestions,
            strategy_used=self.name,
            status=ReflectionStatus.COMPLETED,
        )


# ==================== 主类 ====================

class SelfReflector:
    """
    自我反思器主类

    用于评估答案质量，自动重试或补充检索。

    设计模式：
    - 缓存模式：避免重复反思
    - 策略模式：支持多种反思策略
    - 重试模式：自动重试低质量答案

    使用示例：
        reflector = SelfReflector()
        result = await reflector.reflect(query, answer, context)
        print(f"质量评分: {result.quality_score:.2f}")
    """

    def __init__(
        self,
        strategy=None,
        cache_enabled: bool = True,
        cache_ttl: int = 3600,
        llm=None,
        cache: Optional[CacheManager] = None,
        **kwargs
    ):
        """
        初始化反思器

        Args:
            strategy: 反思策略（可选，默认为 LLMReflectionStrategy）
            cache_enabled: 是否启用缓存
            cache_ttl: 缓存过期时间（秒）
            llm: LLM 实例（可选）
            cache: 缓存管理器实例（可选）
        """
        if strategy is None:
            self.strategy = LLMReflectionStrategy(llm=llm)
        elif isinstance(strategy, str):
            # 如果传入的是字符串，转换为枚举
            strategy_type = ReflectionStrategyType(strategy)
            self.strategy = self._create_strategy(strategy_type, llm=llm)
        else:
            self.strategy = strategy

        # 使用提供的缓存管理器或创建新的
        if cache is not None:
            self._cache_manager = cache
        else:
            self._cache_manager = CacheManager(
                enabled=cache_enabled,
                ttl=cache_ttl,
                max_size=500,
                name="self_reflector"
            )

        # 保持向后兼容
        self.cache_enabled = self._cache_manager.enabled
        self.cache_ttl = self._cache_manager.ttl

    def _create_strategy(
        self,
        strategy_type: ReflectionStrategyType,
        llm=None
    ):
        """根据类型创建策略实例"""
        strategy_map = {
            ReflectionStrategyType.LLM: LLMReflectionStrategy,
            ReflectionStrategyType.RULE_BASED: RuleBasedReflectionStrategy,
            ReflectionStrategyType.HYBRID: HybridReflectionStrategy,
        }

        if strategy_type not in strategy_map:
            raise ValueError(f"Unknown strategy type: {strategy_type}")

        strategy_class = strategy_map[strategy_type]
        return strategy_class(llm=llm)

    async def reflect(
        self,
        query: str,
        answer: str,
        context: str,
        config: Optional[ReflectionConfig] = None,
        **kwargs
    ) -> ReflectionResult:
        """
        执行反思

        Args:
            query: 原始查询
            answer: 原始答案
            context: 检索上下文
            config: 反思配置

        Returns:
            反思结果
        """
        if config is None:
            config = ReflectionConfig()

        # 1. 检查缓存
        cache_key = self._get_cache_key(query, answer, config)
        cached_result = self._cache_manager.get(cache_key)
        if cached_result is not None:
            return cached_result

        # 2. 执行反思
        try:
            result = await self.strategy.reflect(query, answer, context, config, **kwargs)
        except Exception as e:
            # 如果反思失败，返回默认结果
            result = ReflectionResult(
                original_answer=answer,
                reflected_answer=answer,
                quality_score=0.5,
                strategy_used="failed",
                status=ReflectionStatus.FAILED,
                error_message=str(e),
            )

        # 3. 缓存结果
        self._cache_manager.set(cache_key, result)

        return result

    async def reflect_with_retry(
        self,
        query: str,
        answer: str,
        context: str,
        config: Optional[ReflectionConfig] = None,
        retriever=None,
        llm=None,
        **kwargs
    ) -> ReflectionResult:
        """
        带重试的反思

        Args:
            query: 原始查询
            answer: 原始答案
            context: 检索上下文
            config: 反思配置
            retriever: 检索器（用于补充检索）
            llm: LLM 实例（用于重新生成答案）

        Returns:
            反思结果
        """
        if config is None:
            config = ReflectionConfig()

        current_answer = answer
        current_context = context
        retry_count = 0

        while retry_count <= config.max_retries:
            result = await self.reflect(
                query, current_answer, current_context, config, **kwargs
            )

            # 检查质量
            if result.quality_score >= config.quality_threshold:
                result.retry_count = retry_count
                return result

            # 如果需要重试且有检索器
            if retry_count < config.max_retries and retriever and config.enable_supplement:
                # 补充检索
                supplement_context = await self._supplement_retrieval(
                    query, result.issues, retriever
                )
                current_context = current_context + "\n\n" + supplement_context

                # 使用 LLM 重新生成答案
                if llm:
                    current_answer = await self._regenerate_answer(
                        query, current_context, llm
                    )

            retry_count += 1

        # 返回最后一次结果
        result.retry_count = retry_count
        return result

    async def _supplement_retrieval(
        self,
        query: str,
        issues: List[str],
        retriever
    ) -> str:
        """补充检索"""
        # 根据问题生成补充查询
        supplement_queries = self._generate_supplement_queries(query, issues)

        # 检索补充内容
        supplement_docs = []
        for supplement_query in supplement_queries:
            try:
                docs = await retriever.retrieve(supplement_query)
                supplement_docs.extend(docs)
            except:
                pass

        return "\n\n".join([doc.content for doc in supplement_docs[:3]])  # 最多3个文档

    def _generate_supplement_queries(
        self,
        query: str,
        issues: List[str]
    ) -> List[str]:
        """生成补充查询"""
        queries = [query]  # 基础查询

        # 根据问题生成补充查询
        for issue in issues:
            if "关键词" in issue:
                # 提取查询中的关键词
                keywords = re.findall(r'[\w一-鿿]+', query)
                if keywords:
                    queries.append(" ".join(keywords[:3]))
            elif "参考资料" in issue:
                # 使用查询本身
                queries.append(query)

        return queries[:3]  # 最多3个查询

    async def _regenerate_answer(
        self,
        query: str,
        context: str,
        llm
    ) -> str:
        """重新生成答案"""
        prompt = f"""基于以下参考资料回答问题。

参考资料：
{context}

问题：{query}

请提供准确、简洁的回答。"""

        messages = [{"role": "user", "content": prompt}]
        response = await llm.chat(messages=messages, temperature=0.7)
        return response.content

    def _get_cache_key(
        self,
        query: str,
        answer: str,
        config: Optional[ReflectionConfig]
    ) -> str:
        """生成缓存键"""
        content = f"{query}:{answer}:{config.strategy.value if config else 'default'}"
        return hashlib.md5(content.encode()).hexdigest()

    def clear_cache(self):
        """清空缓存"""
        self._cache_manager.clear()

    def get_cache_size(self) -> int:
        """获取缓存大小"""
        return self._cache_manager.get_stats().size

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        return self._cache_manager.get_stats().to_dict()


# ==================== 工厂类 ====================

class SelfReflectorFactory:
    """
    自我反思器工厂

    用于创建反思器实例。

    设计模式：工厂模式 - 统一创建逻辑，便于管理

    使用示例：
        refpector = SelfReflectorFactory.create(ReflectionStrategyType.LLM)
        result = await refpector.reflect(query, answer, context)
    """

    @staticmethod
    def create(
        strategy_type: ReflectionStrategyType,
        **kwargs
    ) -> SelfReflector:
        """
        创建反思器实例

        Args:
            strategy_type: 反思策略类型
            **kwargs: 传递给策略的参数

        Returns:
            反思器实例
        """
        return SelfReflector(
            strategy=strategy_type.value,
            **kwargs
        )

    @staticmethod
    def create_with_llm(
        strategy_type: ReflectionStrategyType,
        llm,
        **kwargs
    ) -> SelfReflector:
        """
        创建带 LLM 的反思器实例

        Args:
            strategy_type: 反思策略类型
            llm: LLM 实例
            **kwargs: 传递给策略的参数

        Returns:
            反思器实例
        """
        return SelfReflector(
            strategy=strategy_type.value,
            llm=llm,
            **kwargs
        )


# ==================== 全局实例 ====================

_reflector: Optional[SelfReflector] = None


def get_reflector(
    strategy_type: ReflectionStrategyType = ReflectionStrategyType.LLM,
    **kwargs
) -> SelfReflector:
    """
    获取全局反思器实例

    Args:
        strategy_type: 反思策略类型

    Returns:
        反思器实例
    """
    global _reflector
    if _reflector is None:
        _reflector = SelfReflectorFactory.create(strategy_type, **kwargs)
    return _reflector


def reset_reflector():
    """重置全局反思器实例"""
    global _reflector
    _reflector = None
