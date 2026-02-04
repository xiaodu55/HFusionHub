"""
答案质量评估器模块

提供多种评估策略，用于评估 AI 回复的质量：
- RuleBasedEvaluationStrategy: 基于规则的评估策略
- LLMEvaluationStrategy: 基于 LLM 的评估策略
- HybridEvaluationStrategy: 混合评估策略

设计模式：
- 枚举模式：EvaluationStrategyType - 类型安全的策略选择
- 策略模式：多种评估策略，运行时可切换
- 工厂模式：AnswerQualityEvaluatorFactory - 统一创建评估器实例
- 缓存模式：减少重复评估计算
- 单例模式：全局唯一评估器实例

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
import json

from .utils import (
    estimate_tokens,
    calculate_text_similarity,
    truncate_text,
    DEFAULT_QUALITY_THRESHOLD,
    CONFIDENCE_BASE_SCORE,
    CONFIDENCE_MAX_SCORE,
    CONFIDENCE_WEIGHT_FACTOR,
)


# ==================== 枚举定义 ====================

class EvaluationStrategyType(str, Enum):
    """评估策略类型枚举"""
    RULE_BASED = "rule_based"
    LLM_BASED = "llm_based"
    RAGAS = "ragas"
    HYBRID = "hybrid"


class EvaluationDimension(str, Enum):
    """评估维度枚举"""
    FAITHFULNESS = "faithfulness"
    ANSWER_RELEVANCY = "answer_relevancy"
    ANSWER_CORRECTNESS = "answer_correctness"
    CONTEXT_PRECISION = "context_precision"
    CONTEXT_RECALL = "context_recall"
    COMPLETENESS = "completeness"
    ACCURACY = "accuracy"
    CLARITY = "clarity"


class EvaluationStatus(str, Enum):
    """评估状态枚举"""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CACHED = "cached"


# ==================== 数据模型 ====================

@dataclass
class EvaluationSample:
    """
    评估样本（输入）

    Attributes:
        query_id: 查询 ID
        query: 用户查询
        response: AI 回复
        context: 检索到的上下文
        sources: 来源信息列表
        ground_truth: 标准答案（可选）
        metadata: 元数据
    """
    query_id: str
    query: str
    response: str
    context: str = ""
    sources: List[Dict[str, Any]] = field(default_factory=list)
    ground_truth: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "query_id": self.query_id,
            "query": self.query,
            "response": self.response,
            "context": self.context[:200] + "..." if len(self.context) > 200 else self.context,
            "sources_count": len(self.sources),
            "has_ground_truth": self.ground_truth is not None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EvaluationSample':
        """从字典创建"""
        return cls(
            query_id=data.get("query_id", ""),
            query=data.get("query", ""),
            response=data.get("response", ""),
            context=data.get("context", ""),
            sources=data.get("sources", []),
            ground_truth=data.get("ground_truth"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class EvaluationResult:
    """
    评估结果（输出）

    Attributes:
        sample_id: 样本 ID
        scores: 各维度得分
        overall_score: 综合得分
        details: 详细信息
        strategy_used: 使用的策略
        status: 评估状态
        timestamp: 评估时间
        error_message: 错误信息（如果失败）
    """
    sample_id: str
    scores: Dict[str, float] = field(default_factory=dict)
    overall_score: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)
    strategy_used: str = ""
    status: EvaluationStatus = EvaluationStatus.COMPLETED
    timestamp: float = field(default_factory=time.time)
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "sample_id": self.sample_id,
            "scores": self.scores,
            "overall_score": self.overall_score,
            "details": self.details,
            "strategy_used": self.strategy_used,
            "status": self.status.value,
            "timestamp": self.timestamp,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EvaluationResult':
        """从字典创建"""
        return cls(
            sample_id=data.get("sample_id", ""),
            scores=data.get("scores", {}),
            overall_score=data.get("overall_score", 0.0),
            details=data.get("details", {}),
            strategy_used=data.get("strategy_used", ""),
            status=EvaluationStatus(data.get("status", "completed")),
            timestamp=data.get("timestamp", time.time()),
            error_message=data.get("error_message"),
        )


@dataclass
class MetricResult:
    """
    指标结果（参考 ragenteval）

    Attributes:
        name: 指标名称
        overall: 整体得分
        per_sample: 每个样本的得分
        meta: 元数据
        is_pct: 是否为百分比
    """
    name: str
    overall: Optional[float]
    per_sample: Dict[str, Optional[float]] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)
    is_pct: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "overall": self.overall,
            "per_sample": self.per_sample,
            "meta": self.meta,
            "is_pct": self.is_pct,
        }


@dataclass
class EvaluationConfig:
    """
    评估配置

    Attributes:
        strategy: 评估策略类型
        dimensions: 评估维度列表
        quality_threshold: 质量阈值
        enable_cache: 是否启用缓存
        cache_ttl: 缓存过期时间（秒）
        language: 语言（zh/en）
    """
    strategy: EvaluationStrategyType = EvaluationStrategyType.HYBRID
    dimensions: List[EvaluationDimension] = field(default_factory=lambda: [
        EvaluationDimension.COMPLETENESS,
        EvaluationDimension.ACCURACY,
        EvaluationDimension.CLARITY,
    ])
    quality_threshold: float = DEFAULT_QUALITY_THRESHOLD
    enable_cache: bool = True
    cache_ttl: int = 3600  # 1小时
    language: str = "zh"


# ==================== 评估策略基类 ====================

class BaseEvaluationStrategy(ABC):
    """评估策略基类"""

    @abstractmethod
    async def evaluate(self, sample: EvaluationSample, config: EvaluationConfig) -> EvaluationResult:
        """
        评估单个样本

        Args:
            sample: 评估样本
            config: 评估配置

        Returns:
            评估结果
        """
        pass

    @abstractmethod
    def get_strategy_type(self) -> EvaluationStrategyType:
        """获取策略类型"""
        pass


# ==================== 基于规则的评估策略 ====================

class RuleBasedEvaluationStrategy(BaseEvaluationStrategy):
    """
    基于规则的评估策略

    使用预定义规则评估答案质量，无需 LLM 调用。
    参考 SelfReflector 的规则评估逻辑。
    """

    def get_strategy_type(self) -> EvaluationStrategyType:
        return EvaluationStrategyType.RULE_BASED

    async def evaluate(self, sample: EvaluationSample, config: EvaluationConfig) -> EvaluationResult:
        """评估单个样本"""
        scores = {}
        details = {}

        # 评估完整性
        if EvaluationDimension.COMPLETENESS in config.dimensions:
            completeness_score, completeness_details = self._evaluate_completeness(sample)
            scores[EvaluationDimension.COMPLETENESS.value] = completeness_score
            details["completeness"] = completeness_details

        # 评估准确性
        if EvaluationDimension.ACCURACY in config.dimensions:
            accuracy_score, accuracy_details = self._evaluate_accuracy(sample)
            scores[EvaluationDimension.ACCURACY.value] = accuracy_score
            details["accuracy"] = accuracy_details

        # 评估清晰度
        if EvaluationDimension.CLARITY in config.dimensions:
            clarity_score, clarity_details = self._evaluate_clarity(sample)
            scores[EvaluationDimension.CLARITY.value] = clarity_score
            details["clarity"] = clarity_details

        # 计算综合得分
        overall_score = self._calculate_overall_score(scores, config.dimensions)

        return EvaluationResult(
            sample_id=sample.query_id,
            scores=scores,
            overall_score=overall_score,
            details=details,
            strategy_used=self.get_strategy_type().value,
            status=EvaluationStatus.COMPLETED,
        )

    def _evaluate_completeness(self, sample: EvaluationSample) -> Tuple[float, Dict[str, Any]]:
        """
        评估完整性

        检查答案是否完整回答了问题。

        Args:
            sample: 评估样本

        Returns:
            (得分, 详细信息)
        """
        details = {
            "has_response": bool(sample.response),
            "response_length": len(sample.response),
            "has_context": bool(sample.context),
            "sources_count": len(sample.sources),
        }

        if not sample.response:
            return 0.0, details

        # 基础分数
        score = CONFIDENCE_BASE_SCORE

        # 响应长度评分
        response_tokens = estimate_tokens(sample.response)
        if response_tokens >= 50:
            score += 0.1
        if response_tokens >= 100:
            score += 0.1

        # 有上下文加分
        if sample.context:
            score += 0.1

        # 有来源加分
        if sample.sources:
            score += 0.1

        # 限制在 0-1 范围内
        score = min(max(score, 0.0), 1.0)

        details["score"] = score
        return score, details

    def _evaluate_accuracy(self, sample: EvaluationSample) -> Tuple[float, Dict[str, Any]]:
        """
        评估准确性

        检查答案是否准确。

        Args:
            sample: 评估样本

        Returns:
            (得分, 详细信息)
        """
        details = {
            "has_response": bool(sample.response),
            "has_context": bool(sample.context),
            "has_ground_truth": sample.ground_truth is not None,
        }

        if not sample.response:
            return 0.0, details

        # 基础分数
        score = CONFIDENCE_BASE_SCORE

        # 如果有标准答案，计算相似度
        if sample.ground_truth:
            similarity = calculate_text_similarity(sample.response, sample.ground_truth)
            score = similarity
            details["ground_truth_similarity"] = similarity
        else:
            # 有上下文时，检查是否引用了上下文
            if sample.context:
                # 简单检查：响应中是否包含上下文中的关键词
                context_keywords = set(re.findall(r'[\w一-鿿]+', sample.context.lower()))
                response_keywords = set(re.findall(r'[\w一-鿿]+', sample.response.lower()))
                overlap = len(context_keywords.intersection(response_keywords))
                if overlap > 0:
                    score += 0.1
                details["context_keyword_overlap"] = overlap

        # 限制在 0-1 范围内
        score = min(max(score, 0.0), 1.0)

        details["score"] = score
        return score, details

    def _evaluate_clarity(self, sample: EvaluationSample) -> Tuple[float, Dict[str, Any]]:
        """
        评估清晰度

        检查答案是否清晰易懂。

        Args:
            sample: 评估样本

        Returns:
            (得分, 详细信息)
        """
        details = {
            "has_response": bool(sample.response),
            "response_length": len(sample.response),
        }

        if not sample.response:
            return 0.0, details

        # 基础分数
        score = CONFIDENCE_BASE_SCORE

        # 检查是否包含常见清晰度指标
        response = sample.response

        # 有段落结构加分
        if "\n" in response:
            score += 0.05

        # 有列表结构加分
        if re.search(r'[\d]+[.、)]', response):
            score += 0.05

        # 有标点符号加分
        if re.search(r'[。，！？,!?]', response):
            score += 0.05

        # 长度适中加分
        response_tokens = estimate_tokens(response)
        if 20 <= response_tokens <= 500:
            score += 0.1

        # 限制在 0-1 范围内
        score = min(max(score, 0.0), 1.0)

        details["score"] = score
        return score, details

    def _calculate_overall_score(
        self,
        scores: Dict[str, float],
        dimensions: List[EvaluationDimension]
    ) -> float:
        """
        计算综合得分

        Args:
            scores: 各维度得分
            dimensions: 评估维度列表

        Returns:
            综合得分
        """
        if not scores:
            return 0.0

        # 计算平均分
        total = sum(scores.values())
        count = len(scores)

        return total / count if count > 0 else 0.0


# ==================== 基于 LLM 的评估策略 ====================

class LLMEvaluationStrategy(BaseEvaluationStrategy):
    """
    基于 LLM 的评估策略

    使用 LLM 评估答案质量。
    """

    def __init__(self, model: str = None):
        """
        初始化

        Args:
            model: LLM 模型名称
        """
        self.model = model

    def get_strategy_type(self) -> EvaluationStrategyType:
        return EvaluationStrategyType.LLM_BASED

    async def evaluate(self, sample: EvaluationSample, config: EvaluationConfig) -> EvaluationResult:
        """评估单个样本"""
        try:
            # 导入 LLM
            from ..llm import get_llm, ChatMessage

            llm = get_llm(model=self.model)

            # 构建评估提示
            prompt = self._build_evaluation_prompt(sample, config)

            # 调用 LLM
            messages = [ChatMessage(role="user", content=prompt)]
            response = await llm.chat(messages=messages, temperature=0.3)

            # 解析 LLM 响应
            scores, details = self._parse_llm_response(response.content, config)

            # 计算综合得分
            overall_score = sum(scores.values()) / len(scores) if scores else 0.0

            return EvaluationResult(
                sample_id=sample.query_id,
                scores=scores,
                overall_score=overall_score,
                details=details,
                strategy_used=self.get_strategy_type().value,
                status=EvaluationStatus.COMPLETED,
            )

        except Exception as e:
            return EvaluationResult(
                sample_id=sample.query_id,
                scores={},
                overall_score=0.0,
                details={"error": str(e)},
                strategy_used=self.get_strategy_type().value,
                status=EvaluationStatus.FAILED,
                error_message=str(e),
            )

    def _build_evaluation_prompt(
        self,
        sample: EvaluationSample,
        config: EvaluationConfig
    ) -> str:
        """
        构建评估提示

        Args:
            sample: 评估样本
            config: 评估配置

        Returns:
            评估提示
        """
        dimensions_desc = "\n".join([
            f"- {dim.value}: 0-1 分"
            for dim in config.dimensions
        ])

        prompt = f"""你是一个答案质量评估专家。请评估以下 AI 回答的质量。

