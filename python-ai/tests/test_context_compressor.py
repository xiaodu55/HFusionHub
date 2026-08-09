"""
ContextCompressor 单元测试

测试上下文压缩器的所有功能：
- 数据模型：CompressionResult, CompressionConfig
- 抽取式压缩：ExtractiveCompressionStrategy
- 生成式压缩：AbstractiveCompressionStrategy
- 混合压缩：HybridCompressionStrategy
- 递归压缩：RecursiveCompressionStrategy
- 主类：ContextCompressor
- 工厂类：ContextCompressorFactory
- 全局实例管理

作者：Claude
日期：2026-07-22
"""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.rag.context_compressor import (
    AbstractiveCompressionStrategy,
    CompressionConfig,
    CompressionResult,
    CompressionStatus,
    CompressionStrategyType,
    ContextCompressor,
    ContextCompressorFactory,
    ExtractiveCompressionStrategy,
    HybridCompressionStrategy,
    RecursiveCompressionStrategy,
    get_compressor,
    reset_compressor,
)

# ==================== 数据模型测试 ====================

class TestCompressionResult:
    """CompressionResult 数据模型测试"""

    def test_creation(self):
        """测试创建 CompressionResult"""
        result = CompressionResult(
            original_text="这是一段测试文本",
            compressed_text="测试文本",
            original_tokens=10,
            compressed_tokens=5,
            compression_ratio=0.5,
            strategy_used="extractive",
            key_phrases=["测试"],
            summary="摘要",
        )

        assert result.original_text == "这是一段测试文本"
        assert result.compressed_text == "测试文本"
        assert result.original_tokens == 10
        assert result.compressed_tokens == 5
        assert result.compression_ratio == 0.5
        assert result.strategy_used == "extractive"
        assert result.key_phrases == ["测试"]
        assert result.summary == "摘要"
        assert result.status == CompressionStatus.COMPLETED

    def test_to_dict(self):
        """测试 to_dict 方法"""
        result = CompressionResult(
            original_text="测试文本内容",
            compressed_text="压缩内容",
            original_tokens=10,
            compressed_tokens=5,
            compression_ratio=0.5,
            strategy_used="extractive",
        )

        d = result.to_dict()
        assert d["compressed_text"] == "压缩内容"
        assert d["original_tokens"] == 10
        assert d["compressed_tokens"] == 5
        assert d["compression_ratio"] == 0.5
        assert d["strategy_used"] == "extractive"
        assert d["status"] == "completed"

    def test_from_dict(self):
        """测试 from_dict 方法"""
        d = {
            "original_text": "原始文本",
            "compressed_text": "压缩文本",
            "original_tokens": 100,
            "compressed_tokens": 50,
            "compression_ratio": 0.5,
            "strategy_used": "extractive",
            "key_phrases": ["关键"],
            "status": "completed",
        }

        result = CompressionResult.from_dict(d)
        assert result.original_text == "原始文本"
        assert result.compressed_text == "压缩文本"
        assert result.original_tokens == 100
        assert result.compressed_tokens == 50
        assert result.compression_ratio == 0.5
        assert result.key_phrases == ["关键"]


class TestCompressionConfig:
    """CompressionConfig 数据模型测试"""

    def test_creation_with_defaults(self):
        """测试使用默认值创建 CompressionConfig"""
        config = CompressionConfig()

        assert config.strategy == CompressionStrategyType.EXTRACTIVE
        assert config.target_ratio == 0.5
        assert config.max_tokens is None
        assert config.preserve_keywords is None
        assert config.language == "zh"
        assert config.min_sentence_length == 10

    def test_creation_with_custom_values(self):
        """测试使用自定义值创建 CompressionConfig"""
        config = CompressionConfig(
            strategy=CompressionStrategyType.ABSTRACTIVE,
            target_ratio=0.3,
            max_tokens=1000,
            preserve_keywords=["Python", "AI"],
            language="en",
            min_sentence_length=5,
        )

        assert config.strategy == CompressionStrategyType.ABSTRACTIVE
        assert config.target_ratio == 0.3
        assert config.max_tokens == 1000
        assert config.preserve_keywords == ["Python", "AI"]
        assert config.language == "en"
        assert config.min_sentence_length == 5


# ==================== 抽取式压缩策略测试 ====================

