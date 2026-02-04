"""
MultimodalRAG 单元测试

测试多模态检索增强生成模块的所有组件
"""

import os
import tempfile
import pytest
import asyncio
from typing import List, Dict, Any
from unittest.mock import MagicMock, AsyncMock, patch

from app.core.rag.multimodal_rag import (
    # 枚举
    ImageEmbeddingModel,
    ModalityType,
    ImageSource,
    ChunkType,
    # 数据模型
    ImageInfo,
    ImageEmbedding,
    MultimodalChunk,
    MultimodalSearchResult,
    MultimodalSearchResponse,
    MultimodalConfig,
    # 图片嵌入器
    BaseImageEmbedder,
    CLIPImageEmbedder,
    ChineseCLIPImageEmbedder,
    RandomImageEmbedder,
    ImageEmbedderFactory,
    # 文档解析器
    MultimodalDocumentParser,
    # 图片分块器
    ImageChunker,
    # 跨模态检索器
    CrossModalRetriever,
    # 主类
    MultimodalRAG,
    MultimodalRAGFactory,
    get_multimodal_rag,
    reset_multimodal_rag,
)


# ============================================================
# 数据模型测试
# ============================================================

class TestImageInfo:
    """ImageInfo 数据模型测试"""

    def test_create_image_info(self):
        """测试创建 ImageInfo"""
        info = ImageInfo(
            image_id="img_001",
            source=ImageSource.PDF,
            file_path="/path/to/image.png",
            description="测试图片",
            page_number=1,
        )

        assert info.image_id == "img_001"
        assert info.source == ImageSource.PDF
        assert info.file_path == "/path/to/image.png"
        assert info.description == "测试图片"
        assert info.page_number == 1

    def test_image_info_to_dict(self):
        """测试 ImageInfo.to_dict"""
        info = ImageInfo(
            image_id="img_001",
            source=ImageSource.DOCX,
            url="https://example.com/image.png",
        )

        data = info.to_dict()
        assert data["image_id"] == "img_001"
        assert data["source"] == "docx"
        assert data["url"] == "https://example.com/image.png"

    def test_image_info_default_values(self):
        """测试 ImageInfo 默认值"""
        info = ImageInfo(image_id="img_001", source=ImageSource.LOCAL)

        assert info.file_path == ""
        assert info.url == ""
        assert info.base64_data == ""
        assert info.description == ""
        assert info.page_number is None
        assert info.metadata == {}


class TestImageEmbedding:
    """ImageEmbedding 数据模型测试"""

    def test_create_image_embedding(self):
        """测试创建 ImageEmbedding"""
        embedding = ImageEmbedding(
            image_id="img_001",
            embedding=[0.1, 0.2, 0.3],
            model_name="clip",
            dimension=3,
        )

        assert embedding.image_id == "img_001"
        assert embedding.embedding == [0.1, 0.2, 0.3]
        assert embedding.model_name == "clip"
        assert embedding.dimension == 3

    def test_image_embedding_to_dict(self):
        """测试 ImageEmbedding.to_dict"""
        embedding = ImageEmbedding(
            image_id="img_001",
            embedding=[0.1, 0.2],
            model_name="clip",
            dimension=2,
        )

        data = embedding.to_dict()
        assert data["image_id"] == "img_001"
        assert data["embedding"] == [0.1, 0.2]
        assert "timestamp" in data


class TestMultimodalChunk:
    """MultimodalChunk 数据模型测试"""

    def test_create_text_chunk(self):
        """测试创建文本分块"""
        chunk = MultimodalChunk(
            chunk_id="chunk_001",
            document_id="doc_001",
            index=0,
            chunk_type=ChunkType.TEXT_ONLY,
            content="这是一段文本",
        )

        assert chunk.chunk_id == "chunk_001"
        assert chunk.chunk_type == ChunkType.TEXT_ONLY
        assert chunk.content == "这是一段文本"
        assert chunk.image_id == ""

    def test_create_image_chunk(self):
        """测试创建图片分块"""
        chunk = MultimodalChunk(
            chunk_id="chunk_002",
            document_id="doc_001",
            index=1,
            chunk_type=ChunkType.IMAGE_ONLY,
            image_id="img_001",
            image_path="/path/to/image.png",
        )

        assert chunk.chunk_type == ChunkType.IMAGE_ONLY
        assert chunk.image_id == "img_001"
        assert chunk.content == ""

    def test_chunk_to_dict(self):
        """测试 MultimodalChunk.to_dict"""
        chunk = MultimodalChunk(
            chunk_id="chunk_001",
            document_id="doc_001",
            index=0,
            chunk_type=ChunkType.TEXT_IMAGE,
            content="文本内容",
            image_id="img_001",
        )

        data = chunk.to_dict()
        assert data["chunk_id"] == "chunk_001"
        assert data["chunk_type"] == "text_image"
        assert data["image_id"] == "img_001"


