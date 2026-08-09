"""
上下文压缩器模块

提供多种压缩策略，用于压缩检索结果，减少 token 消耗：
- ExtractiveCompressionStrategy: 抽取式压缩（基于重要性评分）
- AbstractiveCompressionStrategy: 生成式压缩（使用 LLM）
- HybridCompressionStrategy: 混合压缩（结合抽取和生成）
- RecursiveCompressionStrategy: 递归压缩（逐步压缩）

设计模式：
- 枚举模式：CompressionStrategyType - 类型安全的策略选择
- 策略模式：多种压缩策略，运行时可切换
- 工厂模式：ContextCompressorFactory - 统一创建压缩器实例
- 缓存模式：减少重复压缩计算

作者：Claude
日期：2026-07-22
"""

import asyncio
import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .base import BaseCompressionStrategy
from .cache import CacheManager
from .tokenization import tokenize
from .utils import (
    MAX_KEY_PHRASES,
    estimate_tokens,
    extract_key_phrases,
    split_sentences,
)

# ---- Compression guard thresholds ----
# Tokens below this threshold == skip compression entirely
_MIN_COMPRESSION_TOKENS = 300
# Characters below this threshold == skip compression entirely (rough CJK equivalent)
_MIN_COMPRESSION_CHARS = 600
# RAG 编号块标记（react._retrieve_context 产出的行首 [n] 行），保溯源压缩用
_BLOCK_MARKER_RE = re.compile(r"(?m)^\[(\d{1,2})\][^\n]*\n")


# ==================== 枚举定义 ====================

class CompressionStrategyType(str, Enum):
    """压缩策略类型枚举"""
    EXTRACTIVE = "extractive"
    ABSTRACTIVE = "abstractive"
    HYBRID = "hybrid"
    RECURSIVE = "recursive"


class CompressionStatus(str, Enum):
    """压缩状态枚举"""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


# ==================== 数据模型 ====================

@dataclass
class CompressionResult:
    """
    压缩结果

    Attributes:
        original_text: 原始文本
        compressed_text: 压缩后文本
        original_tokens: 原始 token 数
        compressed_tokens: 压缩后 token 数
        compression_ratio: 压缩率（压缩后/压缩前）
        strategy_used: 使用的策略
        key_phrases: 提取的关键短语
        summary: 摘要（可选）
        status: 压缩状态
        error_message: 错误信息（如果失败）
    """
    original_text: str
    compressed_text: str
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    strategy_used: str
    key_phrases: list[str] = field(default_factory=list)
    summary: str | None = None
    status: CompressionStatus = CompressionStatus.COMPLETED
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "original_text": self.original_text[:100] + "..." if len(self.original_text) > 100 else self.original_text,
            "compressed_text": self.compressed_text,
            "original_tokens": self.original_tokens,
            "compressed_tokens": self.compressed_tokens,
            "compression_ratio": self.compression_ratio,
            "strategy_used": self.strategy_used,
            "key_phrases": self.key_phrases,
            "summary": self.summary,
            "status": self.status.value,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'CompressionResult':
        """从字典创建"""
        return cls(
            original_text=data.get("original_text", ""),
            compressed_text=data.get("compressed_text", ""),
            original_tokens=data.get("original_tokens", 0),
            compressed_tokens=data.get("compressed_tokens", 0),
            compression_ratio=data.get("compression_ratio", 0.0),
            strategy_used=data.get("strategy_used", ""),
            key_phrases=data.get("key_phrases", []),
            summary=data.get("summary"),
            status=CompressionStatus(data.get("status", "completed")),
            error_message=data.get("error_message"),
        )


@dataclass
class CompressionConfig:
    """
    压缩配置

    Attributes:
        strategy: 压缩策略类型
        target_ratio: 目标压缩率（0-1，0.5 表示压缩到原来的一半）
        max_tokens: 最大 token 数
        preserve_keywords: 保留的关键词
        language: 语言（zh/en）
        min_sentence_length: 最小句子长度
    """
    strategy: CompressionStrategyType = CompressionStrategyType.EXTRACTIVE
    target_ratio: float = 0.5
    max_tokens: int | None = None
    preserve_keywords: list[str] | None = None
    language: str = "zh"
    min_sentence_length: int = 10