class TestExtractiveCompressionStrategy:
    """ExtractiveCompressionStrategy 测试"""

    def test_creation(self):
        """测试创建策略实例"""
        strategy = ExtractiveCompressionStrategy()
        assert strategy.name == "extractive"

    def test_estimate_tokens_chinese(self):
        """测试估算中文 token 数"""
        strategy = ExtractiveCompressionStrategy()
        tokens = strategy.estimate_tokens("这是一段中文测试文本")
        assert tokens == 10

    def test_estimate_tokens_english(self):
        """测试估算英文 token 数"""
        strategy = ExtractiveCompressionStrategy()
        tokens = strategy.estimate_tokens("This is an English test text")
        assert tokens == 6

    def test_estimate_tokens_mixed(self):
        """测试估算混合 token 数"""
        strategy = ExtractiveCompressionStrategy()
        tokens = strategy.estimate_tokens("这是中文 This is English")
        assert tokens == 4 + 3  # 4 Chinese chars + 3 English words (This, is, English)

    @pytest.mark.asyncio
    async def test_compress_simple_text(self):
        """测试压缩简单文本"""
        strategy = ExtractiveCompressionStrategy()
        config = CompressionConfig(target_ratio=0.5)

        text = "Python是一种流行的编程语言。它广泛应用于人工智能领域。Python语法简洁易学。"
        result = await strategy.compress(text, config)

        assert result.status == CompressionStatus.COMPLETED
        assert result.strategy_used == "extractive"
        assert result.compressed_tokens <= result.original_tokens
        assert result.compression_ratio <= 1.0

    @pytest.mark.asyncio
    async def test_compress_empty_text(self):
        """测试压缩空文本"""
        strategy = ExtractiveCompressionStrategy()
        result = await strategy.compress("")

        assert result.status == CompressionStatus.COMPLETED
        assert result.compressed_text == ""
        assert result.compression_ratio == 1.0

    @pytest.mark.asyncio
    async def test_compress_preserves_key_phrases(self):
        """测试压缩保留关键短语"""
        strategy = ExtractiveCompressionStrategy()
        text = "Python 3.9版本发布了。API文档更新了。"
        result = await strategy.compress(text)

        # 应该提取出一些关键短语
        assert len(result.key_phrases) > 0

    def test_split_sentences(self):
        """测试分句功能"""
        strategy = ExtractiveCompressionStrategy()
        sentences = strategy._split_sentences("第一句。第二句？第三句！")

        assert len(sentences) == 3
        assert sentences[0] == "第一句。"
        assert sentences[1] == "第二句。"  # 分句后统一添加句号
        assert sentences[2] == "第三句。"

    def test_query_signal_raises_relevant_sentence_score(self):
        """A2：query 重叠信号提升与问题相关的低事实密度句子得分。

        纯事实密度评分对"与问题直接相关但不含数字/日期"的句子是盲的，
        压缩预算紧张时它们会被无差别丢掉。
        """
        strategy = ExtractiveCompressionStrategy()
        sentences = [
            "本段介绍售后政策的适用范围与历史沿革背景说明。",   # 与问题无关
            "售后政策覆盖全国 128 个城市共 3500 个网点。",      # 事实密集
            "音箱 S1 支持自定义唤醒词与唤醒灵敏度调节。",        # 相关但零事实标记
            "固件自 2024 年起累计更新 26 个版本。",             # 事实密集
        ]
        text = "".join(sentences)
        query = "音箱 S1 怎么设置自定义唤醒词"

        scores_no_query = strategy.rank_sentences(sentences, text)
        scores_with_query = strategy.rank_sentences(sentences, text, query=query)

        relevant = 2
        assert scores_with_query[relevant] > scores_no_query[relevant]
        # 机制有界：query 命中满分的句子不应超过其权重上限（0.30 + 其余项）
        assert max(scores_with_query) <= 1.0 + 1e-9

    def test_no_query_keeps_legacy_weights(self):
        """query 缺省/为空时退回历史权重分布，行为向后兼容。"""
        strategy = ExtractiveCompressionStrategy()
        sentences = ["第一句包含 2024 年的数据。", "第二句是普通描述性内容。"]
        text = "".join(sentences)
        assert (strategy.rank_sentences(sentences, text)
                == strategy.rank_sentences(sentences, text, query=None)
                == strategy.rank_sentences(sentences, text, query=""))

    @pytest.mark.asyncio
    async def test_compress_passes_query_to_scorer(self):
        """compress(query=...) 端到端：query 参与句子选择（文本需超过短文本
        守卫阈值，否则 compress 直接原样返回）。"""
        strategy = ExtractiveCompressionStrategy()
        config = CompressionConfig(target_ratio=0.25)
        relevant = "音箱 S1 支持自定义唤醒词与唤醒灵敏度调节。"
        # 长填充句：与问题无关、零事实标记，把合并文本推过守卫阈值
        fillers = [
            f"本段第{i}节介绍售后政策的适用范围与历史沿革背景说明，以及服务承诺的整体框架与边界。"
            for i in range(1, 17)
        ]
        text = (
            fillers[0] + fillers[1]
            + "售后政策覆盖全国 128 个城市共 3500 个网点。"
            + relevant
            + "固件自 2024 年起累计更新 26 个版本。"
            + "".join(fillers[2:])
        )
        assert len(text) > 600  # 确认越过短文本守卫

        result = await strategy.compress(text, config, query="音箱 S1 唤醒词")
        assert result.status == CompressionStatus.COMPLETED
        assert relevant in result.compressed_text