class TestMultimodalSearchResult:
    """MultimodalSearchResult 数据模型测试"""

    def test_create_search_result(self):
        """测试创建搜索结果"""
        result = MultimodalSearchResult(
            result_id="result_001",
            score=0.85,
            chunk_type=ChunkType.TEXT_ONLY,
            content="搜索结果内容",
        )

        assert result.result_id == "result_001"
        assert result.score == 0.85
        assert result.modality == ModalityType.TEXT

    def test_search_result_to_dict(self):
        """测试 MultimodalSearchResult.to_dict"""
        result = MultimodalSearchResult(
            result_id="result_001",
            score=0.9,
            chunk_type=ChunkType.IMAGE_ONLY,
            image_id="img_001",
            modality=ModalityType.IMAGE,
        )

        data = result.to_dict()
        assert data["score"] == 0.9
        assert data["modality"] == "image"


class TestMultimodalSearchResponse:
    """MultimodalSearchResponse 数据模型测试"""

    def test_create_search_response(self):
        """测试创建搜索响应"""
        results = [
            MultimodalSearchResult(
                result_id="r1", score=0.9, chunk_type=ChunkType.TEXT_ONLY
            ),
            MultimodalSearchResult(
                result_id="r2", score=0.8, chunk_type=ChunkType.IMAGE_ONLY
            ),
        ]

        response = MultimodalSearchResponse(
            query="测试查询",
            results=results,
            total_count=2,
            text_results_count=1,
            image_results_count=1,
            search_time_ms=15.5,
        )

        assert response.query == "测试查询"
        assert response.total_count == 2
        assert response.text_results_count == 1
        assert response.image_results_count == 1

    def test_search_response_to_dict(self):
        """测试 MultimodalSearchResponse.to_dict"""
        response = MultimodalSearchResponse(
            query="test",
            results=[],
            total_count=0,
            text_results_count=0,
            image_results_count=0,
            search_time_ms=0,
        )

        data = response.to_dict()
        assert data["query"] == "test"
        assert data["results"] == []


class TestMultimodalConfig:
    """MultimodalConfig 配置测试"""

    def test_default_config(self):
        """测试默认配置"""
        config = MultimodalConfig()

        assert config.image_embedding_model == ImageEmbeddingModel.RANDOM
        assert config.image_embedding_dimension == 512
        assert config.text_embedding_dimension == 1024
        assert config.text_weight == 0.6
        assert config.image_weight == 0.4

    def test_custom_config(self):
        """测试自定义配置"""
        config = MultimodalConfig(
            image_embedding_model=ImageEmbeddingModel.OPENAI_CLIP,
            image_embedding_dimension=768,
            text_weight=0.7,
            image_weight=0.3,
        )

        assert config.image_embedding_model == ImageEmbeddingModel.OPENAI_CLIP
        assert config.image_embedding_dimension == 768
        assert config.text_weight == 0.7

    def test_config_to_dict(self):
        """测试配置转字典"""
        config = MultimodalConfig()
        data = config.to_dict()

        assert "image_embedding_model" in data
        assert "text_weight" in data
        assert data["image_embedding_model"] == "random"


# ============================================================
# 枚举测试
# ============================================================