# ==================== 抽取式压缩策略 ====================

class ExtractiveCompressionStrategy(BaseCompressionStrategy):
    """
    抽取式压缩策略

    基于句子重要性评分，保留关键句子。
    使用 TextRank 算法的简化版本。

    优点：
    - 快速，无需 LLM
    - 保留原始表述

    缺点：
    - 可能不够连贯
    """

    def __init__(self, **kwargs):
        """初始化"""
        self.name = "extractive"

    def get_strategy_name(self) -> str:
        """获取策略名称"""
        return self.name

    def get_strategy_type(self) -> CompressionStrategyType:
        """获取策略类型"""
        return CompressionStrategyType.EXTRACTIVE

    async def compress(
        self,
        text: str,
        config: CompressionConfig | None = None,
        **kwargs
    ) -> CompressionResult:
        """
        压缩文本

        Args:
            text: 原始文本
            config: 压缩配置

        Returns:
            压缩结果
        """
        if config is None:
            config = CompressionConfig()
        # query 经 kwargs 透传：提供时句子评分加入与问题的词元重叠信号，
        # 避免丢掉与问题相关但事实密度低的句子；缺省行为与历史版本一致
        query = kwargs.get("query")

        # 估算 token 数
        original_tokens = self.estimate_tokens(text)

        # ---- 短文本保护：低于阈值不压缩，避免丢失关键事实 ----
        if original_tokens < _MIN_COMPRESSION_TOKENS or len(text) < _MIN_COMPRESSION_CHARS:
            key_phrases = self._extract_key_phrases(text)
            return CompressionResult(
                original_text=text,
                compressed_text=text,
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
                compression_ratio=1.0,
                strategy_used=self.name,
                key_phrases=key_phrases,
                status=CompressionStatus.COMPLETED,
            )

        # 分句
        sentences = self._split_sentences(text)
        if not sentences:
            return CompressionResult(
                original_text=text,
                compressed_text=text,
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
                compression_ratio=1.0,
                strategy_used=self.name,
                status=CompressionStatus.COMPLETED,
            )

        # 计算每个句子的重要性得分
        sentence_scores = self._calculate_sentence_scores(sentences, text, query=query)

        # 确定要保留的句子数量
        target_count = max(1, int(len(sentences) * config.target_ratio))

        # 按得分排序，保留 top-k
        scored_sentences = list(zip(sentences, sentence_scores))
        scored_sentences.sort(key=lambda x: x[1], reverse=True)

        # 保留得分最高的句子
        selected_sentences = [s[0] for s in scored_sentences[:target_count]]

        # 按原始顺序重新排列
        sentence_order = {s: i for i, s in enumerate(sentences)}
        selected_sentences.sort(key=lambda s: sentence_order.get(s, 0))

        # 重新组合成文本
        compressed_text = "".join(selected_sentences)

        # 提取关键短语
        key_phrases = self._extract_key_phrases(text)

        # 估算压缩后的 token 数
        compressed_tokens = self.estimate_tokens(compressed_text)

        # 计算压缩率
        compression_ratio = compressed_tokens / original_tokens if original_tokens > 0 else 1.0

        return CompressionResult(
            original_text=text,
            compressed_text=compressed_text,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            compression_ratio=compression_ratio,
            strategy_used=self.name,
            key_phrases=key_phrases,
            status=CompressionStatus.COMPLETED,
        )

    def estimate_tokens(self, text: str) -> int:
        """估算 token 数"""
        return estimate_tokens(text)

    def _split_sentences(self, text: str) -> list[str]:
        """分句"""
        return split_sentences(text, min_length=2)

    # Patterns that indicate factual density — sentences matching these carry
    # evidence the model needs and must not be dropped by compression.
    _FACT_PATTERNS: list[re.Pattern] = [
        re.compile(p, re.UNICODE)
        for p in [
            # Numbers with units (42%, ¥100, 3.14, 1,000 万)
            r'\d+(?:[,.]\d+)?\s*(?:%|万|亿|元|美元|欧元|日元|英镑|港币|k|K|M|B|tokens?|ms|s|MB|GB|KB|TB)',
            # Numeric ranges or values (>=5, 30-50, +15%)
            r'[>=<]\s*\d+|[+\-]\d+[%％]|\d+\s*[-—]\s*\d+',
            # Dates and times (2024年, 2024-01-15, Q1, 12月)
            r'\d{4}\s*[年/\-]\s*\d{1,2}\s*[月/\-]|\bQ[1-4]\b|\d{1,2}\s*月',
            # Code / technical tokens
            r'\b(function|class|def|import|from|return|SELECT|WHERE|INSERT|UPDATE)\b',
            r'`[^`]+`|```|@\w+|#\w+',
            # Proper nouns: Chinese person/organization names
            r'[一-鿿]{2,4}(?:公司|集团|大学|医院|银行|基金|部门|委员会|平台|系统|模型|算法)',
            # English proper nouns
            r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b|\b[A-Z]{2,}\b',
            # Key evidence markers
            r'(?:关键|重要|核心|结论|发现|根据|数据|显示|表明|证明|证实|结果|统计|报告)',
            r'(?:得分|排名|增长|下降|提升|降低|占比|达到|突破|超过|低于|高于)',
        ]
    ]

    @classmethod
    def _factual_density_score(cls, sentence: str) -> float:
        """Score a sentence by how many distinct fact-pattern categories it matches.

        Returns a value in [0, 1]; higher means the sentence is denser in
        numbers, dates, code, proper nouns and evidence markers.
        """
        if not sentence:
            return 0.0
        matched = 0
        for pattern in cls._FACT_PATTERNS:
            if pattern.search(sentence):
                matched += 1
        return min(1.0, matched / max(len(cls._FACT_PATTERNS) * 0.5, 1))

    def _calculate_sentence_scores(
        self,
        sentences: list[str],
        full_text: str,
        query: str | None = None,
    ) -> list[float]:
        """
        计算句子重要性得分。

        Weight breakdown (evidence-first + query-aware):
        - factual density  — 0.40  (numbers, dates, code, proper nouns, evidence markers)
        - query overlap    — 0.30  (与问题的词元重叠；无 query 时权重回收到其余项)
        - length            — 0.10  (longer sentences typically carry more info)
        - position          — 0.10  (opening / closing sentences set context)
        - keyword overlap   — 0.10  (overlap with key phrases in full text)

        query 信号解决一个盲区：纯"事实密度"评分会把与问题直接相关但不含
        数字/日期等事实标记的句子无差别丢掉——而这些句子往往正是回答所
        需要的证据。query 缺省（None/空）时退回无 query 的旧行为。
        """
        # 无 query 时按原有权重分布归一（事实密度主导），保持向后兼容
        if query and tokenize(query):
            weight_fact, weight_query, weight_len, weight_pos, weight_kw = (
                0.40, 0.30, 0.10, 0.10, 0.10)
            query_terms = set(tokenize(query))
        else:
            weight_fact, weight_query, weight_len, weight_pos, weight_kw = (
                0.50, 0.00, 0.20, 0.15, 0.15)
            query_terms = set()

        scores = []
        max_len = max((len(s) for s in sentences), default=1)
        key_phrases = self._extract_key_phrases(full_text)

        for i, sentence in enumerate(sentences):
            # 1. Factual density (evidence must survive)
            fact_score = self._factual_density_score(sentence)

            # 2. Query overlap: 命中的不同 query 词元占比
            query_score = 0.0
            if query_terms:
                sentence_terms = set(tokenize(sentence))
                query_score = (
                    len(query_terms & sentence_terms) / len(query_terms)
                    if query_terms else 0.0
                )

            # 3. Length score
            length_score = len(sentence) / max_len

            # 4. Position score
            if i == 0:
                position_score = 1.0
            elif i == len(sentences) - 1:
                position_score = 0.8
            else:
                position_score = 0.5

            # 5. Keyword overlap with the full text key phrases
            kw_overlap = 0.0
            if key_phrases:
                hits = sum(1 for kw in key_phrases if kw in sentence)
                kw_overlap = min(1.0, hits / max(len(key_phrases), 1))

            total_score = (
                fact_score * weight_fact +
                query_score * weight_query +
                length_score * weight_len +
                position_score * weight_pos +
                kw_overlap * weight_kw
            )
            scores.append(total_score)

        return scores

    def rank_sentences(
        self,
        sentences: list[str],
        full_text: str,
        query: str | None = None,
    ) -> list[float]:
        """公开的句子打分入口：压缩选择与离线评测共用同一打分实现。

        离线评测轨用它做压缩感知的引用模拟（存活句归属 chunk），若各自
        实现打分逻辑，生产与评测的口径会静默漂移。
        """
        return self._calculate_sentence_scores(sentences, full_text, query=query)

    def _extract_key_phrases(self, text: str) -> list[str]:
        """提取关键短语"""
        return extract_key_phrases(text, MAX_KEY_PHRASES)

    @staticmethod
    def list_block_numbers(text: str) -> list[int]:
        """列出文本中的编号块号（`[n]` 行首标记），保持出现顺序。"""
        return [int(m.group(1)) for m in _BLOCK_MARKER_RE.finditer(text)]

    async def compress_numbered_blocks(
        self,
        text: str,
        config: CompressionConfig | None = None,
        query: str | None = None,
    ) -> tuple[str, list[int], bool]:
        """对 ``[n]`` 编号块上下文做**保溯源**压缩（RAG 引用约束的基座）。

        编号块格式（见 ``react._retrieve_context``）::

            [1] (语义匹配, 相似度: 0.87)
            第一句。第二句。

        压缩在**合并文本**上全局打分选句（与 ``compress`` 同一评分实现与
        预算公式），但重建时按块归属拼回，并只保留至少有一句存活的块——
        编号 ``n`` 与外部 ``sources[n-1]`` 的对应关系因此贯穿压缩全程，
        答案里的 ``[n]`` 标注才能映射回真实来源 chunk。

        Returns:
            ``(压缩后文本, 存活块号列表, 是否执行了压缩)``。文本低于短文本
            守卫阈值时原样返回（全部块存活，未压缩）；文本不含编号块时
            回退普通 ``compress``（块号列表为空——调用方此时无法引用溯源）。
        """
        if config is None:
            config = CompressionConfig()

        marker_matches = list(_BLOCK_MARKER_RE.finditer(text))
        if not marker_matches:
            result = await self.compress(text, config, query=query)
            return result.compressed_text, [], result.compressed_text != text

        original_tokens = self.estimate_tokens(text)
        if (original_tokens < _MIN_COMPRESSION_TOKENS
                or len(text) < _MIN_COMPRESSION_CHARS):
            return text, self.list_block_numbers(text), False

        # 按块切分：块内容 = 标记行之后到下一标记行之前
        blocks: list[tuple[int, str, str]] = []  # (块号, 标记行, 内容)
        for idx, match in enumerate(marker_matches):
            start = match.end()
            end = marker_matches[idx + 1].start() if idx + 1 < len(marker_matches) else len(text)
            blocks.append((int(match.group(1)), match.group(0), text[start:end]))

        sentences: list[str] = []
        owners: list[int] = []
        for number, _marker, content in blocks:
            for sentence in split_sentences(content, min_length=2):
                sentences.append(sentence)
                owners.append(number)
        if not sentences:
            return text, self.list_block_numbers(text), False

        scores = self._calculate_sentence_scores(sentences, text, query=query)
        target_count = max(1, int(len(sentences) * config.target_ratio))
        kept = sorted(range(len(sentences)), key=lambda i: -scores[i])[:target_count]
        surviving_by_block: dict[int, list[int]] = {}
        for i in kept:
            surviving_by_block.setdefault(owners[i], []).append(i)

        # 重建：块按原始顺序输出（保持 [n] 与 sources 的对应），块内句子按原顺序
        parts: list[str] = []
        kept_numbers: list[int] = []
        for number, marker, content in blocks:
            indices = surviving_by_block.get(number)
            if not indices:
                continue
            kept_numbers.append(number)
            body = "".join(sentences[i] for i in sorted(indices))
            parts.append(f"{marker}{body}")
        compressed = "\n\n".join(parts)
        return compressed, kept_numbers, compressed != text