# ==================== 生成式压缩策略测试 ====================

class TestAbstractiveCompressionStrategy:
    """AbstractiveCompressionStrategy 测试"""

    def test_creation_without_llm(self):
        """测试创建策略实例（无 LLM）"""
        strategy = AbstractiveCompressionStrategy()
        assert strategy.name == "abstractive"
        assert strategy.llm is None

    def test_creation_with_llm(self):
        """测试创建策略实例（带 LLM）"""
        mock_llm = MagicMock()
        strategy = AbstractiveCompressionStrategy(llm=mock_llm)
        assert strategy.name == "abstractive"
        assert strategy.llm == mock_llm

    @pytest.mark.asyncio
    async def test_compress_without_llm_fallback(self):
        """测试无 LLM 时降级到抽取式压缩"""
        strategy = AbstractiveCompressionStrategy()
        text = "Python是一种流行的编程语言。它广泛应用于人工智能领域。"
        result = await strategy.compress(text)

        # 应该降级到抽取式压缩
        assert result.status == CompressionStatus.COMPLETED
        assert result.compressed_tokens <= result.original_tokens

    @pytest.mark.asyncio
    async def test_compress_with_mock_llm(self):
        """测试使用 Mock LLM 压缩"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Python是流行编程语言，广泛用于AI。"
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        strategy = AbstractiveCompressionStrategy(llm=mock_llm)
        text = "Python是一种非常流行的编程语言。它被广泛应用于人工智能领域。"
        config = CompressionConfig(target_ratio=0.5)

        result = await strategy.compress(text, config)

        assert result.status == CompressionStatus.COMPLETED
        assert result.strategy_used == "abstractive"
        assert result.summary == "Python是流行编程语言，广泛用于AI。"


# ==================== 混合压缩策略测试 ====================

class TestHybridCompressionStrategy:
    """HybridCompressionStrategy 测试"""

    def test_creation_without_llm(self):
        """测试创建策略实例（无 LLM）"""
        strategy = HybridCompressionStrategy()
        assert strategy.name == "hybrid"
        assert strategy.llm is None

    def test_creation_with_llm(self):
        """测试创建策略实例（带 LLM）"""
        mock_llm = MagicMock()
        strategy = HybridCompressionStrategy(llm=mock_llm)
        assert strategy.name == "hybrid"
        assert strategy.llm == mock_llm

    @pytest.mark.asyncio
    async def test_compress_without_llm(self):
        """测试无 LLM 时只使用抽取式"""
        strategy = HybridCompressionStrategy()
        text = "Python是一种流行的编程语言。它广泛应用于人工智能领域。"
        result = await strategy.compress(text)

        assert result.status == CompressionStatus.COMPLETED
        assert result.strategy_used == "hybrid"
        assert result.compressed_tokens <= result.original_tokens

    @pytest.mark.asyncio
    async def test_compress_with_mock_llm(self):
        """测试使用 Mock LLM 压缩"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Python是流行编程语言，广泛用于AI。"
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        strategy = HybridCompressionStrategy(llm=mock_llm)
        text = "Python是一种非常流行的编程语言。它被广泛应用于人工智能领域。"
        config = CompressionConfig(target_ratio=0.5)

        result = await strategy.compress(text, config)

        assert result.status == CompressionStatus.COMPLETED
        assert result.strategy_used == "hybrid"
        assert result.summary == "Python是流行编程语言，广泛用于AI。"


# ==================== 递归压缩策略测试 ====================