class TestEnums:
    """枚举定义测试"""

    def test_image_embedding_model(self):
        """测试 ImageEmbeddingModel 枚举"""
        assert ImageEmbeddingModel.OPENAI_CLIP == "openai_clip"
        assert ImageEmbeddingModel.CHINESE_CLIP == "chinese_clip"
        assert ImageEmbeddingModel.SIGLIP == "siglip"
        assert ImageEmbeddingModel.RANDOM == "random"

    def test_modality_type(self):
        """测试 ModalityType 枚举"""
        assert ModalityType.TEXT == "text"
        assert ModalityType.IMAGE == "image"
        assert ModalityType.HYBRID == "hybrid"

    def test_image_source(self):
        """测试 ImageSource 枚举"""
        assert ImageSource.PDF == "pdf"
        assert ImageSource.DOCX == "docx"
        assert ImageSource.MARKDOWN == "markdown"
        assert ImageSource.URL == "url"
        assert ImageSource.LOCAL == "local"

    def test_chunk_type(self):
        """测试 ChunkType 枚举"""
        assert ChunkType.TEXT_ONLY == "text_only"
        assert ChunkType.IMAGE_ONLY == "image_only"
        assert ChunkType.TEXT_IMAGE == "text_image"


# ============================================================
# 图片嵌入器测试
# ============================================================

class TestRandomImageEmbedder:
    """RandomImageEmbedder 测试"""

    @pytest.mark.asyncio
    async def test_embed_image(self):
        """测试随机图片嵌入"""
        embedder = RandomImageEmbedder(dimension=128)

        embedding = await embedder.embed_image("/fake/path.png")

        assert len(embedding) == 128
        # 检查是否归一化
        norm = sum(x**2 for x in embedding) ** 0.5
        assert abs(norm - 1.0) < 0.01

    @pytest.mark.asyncio
    async def test_embed_image_from_bytes(self):
        """测试从字节数据嵌入"""
        embedder = RandomImageEmbedder(dimension=64)

        embedding = await embedder.embed_image_from_bytes(b"fake image data")

        assert len(embedding) == 64

    @pytest.mark.asyncio
    async def test_embed_text(self):
        """测试文本嵌入"""
        embedder = RandomImageEmbedder(dimension=64)

        embedding = await embedder.embed_text("测试文本")

        assert len(embedding) == 64

    @pytest.mark.asyncio
    async def test_embed_batch(self):
        """测试批量嵌入"""
        embedder = RandomImageEmbedder(dimension=64)

        embeddings = await embedder.embed_batch([
            "/path/1.png",
            "/path/2.png",
            "/path/3.png",
        ])

        assert len(embeddings) == 3
        for emb in embeddings:
            assert len(emb) == 64


class TestCLIPImageEmbedder:
    """CLIPImageEmbedder 测试"""

    def test_init(self):
        """测试初始化"""
        embedder = CLIPImageEmbedder(
            model_name="ViT-B/32",
            device="cpu",
            dimension=512,
        )

        assert embedder.model_name == "ViT-B/32"
        assert embedder.device == "cpu"
        assert embedder.dimension == 512

    @pytest.mark.asyncio
    async def test_embed_image_fallback(self):
        """测试嵌入图片（CLIP 未加载时降级为随机向量）"""
        embedder = CLIPImageEmbedder(dimension=128)

        # 由于 CLIP 模型可能未安装，应该降级为随机向量
        embedding = await embedder.embed_image("/fake/path.png")

        assert len(embedding) == 128


class TestImageEmbedderFactory:
    """ImageEmbedderFactory 测试"""

    def test_create_random(self):
        """测试创建随机嵌入器"""
        embedder = ImageEmbedderFactory.create(
            ImageEmbeddingModel.RANDOM,
            dimension=256,
        )

        assert isinstance(embedder, RandomImageEmbedder)

    def test_create_clip(self):
        """测试创建 CLIP 嵌入器"""
        embedder = ImageEmbedderFactory.create(
            ImageEmbeddingModel.OPENAI_CLIP,
            dimension=512,
        )

        assert isinstance(embedder, CLIPImageEmbedder)

    def test_create_chinese_clip(self):
        """测试创建 Chinese-CLIP 嵌入器"""
        embedder = ImageEmbedderFactory.create(
            ImageEmbeddingModel.CHINESE_CLIP,
            dimension=512,
        )

        assert isinstance(embedder, ChineseCLIPImageEmbedder)

    def test_create_default(self):
        """测试默认创建"""
        embedder = ImageEmbedderFactory.create()

        assert isinstance(embedder, RandomImageEmbedder)


# ============================================================
# 多模态文档解析器测试
# ============================================================