# ==================== 生成式压缩策略 ====================

class AbstractiveCompressionStrategy(BaseCompressionStrategy):
    """
    生成式压缩策略

    使用 LLM 生成压缩后的摘要。

    优点：
    - 更连贯，更自然
    - 可以重新组织信息

    缺点：
    - 需要 LLM，成本较高
    - 速度较慢
    """

    def __init__(self, llm=None, **kwargs):
        """
        初始化

        Args:
            llm: LLM 实例（可选）
        """
        self.llm = llm
        self.name = "abstractive"

    def get_strategy_name(self) -> str:
        """获取策略名称"""
        return self.name

    def get_strategy_type(self) -> CompressionStrategyType:
        """获取策略类型"""
        return CompressionStrategyType.ABSTRACTIVE

    async def compress(
        self,
        text: str,
        config: CompressionConfig | None = None,
        **kwargs
    ) -> CompressionResult:
        """压缩文本"""
        if config is None:
            config = CompressionConfig()

        # 估算 token 数
        original_tokens = self.estimate_tokens(text)

        # 检查是否有 LLM
        if self.llm is None:
            # 降级到抽取式压缩
            fallback = ExtractiveCompressionStrategy()
            return await fallback.compress(text, config)

        try:
            # 构建压缩提示
            prompt = self._build_compression_prompt(text, config)

            # 调用 LLM
            if hasattr(self.llm, 'ainvoke'):
                response = await self.llm.ainvoke(prompt)
                compressed_text = response.content if hasattr(response, 'content') else str(response)
            else:
                # 降级到抽取式压缩
                fallback = ExtractiveCompressionStrategy()
                return await fallback.compress(text, config)

            # 提取关键短语
            key_phrases = self._extract_key_phrases(text)

            # 估算压缩后的 token 数
            compressed_tokens = self.estimate_tokens(compressed_text)

            # 计算压缩率
            compression_ratio = compressed_tokens / original_tokens if original_tokens > 0 else 1.0

            return CompressionResult(
                original_text=text,
                compressed_text=compressed_text,
                original_tokens=original_tokens,
                compressed_tokens=compressed_tokens,
                compression_ratio=compression_ratio,
                strategy_used=self.name,
                key_phrases=key_phrases,
                summary=compressed_text,
                status=CompressionStatus.COMPLETED,
            )

        except Exception:
            # 降级到抽取式压缩
            fallback = ExtractiveCompressionStrategy()
            return await fallback.compress(text, config)

    def estimate_tokens(self, text: str) -> int:
        """估算 token 数"""
        return estimate_tokens(text)

    def _build_compression_prompt(
        self,
        text: str,
        config: CompressionConfig
    ) -> str:
        """构建压缩提示"""
        target_tokens = int(self.estimate_tokens(text) * config.target_ratio)

        if config.language == "zh":
            return f"""请将以下文本压缩到约 {target_tokens} 个 token，保留关键信息：

原文：
{text}

要求：
1. 保留所有重要信息
2. 删除冗余内容
3. 保持文本连贯性
4. 输出压缩后的文本

压缩后文本："""
        else:
            return f"""Please compress the following text to approximately {target_tokens} tokens, preserving key information:

Original text:
{text}

Requirements:
1. Preserve all important information
2. Remove redundant content
3. Maintain text coherence
4. Output the compressed text

Compressed text:"""

    def _extract_key_phrases(self, text: str) -> list[str]:
        """提取关键短语"""
        return extract_key_phrases(text, MAX_KEY_PHRASES)