class TestRecursiveCompressionStrategy:
    """RecursiveCompressionStrategy 测试"""

    def test_creation(self):
        """测试创建策略实例"""
        strategy = RecursiveCompressionStrategy()
        assert strategy.name == "recursive"

    @pytest.mark.asyncio
    async def test_compress_with_max_tokens(self):
        """测试使用 max_tokens 压缩 — 长文本应发生实际压缩"""
        strategy = RecursiveCompressionStrategy()
        config = CompressionConfig(max_tokens=120)

        text = (
            "Python是一种流行的编程语言。"
            "数据分析是Python的核心应用场景之一。"
            "机器学习需要大量的训练数据和计算资源。"
            "深度学习在图像识别领域取得了突破性进展。"
            "自然语言处理是人工智能的重要分支。"
            "Web开发框架如Django和Flask广受欢迎。"
            "科学计算库NumPy和SciPy功能强大。"
            "数据可视化工具Matplotlib使用方便。"
        ) * 30
        result = await strategy.compress(text, config)

        assert result.status == CompressionStatus.COMPLETED
        assert result.compressed_tokens < result.original_tokens, "长文本应该发生压缩"

    @pytest.mark.asyncio
    async def test_compress_already_meets_target(self):
        """测试已经满足目标时直接返回"""
        strategy = RecursiveCompressionStrategy()
        config = CompressionConfig(max_tokens=1000)

        text = "短文本"
        result = await strategy.compress(text, config)

        assert result.status == CompressionStatus.COMPLETED
        assert result.compressed_text == text
        assert result.compression_ratio == 1.0


# ==================== 主类测试 ====================

class TestContextCompressor:
    """ContextCompressor 主类测试"""

    def test_creation_default(self):
        """测试默认创建"""
        compressor = ContextCompressor()
        assert compressor.cache_enabled is True
        assert compressor.cache_ttl == 3600

    def test_creation_custom_strategy(self):
        """测试自定义策略创建"""
        strategy = ExtractiveCompressionStrategy()
        compressor = ContextCompressor(strategy=strategy)
        assert compressor.strategy == strategy

    def test_creation_string_strategy(self):
        """测试字符串策略创建"""
        compressor = ContextCompressor(strategy="extractive")
        assert isinstance(compressor.strategy, ExtractiveCompressionStrategy)

    def test_creation_no_cache(self):
        """测试禁用缓存"""
        compressor = ContextCompressor(cache_enabled=False)
        assert compressor.cache_enabled is False

    @pytest.mark.asyncio
    async def test_compress_simple(self):
        """测试简单压缩"""
        compressor = ContextCompressor(cache_enabled=False)
        text = "Python是一种流行的编程语言。它广泛应用于人工智能领域。"
        result = await compressor.compress(text)

        assert result.status == CompressionStatus.COMPLETED
        assert result.compressed_tokens <= result.original_tokens

    @pytest.mark.asyncio
    async def test_compress_with_config(self):
        """测试使用配置压缩"""
        compressor = ContextCompressor(cache_enabled=False)
        config = CompressionConfig(target_ratio=0.3)
        text = (
            "Python是一种流行的编程语言。它广泛应用于人工智能领域。Python语法简洁易学。"
            + "数据分析是Python的核心应用场景。" * 30
            + "机器学习、深度学习、自然语言处理、计算机视觉都是人工智能的重要分支。"
        )
        result = await compressor.compress(text, config)

        assert result.status == CompressionStatus.COMPLETED
        assert result.compression_ratio < 1.0  # 长文本应发生实际压缩

    @pytest.mark.asyncio
    async def test_compress_batch(self):
        """测试批量压缩"""
        compressor = ContextCompressor(cache_enabled=False)
        texts = [
            "Python是一种流行的编程语言。",
            "Java是一种广泛使用的编程语言。",
            "JavaScript是Web开发的核心语言。",
        ]

        results = await compressor.compress_batch(texts)

        assert len(results) == 3
        for result in results:
            assert result.status == CompressionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_cache(self):
        """测试缓存功能"""
        compressor = ContextCompressor(cache_enabled=True, cache_ttl=3600)
        text = "测试缓存文本"
        config = CompressionConfig()

        # 第一次压缩
        result1 = await compressor.compress(text, config)
        assert compressor.get_cache_size() == 1

        # 第二次压缩，应该使用缓存
        result2 = await compressor.compress(text, config)
        assert result1.compressed_text == result2.compressed_text
        assert compressor.get_cache_size() == 1

    def test_clear_cache(self):
        """测试清空缓存"""
        compressor = ContextCompressor(cache_enabled=True)
        compressor._cache["test"] = (MagicMock(), time.time())

        compressor.clear_cache()
        assert compressor.get_cache_size() == 0


# ==================== 工厂类测试 ====================