class TestMultimodalDocumentParser:
    """MultimodalDocumentParser 测试"""

    def test_init(self):
        """测试初始化"""
        parser = MultimodalDocumentParser()
        assert parser.config is not None

    def test_parse_unsupported_format(self):
        """测试解析不支持的格式"""
        parser = MultimodalDocumentParser()

        chunks = parser.parse("/fake/file.xyz", "doc_001")

        assert chunks == []

    def test_parse_markdown(self):
        """测试解析 Markdown"""
        parser = MultimodalDocumentParser()

        # 创建临时 Markdown 文件
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write("# 标题\n\n这是第一段。\n\n这是第二段。\n\n")
            temp_path = f.name

        try:
            chunks = parser.parse(temp_path, "doc_001")

            # 应该有文本块
            assert len(chunks) > 0
            assert any(c.chunk_type == ChunkType.TEXT_ONLY for c in chunks)
        finally:
            os.unlink(temp_path)

    def test_parse_markdown_with_images(self):
        """测试解析带图片的 Markdown"""
        parser = MultimodalDocumentParser()

        # 创建临时 Markdown 文件和图片
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write("# 标题\n\n这是文本。\n\n![图片描述](test.png)\n\n")
            temp_path = f.name

        # 创建一个假的图片文件
        img_path = os.path.join(os.path.dirname(temp_path), "test.png")
        with open(img_path, "wb") as f:
            f.write(b"fake png data")

        try:
            chunks = parser.parse(temp_path, "doc_001")

            # 应该有文本块和图片块
            text_chunks = [c for c in chunks if c.chunk_type == ChunkType.TEXT_ONLY]
            image_chunks = [c for c in chunks if c.chunk_type == ChunkType.IMAGE_ONLY]

            assert len(text_chunks) > 0
            assert len(image_chunks) > 0
        finally:
            os.unlink(temp_path)
            if os.path.exists(img_path):
                os.unlink(img_path)


# ============================================================
# 图片分块器测试
# ============================================================

class TestImageChunker:
    """ImageChunker 测试"""

    def test_init(self):
        """测试初始化"""
        chunker = ImageChunker()
        assert chunker.config is not None

    def test_chunk_empty(self):
        """测试空分块"""
        chunker = ImageChunker()

        result = chunker.chunk([], "doc_001")

        assert result == []

    def test_chunk_text_only(self):
        """测试仅文本分块"""
        chunker = ImageChunker()

        chunks = [
            MultimodalChunk(
                chunk_id="c1",
                document_id="doc_001",
                index=0,
                chunk_type=ChunkType.TEXT_ONLY,
                content="文本1",
            ),
            MultimodalChunk(
                chunk_id="c2",
                document_id="doc_001",
                index=1,
                chunk_type=ChunkType.TEXT_ONLY,
                content="文本2",
            ),
        ]

        result = chunker.chunk(chunks, "doc_001")

        assert len(result) == 2
        assert all(c.chunk_type == ChunkType.TEXT_ONLY for c in result)

    def test_chunk_with_images(self):
        """测试带图片的分块"""
        chunker = ImageChunker()

        chunks = [
            MultimodalChunk(
                chunk_id="c1",
                document_id="doc_001",
                index=0,
                chunk_type=ChunkType.TEXT_ONLY,
                content="这是图片前的文本",
            ),
            MultimodalChunk(
                chunk_id="c2",
                document_id="doc_001",
                index=1,
                chunk_type=ChunkType.IMAGE_ONLY,
                image_id="img_001",
                image_path="/path/to/image.png",
            ),
            MultimodalChunk(
                chunk_id="c3",
                document_id="doc_001",
                index=2,
                chunk_type=ChunkType.TEXT_ONLY,
                content="这是图片后的文本",
            ),
        ]

        result = chunker.chunk(chunks, "doc_001")

        # 图片块应该关联到最近的文本
        image_chunk = next(c for c in result if c.chunk_type == ChunkType.TEXT_IMAGE)
        assert image_chunk.surrounding_text == "这是图片前的文本"


# ============================================================
# 跨模态检索器测试
# ============================================================