# ==================== 混合压缩策略 ====================

class HybridCompressionStrategy(BaseCompressionStrategy):
    """
    混合压缩策略

    结合抽取和生成：
    1. 先用抽取式提取关键句子
    2. 再用 LLM 优化这些句子

    优点：
    - 平衡速度和质量
    """

    def __init__(self, llm=None, **kwargs):
        """初始化"""
        self.llm = llm
        self.extractive = ExtractiveCompressionStrategy()
        self.name = "hybrid"

    def get_strategy_name(self) -> str:
        """获取策略名称"""
        return self.name

    def get_strategy_type(self) -> CompressionStrategyType:
        """获取策略类型"""
        return CompressionStrategyType.HYBRID

    async def compress(
        self,
        text: str,
        config: CompressionConfig | None = None,
        **kwargs
    ) -> CompressionResult:
        """压缩文本"""
        if config is None:
            config = CompressionConfig()

        # 估算 token 数
        original_tokens = self.estimate_tokens(text)

        # 第一步：抽取式压缩
        extractive_result = await self.extractive.compress(text, config)

        # 如果没有 LLM，直接返回抽取式结果
        if self.llm is None:
            return CompressionResult(
                original_text=text,
                compressed_text=extractive_result.compressed_text,
                original_tokens=original_tokens,
                compressed_tokens=extractive_result.compressed_tokens,
                compression_ratio=extractive_result.compression_ratio,
                strategy_used=self.name,
                key_phrases=extractive_result.key_phrases,
                summary=extractive_result.compressed_text,
                status=CompressionStatus.COMPLETED,
            )

        try:
            # 第二步：用 LLM 优化
            prompt = self._build_optimization_prompt(
                text,
                extractive_result.compressed_text,
                config
            )

            if hasattr(self.llm, 'ainvoke'):
                response = await self.llm.ainvoke(prompt)
                optimized_text = response.content if hasattr(response, 'content') else str(response)
            else:
                optimized_text = extractive_result.compressed_text

            # 提取关键短语
            key_phrases = self._extract_key_phrases(text)

            # 估算压缩后的 token 数
            compressed_tokens = self.estimate_tokens(optimized_text)

            # 计算压缩率
            compression_ratio = compressed_tokens / original_tokens if original_tokens > 0 else 1.0

            return CompressionResult(
                original_text=text,
                compressed_text=optimized_text,
                original_tokens=original_tokens,
                compressed_tokens=compressed_tokens,
                compression_ratio=compression_ratio,
                strategy_used=self.name,
                key_phrases=key_phrases,
                summary=optimized_text,
                status=CompressionStatus.COMPLETED,
            )

        except Exception:
            # 降级到抽取式结果
            return CompressionResult(
                original_text=text,
                compressed_text=extractive_result.compressed_text,
                original_tokens=original_tokens,
                compressed_tokens=extractive_result.compressed_tokens,
                compression_ratio=extractive_result.compression_ratio,
                strategy_used=self.name,
                key_phrases=extractive_result.key_phrases,
                summary=extractive_result.compressed_text,
                status=CompressionStatus.COMPLETED,
            )

    def estimate_tokens(self, text: str) -> int:
        """估算 token 数"""
        return estimate_tokens(text)

    def _build_optimization_prompt(
        self,
        original_text: str,
        extracted_text: str,
        config: CompressionConfig
    ) -> str:
        """构建优化提示"""
        if config.language == "zh":
            return f"""请优化以下抽取式压缩的结果，使其更连贯、更自然：

原文片段：
{extracted_text}

要求：
1. 保持关键信息
2. 提高文本连贯性
3. 删除冗余内容
4. 输出优化后的文本

优化后文本："""
        else:
            return f"""Please optimize the following extractive compression result to make it more coherent and natural:

Extracted text:
{extracted_text}

Requirements:
1. Preserve key information
2. Improve text coherence
3. Remove redundant content
4. Output the optimized text

Optimized text:"""

    def _extract_key_phrases(self, text: str) -> list[str]:
        """提取关键短语"""
        return extract_key_phrases(text, MAX_KEY_PHRASES)