## 用户问题
{sample.query}

## AI 回答
{sample.response}

## 参考上下文
{sample.context if sample.context else "无"}

## 评估维度
{dimensions_desc}

请以 JSON 格式返回评估结果，格式如下：
{{
    "scores": {{
        "维度名": 分数
    }},
    "reasoning": "评估理由"
}}

注意：
1. 分数范围是 0-1
2. 每个维度都需要评估
3. 请给出详细的评估理由
"""
        return prompt

    def _parse_llm_response(
        self,
        response: str,
        config: EvaluationConfig
    ) -> Tuple[Dict[str, float], Dict[str, Any]]:
        """
        解析 LLM 响应

        Args:
            response: LLM 响应
            config: 评估配置

        Returns:
            (得分字典, 详细信息)
        """
        details = {
            "raw_response": response,
        }

        try:
            # 尝试解析 JSON
            # 查找 JSON 部分
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                json_str = json_match.group()
                data = json.loads(json_str)

                scores = data.get("scores", {})
                details["reasoning"] = data.get("reasoning", "")

                # 确保所有需要的维度都有分数
                for dim in config.dimensions:
                    if dim.value not in scores:
                        scores[dim.value] = 0.0

                return scores, details
        except json.JSONDecodeError:
            pass

        # 如果解析失败，返回默认分数
        scores = {dim.value: 0.5 for dim in config.dimensions}
        details["parse_error"] = "Failed to parse LLM response"

        return scores, details


# ==================== 混合评估策略 ====================

class HybridEvaluationStrategy(BaseEvaluationStrategy):
    """
    混合评估策略

    结合规则评估和 LLM 评估。
    规则评估作为基础，LLM 评估作为补充。
    """

    def __init__(self, model: str = None):
        """
        初始化

        Args:
            model: LLM 模型名称
        """
        self.rule_strategy = RuleBasedEvaluationStrategy()
        self.llm_strategy = LLMEvaluationStrategy(model=model)

    def get_strategy_type(self) -> EvaluationStrategyType:
        return EvaluationStrategyType.HYBRID

    async def evaluate(self, sample: EvaluationSample, config: EvaluationConfig) -> EvaluationResult:
        """评估单个样本"""
        # 先进行规则评估
        rule_result = await self.rule_strategy.evaluate(sample, config)

        # 如果规则评估分数较高，直接返回
        if rule_result.overall_score >= 0.8:
            rule_result.details["evaluation_method"] = "rule_based"
            return rule_result

        # 否则进行 LLM 评估
        try:
            llm_result = await self.llm_strategy.evaluate(sample, config)

            # 合并分数（取平均）
            combined_scores = {}
            for dim in config.dimensions:
                dim_key = dim.value
                rule_score = rule_result.scores.get(dim_key, 0.0)
                llm_score = llm_result.scores.get(dim_key, 0.0)
                combined_scores[dim_key] = (rule_score + llm_score) / 2

            # 计算综合得分
            overall_score = sum(combined_scores.values()) / len(combined_scores) if combined_scores else 0.0

            return EvaluationResult(
                sample_id=sample.query_id,
                scores=combined_scores,
                overall_score=overall_score,
                details={
                    "rule_result": rule_result.to_dict(),
                    "llm_result": llm_result.to_dict(),
                    "evaluation_method": "hybrid",
                },
                strategy_used=self.get_strategy_type().value,
                status=EvaluationStatus.COMPLETED,
            )

        except Exception as e:
            # LLM 评估失败，返回规则评估结果
            rule_result.details["evaluation_method"] = "rule_based_fallback"
            rule_result.details["llm_error"] = str(e)
            return rule_result


# ==================== 主类 ====================

class AnswerQualityEvaluator:
    """
    答案质量评估器

    提供多种评估策略，用于评估 AI 回复的质量。
    """

    def __init__(
        self,
        strategy_type: EvaluationStrategyType = EvaluationStrategyType.HYBRID,
        config: EvaluationConfig = None,
        **kwargs
    ):
        """
        初始化

        Args:
            strategy_type: 评估策略类型
            config: 评估配置
            **kwargs: 其他参数
        """
        self.strategy_type = strategy_type
        self.config = config or EvaluationConfig(strategy=strategy_type)
        self.strategy = self._create_strategy(strategy_type, **kwargs)
        self.cache: Dict[str, EvaluationResult] = {}
        self.cache_timestamps: Dict[str, float] = {}

    def _create_strategy(
        self,
        strategy_type: EvaluationStrategyType,
        **kwargs
    ) -> BaseEvaluationStrategy:
        """
        创建策略实例

        Args:
            strategy_type: 策略类型
            **kwargs: 其他参数

        Returns:
            策略实例
        """
        if strategy_type == EvaluationStrategyType.RULE_BASED:
            return RuleBasedEvaluationStrategy()
        elif strategy_type == EvaluationStrategyType.LLM_BASED:
            return LLMEvaluationStrategy(**kwargs)
        elif strategy_type == EvaluationStrategyType.HYBRID:
            return HybridEvaluationStrategy(**kwargs)
        else:
            raise ValueError(f"Unknown strategy type: {strategy_type}")

    def _generate_cache_key(self, sample: EvaluationSample) -> str:
        """
        生成缓存键

        Args:
            sample: 评估样本

        Returns:
            缓存键
        """
        content = f"{sample.query_id}:{sample.query}:{sample.response}:{sample.context}"
        return hashlib.md5(content.encode()).hexdigest()

    def _is_cache_valid(self, cache_key: str) -> bool:
        """
        检查缓存是否有效

        Args:
            cache_key: 缓存键

        Returns:
            是否有效
        """
        if cache_key not in self.cache:
            return False

        if not self.config.enable_cache:
            return False

        timestamp = self.cache_timestamps.get(cache_key, 0)
        return (time.time() - timestamp) < self.config.cache_ttl

    async def evaluate(self, sample: EvaluationSample) -> EvaluationResult:
        """
        评估单个样本

        Args:
            sample: 评估样本

        Returns:
            评估结果
        """
        # 检查缓存
        cache_key = self._generate_cache_key(sample)
        if self._is_cache_valid(cache_key):
            result = self.cache[cache_key]
            result.status = EvaluationStatus.CACHED
            return result

        # 执行评估
        result = await self.strategy.evaluate(sample, self.config)

        # 缓存结果
        if self.config.enable_cache:
            self.cache[cache_key] = result
            self.cache_timestamps[cache_key] = time.time()

        return result

    async def evaluate_batch(self, samples: List[EvaluationSample]) -> List[EvaluationResult]:
        """
        批量评估

        Args:
            samples: 评估样本列表

        Returns:
            评估结果列表
        """
        results = []
        for sample in samples:
            result = await self.evaluate(sample)
            results.append(result)
        return results

    def get_metrics(self, results: List[EvaluationResult]) -> List[MetricResult]:
        """
        计算指标

        Args:
            results: 评估结果列表

        Returns:
            指标结果列表
        """
        metrics = []

        # 收集所有维度
        all_dimensions = set()
        for result in results:
            all_dimensions.update(result.scores.keys())

        # 为每个维度计算指标
        for dim in all_dimensions:
            dim_scores = []
            per_sample = {}

            for result in results:
                score = result.scores.get(dim)
                if score is not None:
                    dim_scores.append(score)
                    per_sample[result.sample_id] = score

            # 计算整体均值
            overall = sum(dim_scores) / len(dim_scores) if dim_scores else None

            metrics.append(MetricResult(
                name=dim,
                overall=overall,
                per_sample=per_sample,
                meta={
                    "count": len(dim_scores),
                    "min": min(dim_scores) if dim_scores else None,
                    "max": max(dim_scores) if dim_scores else None,
                },
            ))

        # 计算综合得分指标
        overall_scores = [r.overall_score for r in results if r.overall_score > 0]
        if overall_scores:
            metrics.append(MetricResult(
                name="overall_score",
                overall=sum(overall_scores) / len(overall_scores),
                per_sample={r.sample_id: r.overall_score for r in results},
                meta={
                    "count": len(overall_scores),
                    "min": min(overall_scores),
                    "max": max(overall_scores),
                },
            ))

        return metrics

    def clear_cache(self):
        """清空缓存"""
        self.cache.clear()
        self.cache_timestamps.clear()


# ==================== 工厂类 ====================

class AnswerQualityEvaluatorFactory:
    """评估器工厂"""

    @staticmethod
    def create(
        strategy_type: EvaluationStrategyType = EvaluationStrategyType.HYBRID,
        config: EvaluationConfig = None,
        **kwargs
    ) -> AnswerQualityEvaluator:
        """
        创建评估器实例

        Args:
            strategy_type: 策略类型
            config: 评估配置
            **kwargs: 其他参数

        Returns:
            评估器实例
        """
        return AnswerQualityEvaluator(
            strategy_type=strategy_type,
            config=config,
            **kwargs
        )


# ==================== 全局实例管理 ====================

_evaluator: Optional[AnswerQualityEvaluator] = None


def get_evaluator(
    strategy_type: EvaluationStrategyType = EvaluationStrategyType.HYBRID,
    **kwargs
) -> AnswerQualityEvaluator:
    """
    获取全局评估器实例

    Args:
        strategy_type: 策略类型（默认混合策略）
        **kwargs: 其他参数

    Returns:
        评估器实例
    """
    global _evaluator

    if _evaluator is None:
        _evaluator = AnswerQualityEvaluatorFactory.create(strategy_type, **kwargs)

    return _evaluator


def reset_evaluator():
    """重置全局评估器（用于测试）"""
    global _evaluator
    _evaluator = None