class TestCrossModalRetriever:
    """CrossModalRetriever 测试"""

    @pytest.mark.asyncio
    async def test_search_empty(self):
        """测试空搜索"""
        embedder = RandomImageEmbedder(dimension=64)
        retriever = CrossModalRetriever(embedder)

        response = await retriever.search(
            query="测试查询",
            chunks=[],
            modality=ModalityType.HYBRID,
        )

        assert response.total_count == 0
        assert response.results == []

    @pytest.mark.asyncio
    async def test_search_text_only(self):
        """测试仅文本搜索"""
        embedder = RandomImageEmbedder(dimension=64)
        retriever = CrossModalRetriever(embedder)

        chunks = [
            MultimodalChunk(
                chunk_id="c1",
                document_id="doc_001",
                index=0,
                chunk_type=ChunkType.TEXT_ONLY,
                content="测试文本",
                text_embedding=[0.1] * 64,
            ),
        ]

        response = await retriever.search(
            query="测试查询",
            chunks=chunks,
            modality=ModalityType.TEXT,
        )

        assert response.text_results_count >= 0

    @pytest.mark.asyncio
    async def test_search_hybrid(self):
        """测试混合搜索"""
        embedder = RandomImageEmbedder(dimension=64)
        retriever = CrossModalRetriever(embedder)

        chunks = [
            MultimodalChunk(
                chunk_id="c1",
                document_id="doc_001",
                index=0,
                chunk_type=ChunkType.TEXT_ONLY,
                content="文本",
                text_embedding=[0.1] * 64,
            ),
            MultimodalChunk(
                chunk_id="c2",
                document_id="doc_001",
                index=1,
                chunk_type=ChunkType.IMAGE_ONLY,
                image_id="img_001",
                image_path="/fake/path.png",
            ),
        ]

        response = await retriever.search(
            query="测试",
            chunks=chunks,
            modality=ModalityType.HYBRID,
            top_k=5,
        )

        assert response.query == "测试"
        assert isinstance(response.results, list)


# ============================================================
# MultimodalRAG 主类测试
# ============================================================

class TestMultimodalRAG:
    """MultimodalRAG 主类测试"""

    def test_init(self):
        """测试初始化"""
        rag = MultimodalRAG()

        assert rag.config is not None
        assert rag.image_embedder is not None
        assert rag.document_parser is not None
        assert rag.retriever is not None

    def test_init_custom_config(self):
        """测试自定义配置初始化"""
        config = MultimodalConfig(
            image_embedding_model=ImageEmbeddingModel.RANDOM,
            text_weight=0.7,
        )

        rag = MultimodalRAG(config=config)

        assert rag.config.text_weight == 0.7

    @pytest.mark.asyncio
    async def test_search_empty(self):
        """测试空搜索"""
        rag = MultimodalRAG()

        response = await rag.search(query="测试查询")

        assert response.total_count == 0
        assert "No documents indexed" in response.metadata.get("error", "")

    @pytest.mark.asyncio
    async def test_search_with_document(self):
        """测试带文档搜索"""
        rag = MultimodalRAG()

        # 手动添加一些分块
        rag._document_chunks["doc_001"] = [
            MultimodalChunk(
                chunk_id="c1",
                document_id="doc_001",
                index=0,
                chunk_type=ChunkType.TEXT_ONLY,
                content="测试文本",
            ),
        ]

        response = await rag.search(
            query="测试",
            document_id="doc_001",
        )

        assert isinstance(response.results, list)

    def test_get_document_info(self):
        """测试获取文档信息"""
        rag = MultimodalRAG()

        rag._document_chunks["doc_001"] = [
            MultimodalChunk(
                chunk_id="c1",
                document_id="doc_001",
                index=0,
                chunk_type=ChunkType.TEXT_ONLY,
                content="文本",
            ),
            MultimodalChunk(
                chunk_id="c2",
                document_id="doc_001",
                index=1,
                chunk_type=ChunkType.IMAGE_ONLY,
                image_id="img_001",
            ),
        ]

        info = rag.get_document_info("doc_001")

        assert info is not None
        assert info["total_chunks"] == 2
        assert info["text_chunks"] == 1
        assert info["image_chunks"] == 1

    def test_get_document_info_not_found(self):
        """测试获取不存在的文档信息"""
        rag = MultimodalRAG()

        info = rag.get_document_info("nonexistent")

        assert info is None

    def test_clear_document(self):
        """测试清除文档"""
        rag = MultimodalRAG()

        rag._document_chunks["doc_001"] = [
            MultimodalChunk(
                chunk_id="c1",
                document_id="doc_001",
                index=0,
                chunk_type=ChunkType.TEXT_ONLY,
                content="文本",
            ),
        ]

        result = rag.clear_document("doc_001")

        assert result is True
        assert "doc_001" not in rag._document_chunks

    def test_clear_document_not_found(self):
        """测试清除不存在的文档"""
        rag = MultimodalRAG()

        result = rag.clear_document("nonexistent")

        assert result is False

    def test_clear_all(self):
        """测试清除所有"""
        rag = MultimodalRAG()

        rag._document_chunks["doc_001"] = []
        rag._document_chunks["doc_002"] = []

        rag.clear_all()

        assert len(rag._document_chunks) == 0
        assert len(rag._document_embeddings) == 0