# ==================== 递归压缩策略 ====================

class RecursiveCompressionStrategy(BaseCompressionStrategy):
    """
    递归压缩策略

    逐步压缩，直到达到目标长度。

    优点：
    - 精确控制压缩率
    """

    def __init__(self, **kwargs):
        """初始化"""
        self.extractive = ExtractiveCompressionStrategy()
        self.name = "recursive"

    def get_strategy_name(self) -> str:
        """获取策略名称"""
        return self.name

    def get_strategy_type(self) -> CompressionStrategyType:
        """获取策略类型"""
        return CompressionStrategyType.RECURSIVE

    async def compress(
        self,
        text: str,
        config: CompressionConfig | None = None,
        **kwargs
    ) -> CompressionResult:
        """压缩文本"""
        if config is None:
            config = CompressionConfig()

        # 估算 token 数
        original_tokens = self.estimate_tokens(text)

        # 如果已经满足目标，直接返回
        if config.max_tokens and original_tokens <= config.max_tokens:
            return CompressionResult(
                original_text=text,
                compressed_text=text,
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
                compression_ratio=1.0,
                strategy_used=self.name,
                key_phrases=self._extract_key_phrases(text),
                status=CompressionStatus.COMPLETED,
            )

        # 递归压缩
        current_text = text
        current_tokens = original_tokens
        iteration = 0
        max_iterations = 5

        # max_tokens 未配置时不做阈值压缩（避免 int > None TypeError），
        # 直接按 target_ratio 迭代压缩
        while (config.max_tokens is None or current_tokens > config.max_tokens) and iteration < max_iterations:
            # 每次压缩 30%
            current_config = CompressionConfig(
                strategy=CompressionStrategyType.EXTRACTIVE,
                target_ratio=0.7,
                language=config.language,
            )

            result = await self.extractive.compress(current_text, current_config)
            current_text = result.compressed_text
            current_tokens = result.compressed_tokens
            iteration += 1

        # 提取关键短语
        key_phrases = self._extract_key_phrases(text)

        # 计算压缩率
        compression_ratio = current_tokens / original_tokens if original_tokens > 0 else 1.0

        return CompressionResult(
            original_text=text,
            compressed_text=current_text,
            original_tokens=original_tokens,
            compressed_tokens=current_tokens,
            compression_ratio=compression_ratio,
            strategy_used=self.name,
            key_phrases=key_phrases,
            status=CompressionStatus.COMPLETED,
        )

    def estimate_tokens(self, text: str) -> int:
        """估算 token 数"""
        return estimate_tokens(text)

    def _extract_key_phrases(self, text: str) -> list[str]:
        """提取关键短语"""
        return extract_key_phrases(text, MAX_KEY_PHRASES)