class TestContextCompressorFactory:
    """ContextCompressorFactory 测试"""

    def test_create_extractive(self):
        """测试创建抽取式压缩器"""
        compressor = ContextCompressorFactory.create(
            CompressionStrategyType.EXTRACTIVE
        )
        assert isinstance(compressor.strategy, ExtractiveCompressionStrategy)

    def test_create_abstractive(self):
        """测试创建生成式压缩器"""
        compressor = ContextCompressorFactory.create(
            CompressionStrategyType.ABSTRACTIVE
        )
        assert isinstance(compressor.strategy, AbstractiveCompressionStrategy)

    def test_create_hybrid(self):
        """测试创建混合压缩器"""
        compressor = ContextCompressorFactory.create(
            CompressionStrategyType.HYBRID
        )
        assert isinstance(compressor.strategy, HybridCompressionStrategy)

    def test_create_recursive(self):
        """测试创建递归压缩器"""
        compressor = ContextCompressorFactory.create(
            CompressionStrategyType.RECURSIVE
        )
        assert isinstance(compressor.strategy, RecursiveCompressionStrategy)

    def test_create_with_llm(self):
        """测试创建带 LLM 的压缩器"""
        mock_llm = MagicMock()
        compressor = ContextCompressorFactory.create_with_llm(
            CompressionStrategyType.ABSTRACTIVE,
            llm=mock_llm
        )
        assert isinstance(compressor.strategy, AbstractiveCompressionStrategy)
        assert compressor.strategy.llm == mock_llm


# ==================== 全局实例测试 ====================

class TestGlobalInstance:
    """全局实例管理测试"""

    def setup_method(self):
        """每个测试前重置"""
        reset_compressor()

    def test_get_compressor(self):
        """测试获取全局压缩器"""
        compressor = get_compressor()
        assert compressor is not None
        assert isinstance(compressor, ContextCompressor)

    def test_singleton(self):
        """测试单例模式"""
        compressor1 = get_compressor()
        compressor2 = get_compressor()
        assert compressor1 is compressor2

    def test_reset(self):
        """测试重置"""
        compressor1 = get_compressor()
        reset_compressor()
        compressor2 = get_compressor()
        assert compressor1 is not compressor2


# ==================== 集成测试 ====================

class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_end_to_end_extractive(self):
        """端到端测试：抽取式压缩"""
        compressor = ContextCompressorFactory.create(
            CompressionStrategyType.EXTRACTIVE
        )

        text = (
            "Python是一种广泛使用的高级编程语言。它由Guido van Rossum于1991年创建。"
            + "Python的设计哲学强调代码的可读性和简洁性。Python支持多种编程范式，"
            + "包括面向对象、函数式和过程式编程。Python广泛应用于Web开发、数据分析、"
            + "人工智能、科学计算等领域。"
        ) * 5

        config = CompressionConfig(target_ratio=0.5, language="zh")
        result = await compressor.compress(text, config)

        assert result.status == CompressionStatus.COMPLETED
        assert result.compression_ratio < 1.0, f"长文本应发生压缩，ratio={result.compression_ratio:.2f}"
        print(f"\n抽取式压缩：{result.original_tokens} -> {result.compressed_tokens} tokens")
        print(f"压缩率：{result.compression_ratio:.2%}")

    @pytest.mark.asyncio
    async def test_end_to_end_recursive(self):
        """端到端测试：递归压缩"""
        compressor = ContextCompressorFactory.create(
            CompressionStrategyType.RECURSIVE
        )

        text = (
            "Python是一种广泛使用的高级编程语言。它由Guido van Rossum于1991年创建。"
            + "Python的设计哲学强调代码的可读性和简洁性。Python支持多种编程范式，"
            + "包括面向对象、函数式和过程式编程。Python广泛应用于Web开发、数据分析、"
            + "人工智能、科学计算等领域。"
        ) * 10

        config = CompressionConfig(max_tokens=200)
        result = await compressor.compress(text, config)

        assert result.status == CompressionStatus.COMPLETED
        assert result.compressed_tokens < result.original_tokens, "长文本应发生压缩"
        print(f"\n递归压缩：{result.original_tokens} -> {result.compressed_tokens} tokens")

    @pytest.mark.asyncio
    async def test_short_text_is_preserved(self):
        """短文本不应被压缩（防止丢失关键事实）。"""
        compressor = ContextCompressorFactory.create(
            CompressionStrategyType.EXTRACTIVE
        )
        short = "关键数据：2024年Q1营收增长42%，净利润达到3.5亿元。"
        config = CompressionConfig(target_ratio=0.5, language="zh")
        result = await compressor.compress(short, config)

        assert result.status == CompressionStatus.COMPLETED
        assert result.compressed_text == short, "短文本应原样保留"
        assert result.compression_ratio == 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