# ============================================================
# 工厂类测试
# ============================================================

class TestMultimodalRAGFactory:
    """MultimodalRAGFactory 测试"""

    def test_create_default(self):
        """测试默认创建"""
        rag = MultimodalRAGFactory.create()

        assert isinstance(rag, MultimodalRAG)
        assert rag.config.image_embedding_model == ImageEmbeddingModel.RANDOM

    def test_create_with_model(self):
        """测试指定模型创建"""
        rag = MultimodalRAGFactory.create(
            model_type=ImageEmbeddingModel.RANDOM,
        )

        assert isinstance(rag, MultimodalRAG)

    def test_create_with_custom_config(self):
        """测试自定义配置创建"""
        rag = MultimodalRAGFactory.create(
            model_type=ImageEmbeddingModel.RANDOM,
            text_weight=0.8,
        )

        assert rag.config.text_weight == 0.8


# ============================================================
# 全局实例管理测试
# ============================================================

class TestGlobalInstanceManagement:
    """全局实例管理测试"""

    def setup_method(self):
        """每个测试前重置"""
        reset_multimodal_rag()

    def teardown_method(self):
        """每个测试后重置"""
        reset_multimodal_rag()

    def test_get_multimodal_rag(self):
        """测试获取全局实例"""
        rag = get_multimodal_rag()

        assert isinstance(rag, MultimodalRAG)

    def test_get_multimodal_rag_singleton(self):
        """测试全局实例单例"""
        rag1 = get_multimodal_rag()
        rag2 = get_multimodal_rag()

        assert rag1 is rag2

    def test_reset_multimodal_rag(self):
        """测试重置全局实例"""
        rag1 = get_multimodal_rag()
        reset_multimodal_rag()
        rag2 = get_multimodal_rag()

        assert rag1 is not rag2


# ============================================================
# 集成测试
# ============================================================

class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_end_to_end_text_search(self):
        """测试端到端文本搜索"""
        rag = MultimodalRAG()

        # 添加测试数据
        rag._document_chunks["doc_001"] = [
            MultimodalChunk(
                chunk_id="c1",
                document_id="doc_001",
                index=0,
                chunk_type=ChunkType.TEXT_ONLY,
                content="Python 是一种编程语言",
            ),
            MultimodalChunk(
                chunk_id="c2",
                document_id="doc_001",
                index=1,
                chunk_type=ChunkType.TEXT_ONLY,
                content="Java 也是一种编程语言",
            ),
        ]

        response = await rag.search(
            query="编程语言",
            modality=ModalityType.TEXT,
        )

        assert response.total_count >= 0
        assert response.search_time_ms >= 0

    @pytest.mark.asyncio
    async def test_end_to_end_multimodal_search(self):
        """测试端到端多模态搜索"""
        rag = MultimodalRAG()

        # 添加测试数据
        rag._document_chunks["doc_001"] = [
            MultimodalChunk(
                chunk_id="c1",
                document_id="doc_001",
                index=0,
                chunk_type=ChunkType.TEXT_ONLY,
                content="这是一张图片的描述",
            ),
            MultimodalChunk(
                chunk_id="c2",
                document_id="doc_001",
                index=1,
                chunk_type=ChunkType.IMAGE_ONLY,
                image_id="img_001",
                image_path="/fake/path.png",
            ),
        ]

        response = await rag.search(
            query="图片",
            modality=ModalityType.HYBRID,
        )

        assert isinstance(response.results, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