# ==================== 主类 ====================

class ContextCompressor:
    """
    上下文压缩器主类

    用于压缩检索结果，减少 token 消耗。

    设计模式：
    - 缓存模式：避免重复压缩
    - 策略模式：支持多种压缩策略

    使用示例：
        compressor = ContextCompressor()
        result = await compressor.compress("长文本...")
        print(f"压缩率: {result.compression_ratio:.2%}")
    """

    def __init__(
        self,
        strategy=None,
        cache_enabled: bool = True,
        cache_ttl: int = 3600,
        llm=None,
        cache: CacheManager | None = None,
        **kwargs
    ):
        """
        初始化压缩器

        Args:
            strategy: 压缩策略（可选，默认为 ExtractiveCompressionStrategy）
            cache_enabled: 是否启用缓存
            cache_ttl: 缓存过期时间（秒）
            llm: LLM 实例（可选）
            cache: 缓存管理器实例（可选）
        """
        if strategy is None:
            self.strategy = ExtractiveCompressionStrategy(llm=llm)
        elif isinstance(strategy, str):
            # 如果传入的是字符串，转换为枚举
            strategy_type = CompressionStrategyType(strategy)
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
                name="context_compressor"
            )

        # 保持向后兼容
        self.cache_enabled = self._cache_manager.enabled
        self.cache_ttl = self._cache_manager.ttl
        self._cache = self._cache_manager._cache

    def _create_strategy(
        self,
        strategy_type: CompressionStrategyType,
        llm=None
    ):
        """根据类型创建策略实例"""
        strategy_map = {
            CompressionStrategyType.EXTRACTIVE: ExtractiveCompressionStrategy,
            CompressionStrategyType.ABSTRACTIVE: AbstractiveCompressionStrategy,
            CompressionStrategyType.HYBRID: HybridCompressionStrategy,
            CompressionStrategyType.RECURSIVE: RecursiveCompressionStrategy,
        }

        if strategy_type not in strategy_map:
            raise ValueError(f"Unknown strategy type: {strategy_type}")

        strategy_class = strategy_map[strategy_type]
        return strategy_class(llm=llm)

    async def compress(
        self,
        text: str,
        config: CompressionConfig | None = None,
        **kwargs
    ) -> CompressionResult:
        """
        压缩文本

        Args:
            text: 原始文本
            config: 压缩配置
            query: 触发检索的用户问题（影响抽取式评分的 query 重叠信号，
                已纳入缓存键——不同问题对同一文本的压缩结果不同）

        Returns:
            压缩结果
        """
        if config is None:
            config = CompressionConfig()

        # 1. 检查缓存（query 影响压缩结果，必须进缓存键）
        cache_key = self._get_cache_key(text, config, query=kwargs.get("query"))
        cached_result = self._cache_manager.get(cache_key)
        if cached_result is not None:
            return cached_result

        # 2. 执行压缩
        try:
            result = await self.strategy.compress(text, config, **kwargs)
        except Exception as e:
            # 如果压缩失败，返回原始文本
            original_tokens = self._estimate_tokens(text)
            result = CompressionResult(
                original_text=text,
                compressed_text=text,
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
                compression_ratio=1.0,
                strategy_used="failed",
                status=CompressionStatus.FAILED,
                error_message=str(e),
            )

        # 3. 缓存结果
        self._cache_manager.set(cache_key, result)

        return result

    async def compress_batch(
        self,
        texts: list[str],
        config: CompressionConfig | None = None,
        **kwargs
    ) -> list[CompressionResult]:
        """
        批量压缩

        Args:
            texts: 文本列表
            config: 压缩配置

        Returns:
            压缩结果列表
        """
        tasks = [self.compress(text, config, **kwargs) for text in texts]
        return await asyncio.gather(*tasks)

    def _get_cache_key(
        self,
        text: str,
        config: CompressionConfig | None,
        query: str | None = None,
    ) -> str:
        """生成缓存键（纳入影响压缩结果的全部配置，避免不同参数互串缓存）"""
        if config is not None:
            content = (
                f"{text}:{config.strategy.value}"
                f":{config.target_ratio}:{config.max_tokens}"
                f":{config.preserve_keywords}"
            )
        else:
            content = f"{text}:default"
        if query:
            content = f"{content}:q={query}"
        return hashlib.md5(content.encode()).hexdigest()

    def _estimate_tokens(self, text: str) -> int:
        """估算 token 数"""
        return estimate_tokens(text)

    def clear_cache(self):
        """清空缓存"""
        self._cache_manager.clear()

    def get_cache_size(self) -> int:
        """获取缓存大小"""
        return self._cache_manager.get_stats().size

    def get_cache_stats(self) -> dict[str, Any]:
        """获取缓存统计"""
        return self._cache_manager.get_stats().to_dict()


# ==================== 工厂类 ====================

class ContextCompressorFactory:
    """
    上下文压缩器工厂

    用于创建压缩器实例。

    设计模式：工厂模式 - 统一创建逻辑，便于管理

    使用示例：
        compressor = ContextCompressorFactory.create(CompressionStrategyType.EXTRACTIVE)
        result = await compressor.compress("长文本...")
    """

    @staticmethod
    def create(
        strategy_type: CompressionStrategyType,
        **kwargs
    ) -> ContextCompressor:
        """
        创建压缩器实例

        Args:
            strategy_type: 压缩策略类型
            **kwargs: 传递给策略的参数

        Returns:
            压缩器实例
        """
        return ContextCompressor(
            strategy=strategy_type.value,
            **kwargs
        )

    @staticmethod
    def create_with_llm(
        strategy_type: CompressionStrategyType,
        llm,
        **kwargs
    ) -> ContextCompressor:
        """
        创建带 LLM 的压缩器实例

        Args:
            strategy_type: 压缩策略类型
            llm: LLM 实例
            **kwargs: 传递给策略的参数

        Returns:
            压缩器实例
        """
        return ContextCompressor(
            strategy=strategy_type.value,
            llm=llm,
            **kwargs
        )


# ==================== 全局实例 ====================

_compressor: ContextCompressor | None = None


def get_compressor(
    strategy_type: CompressionStrategyType = CompressionStrategyType.EXTRACTIVE,
    **kwargs
) -> ContextCompressor:
    """
    获取全局压缩器实例

    Args:
        strategy_type: 压缩策略类型

    Returns:
        压缩器实例
    """
    global _compressor
    if _compressor is None:
        _compressor = ContextCompressorFactory.create(strategy_type, **kwargs)
    return _compressor


def reset_compressor():
    """重置全局压缩器实例"""
    global _compressor
    _compressor = None
