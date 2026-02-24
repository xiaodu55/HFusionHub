"""
MultimodalRAG - 多模态检索增强生成模块

参考开源项目:
- LlamaIndex Multimodal RAG
- LangChain Multimodal
- CLIP (OpenAI)
- Chinese-CLIP (OFA-Sys)

核心功能:
1. 图片向量化 (CLIP/Chinese-CLIP)
2. 多模态文档解析 (从 PDF/DOCX 提取图片)
3. 图片分块器 (图片与文本关联)
4. 跨模态检索 (文本→图片、图片→文本)
"""

import os
import re
import time
import hashlib
import logging
import tempfile
from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass, field
from typing import (
    Any, Dict, List, Optional, Tuple, Union, Set
)
from pathlib import Path

logger = logging.getLogger(__name__)


# ============================================================
# 枚举定义
# ============================================================

class ImageEmbeddingModel(str, Enum):
    """图片嵌入模型类型"""
    OPENAI_CLIP = "openai_clip"  # OpenAI CLIP ViT-B/32
    CHINESE_CLIP = "chinese_clip"  # Chinese-CLIP (中文优化)
    SIGLIP = "siglip"  # Google SigLIP
    RANDOM = "random"  # 随机向量（降级方案）


class ModalityType(str, Enum):
    """模态类型"""
    TEXT = "text"
    IMAGE = "image"
    HYBRID = "hybrid"  # 文本+图片联合


class ImageSource(str, Enum):
    """图片来源"""
    PDF = "pdf"
    DOCX = "docx"
    MARKDOWN = "markdown"
    URL = "url"
    LOCAL = "local"


class ChunkType(str, Enum):
    """分块类型"""
    TEXT_ONLY = "text_only"
    IMAGE_ONLY = "image_only"
    TEXT_IMAGE = "text_image"  # 文本+图片关联


# ============================================================
# 数据模型
# ============================================================

@dataclass
class ImageInfo:
    """图片信息"""
    image_id: str
    source: ImageSource
    file_path: str = ""
    url: str = ""
    base64_data: str = ""
    description: str = ""  # 图片描述（可选，由 LLM 生成）
    page_number: Optional[int] = None  # 在文档中的页码
    position: Optional[int] = None  # 在页面中的位置
    surrounding_text: str = ""  # 周围文本
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "image_id": self.image_id,
            "source": self.source.value,
            "file_path": self.file_path,
            "url": self.url,
            "description": self.description,
            "page_number": self.page_number,
            "position": self.position,
            "surrounding_text": self.surrounding_text,
            "metadata": self.metadata,
        }


@dataclass
class ImageEmbedding:
    """图片嵌入结果"""
    image_id: str
    embedding: List[float]
    model_name: str
    dimension: int
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "image_id": self.image_id,
            "embedding": self.embedding,
            "model_name": self.model_name,
            "dimension": self.dimension,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class MultimodalChunk:
    """多模态分块"""
    chunk_id: str
    document_id: str
    index: int
    chunk_type: ChunkType
    content: str = ""  # 文本内容
    image_id: str = ""  # 关联的图片 ID
    image_path: str = ""  # 图片路径
    text_embedding: List[float] = field(default_factory=list)
    image_embedding: List[float] = field(default_factory=list)
    outline_path: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "index": self.index,
            "chunk_type": self.chunk_type.value,
            "content": self.content,
            "image_id": self.image_id,
            "image_path": self.image_path,
            "text_embedding": self.text_embedding,
            "image_embedding": self.image_embedding,
            "outline_path": self.outline_path,
            "metadata": self.metadata,
        }


@dataclass
class MultimodalSearchResult:
    """多模态搜索结果"""
    result_id: str
    score: float
    chunk_type: ChunkType
    content: str = ""
    image_id: str = ""
    image_path: str = ""
    text_snippet: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    modality: ModalityType = ModalityType.TEXT

    def to_dict(self) -> Dict[str, Any]:
        return {
            "result_id": self.result_id,
            "score": self.score,
            "chunk_type": self.chunk_type.value,
            "content": self.content,
            "image_id": self.image_id,
            "image_path": self.image_path,
            "text_snippet": self.text_snippet,
            "metadata": self.metadata,
            "modality": self.modality.value,
        }


@dataclass
class MultimodalSearchResponse:
    """多模态搜索响应"""
    query: str
    results: List[MultimodalSearchResult]
    total_count: int
    text_results_count: int
    image_results_count: int
    search_time_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "results": [r.to_dict() for r in self.results],
            "total_count": self.total_count,
            "text_results_count": self.text_results_count,
            "image_results_count": self.image_results_count,
            "search_time_ms": self.search_time_ms,
            "metadata": self.metadata,
        }


@dataclass
class MultimodalConfig:
    """多模态配置"""
    # 图片嵌入模型
    image_embedding_model: ImageEmbeddingModel = ImageEmbeddingModel.RANDOM
    image_embedding_dimension: int = 512  # CLIP 默认 512

    # 文本嵌入维度（与现有系统一致）
    text_embedding_dimension: int = 1024

    # 图片处理配置
    max_image_size_mb: float = 10.0
    supported_image_formats: List[str] = field(
        default_factory=lambda: [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"]
    )
    image_resize_max: Tuple[int, int] = (1024, 1024)

    # 检索配置
    text_weight: float = 0.6  # 文本检索权重
    image_weight: float = 0.4  # 图片检索权重
    max_results: int = 10
    similarity_threshold: float = 0.3

    # 缓存配置
    enable_cache: bool = True
    cache_ttl_seconds: int = 3600

    def to_dict(self) -> Dict[str, Any]:
        return {
            "image_embedding_model": self.image_embedding_model.value,
            "image_embedding_dimension": self.image_embedding_dimension,
            "text_embedding_dimension": self.text_embedding_dimension,
            "max_image_size_mb": self.max_image_size_mb,
            "supported_image_formats": self.supported_image_formats,
            "image_resize_max": self.image_resize_max,
            "text_weight": self.text_weight,
            "image_weight": self.image_weight,
            "max_results": self.max_results,
            "similarity_threshold": self.similarity_threshold,
            "enable_cache": self.enable_cache,
            "cache_ttl_seconds": self.cache_ttl_seconds,
        }


# ============================================================
# 图片嵌入器 (策略模式)
# ============================================================

class BaseImageEmbedder(ABC):
    """图片嵌入器基类"""

    @abstractmethod
    async def embed_image(self, image_path: str) -> List[float]:
        """嵌入单张图片"""
        pass

    @abstractmethod
    async def embed_image_from_bytes(self, image_bytes: bytes) -> List[float]:
        """从字节数据嵌入图片"""
        pass

    @abstractmethod
    async def embed_text(self, text: str) -> List[float]:
        """嵌入文本（用于跨模态对齐）"""
        pass

    @abstractmethod
    async def embed_batch(self, image_paths: List[str]) -> List[List[float]]:
        """批量嵌入图片"""
        pass


class CLIPImageEmbedder(BaseImageEmbedder):
    """CLIP 图片嵌入器"""

    def __init__(
        self,
        model_name: str = " ViT-B/32",
        device: str = "cpu",
        dimension: int = 512,
    ):
        self.model_name = model_name
        self.device = device
        self.dimension = dimension
        self._model = None
        self._processor = None
        self._available = False

    def _load_model(self):
        """懒加载模型"""
        if self._model is not None:
            return

        try:
            # 尝试加载 open_clip
            import open_clip
            import torch

            self._model, _, self._processor = open_clip.create_model_and_transforms(
                self.model_name,
                pretrained="openai",
                device=self.device
            )
            self._available = True
            logger.info(f"CLIP model loaded: {self.model_name}")
        except ImportError:
            logger.warning("open_clip not installed, using random vectors")
            self._available = False
        except Exception as e:
            logger.warning(f"Failed to load CLIP model: {e}")
            self._available = False

    async def embed_image(self, image_path: str) -> List[float]:
        """嵌入单张图片"""
        self._load_model()

        if not self._available:
            return self._random_embedding()

        try:
            import torch
            from PIL import Image

            image = Image.open(image_path).convert("RGB")
            image_tensor = self._processor(image).unsqueeze(0).to(self.device)

            with torch.no_grad():
                embedding = self._model.encode_image(image_tensor)
                embedding = embedding / embedding.norm(dim=-1, keepdim=True)

            return embedding.cpu().numpy().flatten().tolist()[:self.dimension]
        except Exception as e:
            logger.error(f"CLIP image embedding failed: {e}")
            return self._random_embedding()

    async def embed_image_from_bytes(self, image_bytes: bytes) -> List[float]:
        """从字节数据嵌入图片"""
        self._load_model()

        if not self._available:
            return self._random_embedding()

        try:
            import torch
            from PIL import Image
            import io

            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            image_tensor = self._processor(image).unsqueeze(0).to(self.device)

            with torch.no_grad():
                embedding = self._model.encode_image(image_tensor)
                embedding = embedding / embedding.norm(dim=-1, keepdim=True)

            return embedding.cpu().numpy().flatten().tolist()[:self.dimension]
        except Exception as e:
            logger.error(f"CLIP image embedding from bytes failed: {e}")
            return self._random_embedding()

    async def embed_text(self, text: str) -> List[float]:
        """嵌入文本（用于跨模态对齐）"""
        self._load_model()

        if not self._available:
            return self._random_embedding()

        try:
            import torch
            import open_clip

            tokenizer = open_clip.get_tokenizer(self.model_name)
            tokens = tokenizer([text]).to(self.device)

            with torch.no_grad():
                embedding = self._model.encode_text(tokens)
                embedding = embedding / embedding.norm(dim=-1, keepdim=True)

            return embedding.cpu().numpy().flatten().tolist()[:self.dimension]
        except Exception as e:
            logger.error(f"CLIP text embedding failed: {e}")
            return self._random_embedding()

    async def embed_batch(self, image_paths: List[str]) -> List[List[float]]:
        """批量嵌入图片"""
        results = []
        for path in image_paths:
            embedding = await self.embed_image(path)
            results.append(embedding)
        return results

    def _random_embedding(self) -> List[float]:
        """生成随机向量作为降级方案"""
        import random
        vec = [random.gauss(0, 1) for _ in range(self.dimension)]
        norm = sum(x**2 for x in vec) ** 0.5
        return [x / norm for x in vec]


class ChineseCLIPImageEmbedder(BaseImageEmbedder):
    """Chinese-CLIP 图片嵌入器（中文优化）"""

    def __init__(
        self,
        model_name: str = "chinese-clip-vit-base-patch16",
        device: str = "cpu",
        dimension: int = 512,
    ):
        self.model_name = model_name
        self.device = device
        self.dimension = dimension
        self._model = None
        self._available = False

    def _load_model(self):
        """懒加载模型"""
        if self._model is not None:
            return

        try:
            from chinese_clip import load_image, ChineseCLIP
            self._model = ChineseCLIP(self.model_name)
            self._available = True
            logger.info(f"Chinese-CLIP model loaded: {self.model_name}")
        except ImportError:
            logger.warning("chinese_clip not installed, using random vectors")
            self._available = False
        except Exception as e:
            logger.warning(f"Failed to load Chinese-CLIP model: {e}")
            self._available = False

    async def embed_image(self, image_path: str) -> List[float]:
        self._load_model()
        if not self._available:
            return self._random_embedding()

        try:
            import torch
            from PIL import Image

            image = Image.open(image_path).convert("RGB")
            # Chinese-CLIP 使用自己的预处理
            from torchvision import transforms
            transform = transforms.Compose([
                transforms.Resize(224),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
            ])
            image_tensor = transform(image).unsqueeze(0)

            with torch.no_grad():
                embedding = self._model.encode_image(image_tensor)
                embedding = embedding / embedding.norm(dim=-1, keepdim=True)

            return embedding.cpu().numpy().flatten().tolist()[:self.dimension]
        except Exception as e:
            logger.error(f"Chinese-CLIP image embedding failed: {e}")
            return self._random_embedding()

    async def embed_image_from_bytes(self, image_bytes: bytes) -> List[float]:
        self._load_model()
        if not self._available:
            return self._random_embedding()

        try:
            import torch
            from PIL import Image
            import io
            from torchvision import transforms

            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            transform = transforms.Compose([
                transforms.Resize(224),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
            ])
            image_tensor = transform(image).unsqueeze(0)

            with torch.no_grad():
                embedding = self._model.encode_image(image_tensor)
                embedding = embedding / embedding.norm(dim=-1, keepdim=True)

            return embedding.cpu().numpy().flatten().tolist()[:self.dimension]
        except Exception as e:
            logger.error(f"Chinese-CLIP image embedding from bytes failed: {e}")
            return self._random_embedding()

    async def embed_text(self, text: str) -> List[float]:
        self._load_model()
        if not self._available:
            return self._random_embedding()

        try:
            import torch
            from transformers import BertTokenizer

            tokenizer = BertTokenizer.from_pretrained(self.model_name)
            inputs = tokenizer(
                [text], padding=True, truncation=True,
                max_length=512, return_tensors="pt"
            )

            with torch.no_grad():
                embedding = self._model.encode_text(inputs)
                embedding = embedding / embedding.norm(dim=-1, keepdim=True)

            return embedding.cpu().numpy().flatten().tolist()[:self.dimension]
        except Exception as e:
            logger.error(f"Chinese-CLIP text embedding failed: {e}")
            return self._random_embedding()

    async def embed_batch(self, image_paths: List[str]) -> List[List[float]]:
        results = []
        for path in image_paths:
            embedding = await self.embed_image(path)
            results.append(embedding)
        return results

    def _random_embedding(self) -> List[float]:
        import random
        vec = [random.gauss(0, 1) for _ in range(self.dimension)]
        norm = sum(x**2 for x in vec) ** 0.5
        return [x / norm for x in vec]


class RandomImageEmbedder(BaseImageEmbedder):
    """随机图片嵌入器（降级方案）"""

    def __init__(self, dimension: int = 512):
        self.dimension = dimension

    async def embed_image(self, image_path: str) -> List[float]:
        return self._random_embedding()

    async def embed_image_from_bytes(self, image_bytes: bytes) -> List[float]:
        return self._random_embedding()

    async def embed_text(self, text: str) -> List[float]:
        return self._random_embedding()

    async def embed_batch(self, image_paths: List[str]) -> List[List[float]]:
        return [self._random_embedding() for _ in image_paths]

    def _random_embedding(self) -> List[float]:
        import random
        vec = [random.gauss(0, 1) for _ in range(self.dimension)]
        norm = sum(x**2 for x in vec) ** 0.5
        return [x / norm for x in vec]


class ImageEmbedderFactory:
    """图片嵌入器工厂"""

    @staticmethod
    def create(
        model_type: ImageEmbeddingModel = ImageEmbeddingModel.RANDOM,
        **kwargs
    ) -> BaseImageEmbedder:
        if model_type == ImageEmbeddingModel.OPENAI_CLIP:
            return CLIPImageEmbedder(**kwargs)
        elif model_type == ImageEmbeddingModel.CHINESE_CLIP:
            return ChineseCLIPImageEmbedder(**kwargs)
        elif model_type == ImageEmbeddingModel.SIGLIP:
            # SigLIP 使用与 CLIP 相同的接口
            return CLIPImageEmbedder(
                model_name=kwargs.get("model_name", "ViT-B/16"),
                **{k: v for k, v in kwargs.items() if k != "model_name"}
            )
        else:
            return RandomImageEmbedder(dimension=kwargs.get("dimension", 512))


# ============================================================
# 多模态文档解析器
# ============================================================

class MultimodalDocumentParser:
    """
    多模态文档解析器
    从 PDF/DOCX/Markdown 中提取图片和文本
    """

    def __init__(self, config: Optional[MultimodalConfig] = None):
        self.config = config or MultimodalConfig()

    def parse(self, file_path: str, document_id: str) -> List[MultimodalChunk]:
        """
        解析文档，提取文本和图片

        Args:
            file_path: 文件路径
            document_id: 文档ID

        Returns:
            多模态分块列表
        """
        file_ext = Path(file_path).suffix.lower()

        if file_ext == ".pdf":
            return self._parse_pdf(file_path, document_id)
        elif file_ext == ".docx":
            return self._parse_docx(file_path, document_id)
        elif file_ext in [".md", ".markdown"]:
            return self._parse_markdown(file_path, document_id)
        else:
            logger.warning(f"Unsupported file type for multimodal parsing: {file_ext}")
            return []

    def _parse_pdf(
        self, file_path: str, document_id: str
    ) -> List[MultimodalChunk]:
        """解析 PDF 文件"""
        chunks = []
        chunk_index = 0

        try:
            from PyPDF2 import PdfReader
            from PIL import Image
            import io

            reader = PdfReader(file_path)

            for page_num, page in enumerate(reader.pages):
                # 提取文本
                text = page.extract_text()
                if text and text.strip():
                    paragraphs = text.split('\n\n')
                    for para in paragraphs:
                        para = para.strip()
                        if not para:
                            continue

                        chunks.append(MultimodalChunk(
                            chunk_id=f"{document_id}_chunk_{chunk_index:04d}",
                            document_id=document_id,
                            index=chunk_index,
                            chunk_type=ChunkType.TEXT_ONLY,
                            content=para,
                            outline_path=[],
                            metadata={
                                "page": page_num + 1,
                                "char_count": len(para),
                                "source": "pdf"
                            }
                        ))
                        chunk_index += 1

                # 尝试提取图片（如果页面有图片）
                if hasattr(page, 'images'):
                    for img_idx, img in enumerate(page.images):
                        try:
                            img_data = img.data
                            if img_data:
                                # 保存图片到临时文件
                                img_id = f"{document_id}_img_{page_num}_{img_idx}"
                                img_path = os.path.join(
                                    tempfile.gettempdir(),
                                    f"{img_id}.png"
                                )
                                with open(img_path, "wb") as f:
                                    f.write(img_data)

                                # 创建图片分块
                                chunks.append(MultimodalChunk(
                                    chunk_id=f"{document_id}_chunk_{chunk_index:04d}",
                                    document_id=document_id,
                                    index=chunk_index,
                                    chunk_type=ChunkType.IMAGE_ONLY,
                                    image_id=img_id,
                                    image_path=img_path,
                                    metadata={
                                        "page": page_num + 1,
                                        "position": img_idx,
                                        "source": "pdf"
                                    }
                                ))
                                chunk_index += 1
                        except Exception as e:
                            logger.warning(f"Failed to extract image from PDF: {e}")

        except ImportError:
            logger.error("PyPDF2 or Pillow not installed")
        except Exception as e:
            logger.error(f"PDF parsing failed: {e}")

        return chunks

    def _parse_docx(
        self, file_path: str, document_id: str
    ) -> List[MultimodalChunk]:
        """解析 DOCX 文件"""
        chunks = []
        chunk_index = 0

        try:
            from docx import Document
            from PIL import Image
            import io

            doc = Document(file_path)

            # 提取文本段落
            for para in doc.paragraphs:
                text = para.text.strip()
                if not text:
                    continue

                # 判断段落类型
                block_type = "PARAGRAPH"
                if para.style and para.style.name:
                    style_name = para.style.name.lower()
                    if "heading" in style_name:
                        block_type = "HEADING"

                chunks.append(MultimodalChunk(
                    chunk_id=f"{document_id}_chunk_{chunk_index:04d}",
                    document_id=document_id,
                    index=chunk_index,
                    chunk_type=ChunkType.TEXT_ONLY,
                    content=text,
                    outline_path=[],
                    metadata={
                        "paragraph_index": chunk_index,
                        "style": para.style.name if para.style else "",
                        "source": "docx"
                    }
                ))
                chunk_index += 1

            # 提取图片
            for rel in doc.part.rels.values():
                if "image" in rel.reltype:
                    try:
                        img_data = rel.target_part.blob
                        img_id = f"{document_id}_img_{len(chunks)}"
                        img_ext = Path(rel.target_ref).suffix or ".png"
                        img_path = os.path.join(
                            tempfile.gettempdir(),
                            f"{img_id}{img_ext}"
                        )
                        with open(img_path, "wb") as f:
                            f.write(img_data)

                        chunks.append(MultimodalChunk(
                            chunk_id=f"{document_id}_chunk_{chunk_index:04d}",
                            document_id=document_id,
                            index=chunk_index,
                            chunk_type=ChunkType.IMAGE_ONLY,
                            image_id=img_id,
                            image_path=img_path,
                            metadata={
                                "source": "docx",
                                "rel_type": rel.reltype
                            }
                        ))
                        chunk_index += 1
                    except Exception as e:
                        logger.warning(f"Failed to extract image from DOCX: {e}")

        except ImportError:
            logger.error("python-docx or Pillow not installed")
        except Exception as e:
            logger.error(f"DOCX parsing failed: {e}")

        return chunks

    def _parse_markdown(
        self, file_path: str, document_id: str
    ) -> List[MultimodalChunk]:
        """解析 Markdown 文件"""
        chunks = []
        chunk_index = 0

        try:
            base_dir = Path(file_path).parent

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 使用正则表达式提取图片引用
            img_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
            img_matches = list(re.finditer(img_pattern, content))

            # 提取文本块（按段落分割）
            text_parts = re.split(r'\n\n+', content)

            for part in text_parts:
                part = part.strip()
                if not part:
                    continue

                # 跳过纯图片行
                if re.match(r'^!\[.*\]\(.*\)$', part):
                    continue

                chunks.append(MultimodalChunk(
                    chunk_id=f"{document_id}_chunk_{chunk_index:04d}",
                    document_id=document_id,
                    index=chunk_index,
                    chunk_type=ChunkType.TEXT_ONLY,
                    content=part,
                    outline_path=[],
                    metadata={
                        "source": "markdown"
                    }
                ))
                chunk_index += 1

            # 提取图片
            for img_match in img_matches:
                alt_text = img_match.group(1)
                img_path_raw = img_match.group(2)

                # 解析图片路径
                if img_path_raw.startswith(("http://", "https://")):
                    img_path = img_path_raw
                    img_id = hashlib.md5(img_path.encode()).hexdigest()[:12]
                else:
                    img_path = str(base_dir / img_path_raw)
                    img_id = f"{document_id}_img_{chunk_index}"

                # 检查本地文件是否存在
                if os.path.exists(img_path):
                    chunks.append(MultimodalChunk(
                        chunk_id=f"{document_id}_chunk_{chunk_index:04d}",
                        document_id=document_id,
                        index=chunk_index,
                        chunk_type=ChunkType.IMAGE_ONLY,
                        image_id=img_id,
                        image_path=img_path,
                        content=alt_text,  # alt 文本作为描述
                        metadata={
                            "source": "markdown",
                            "alt_text": alt_text,
                            "original_path": img_path_raw
                        }
                    ))
                    chunk_index += 1
                else:
                    logger.warning(f"Image not found: {img_path}")

        except Exception as e:
            logger.error(f"Markdown parsing failed: {e}")

        return chunks


# ============================================================
# 图片分块器
# ============================================================

class ImageChunker:
    """
    图片分块器
    将图片与周围文本关联，创建多模态分块
    """

    def __init__(self, config: Optional[MultimodalConfig] = None):
        self.config = config or MultimodalConfig()

    def chunk(
        self,
        chunks: List[MultimodalChunk],
        document_id: str
    ) -> List[MultimodalChunk]:
        """
        处理分块，关联图片和文本

        Args:
            chunks: 原始分块列表
            document_id: 文档ID

        Returns:
            处理后的多模态分块列表
        """
        if not chunks:
            return []

        # 分离文本块和图片块
        text_chunks = [c for c in chunks if c.chunk_type == ChunkType.TEXT_ONLY]
        image_chunks = [c for c in chunks if c.chunk_type == ChunkType.IMAGE_ONLY]

        if not image_chunks:
            return text_chunks

        # 为每个图片找到最近的文本块
        result = []
        image_indices = {c.index: c for c in image_chunks}

        for chunk in chunks:
            if chunk.chunk_type == ChunkType.IMAGE_ONLY:
                # 查找最近的文本块
                nearest_text = self._find_nearest_text(
                    chunk.index, text_chunks
                )
                if nearest_text:
                    chunk.surrounding_text = nearest_text.content
                    chunk.chunk_type = ChunkType.TEXT_IMAGE
                result.append(chunk)
            else:
                result.append(chunk)

        return result

    def _find_nearest_text(
        self,
        image_index: int,
        text_chunks: List[MultimodalChunk],
        max_distance: int = 3
    ) -> Optional[MultimodalChunk]:
        """查找最近的文本块"""
        nearest = None
        min_distance = float('inf')

        for chunk in text_chunks:
            distance = abs(chunk.index - image_index)
            if distance < min_distance and distance <= max_distance:
                min_distance = distance
                nearest = chunk

        return nearest


# ============================================================
# 跨模态检索器
# ============================================================

class CrossModalRetriever:
    """
    跨模态检索器
    支持文本→图片、图片→文本、混合检索
    """

    def __init__(
        self,
        image_embedder: BaseImageEmbedder,
        config: Optional[MultimodalConfig] = None,
    ):
        self.image_embedder = image_embedder
        self.config = config or MultimodalConfig()
        self._embedding_cache: Dict[str, List[float]] = {}

    async def search(
        self,
        query: str,
        chunks: List[MultimodalChunk],
        text_embeddings: Optional[List[List[float]]] = None,
        modality: ModalityType = ModalityType.HYBRID,
        top_k: int = 10,
    ) -> MultimodalSearchResponse:
        """
        执行多模态搜索

        Args:
            query: 查询文本
            chunks: 可用的多模态分块列表
            text_embeddings: 预计算的文本嵌入（可选）
            modality: 搜索模态
            top_k: 返回结果数量

        Returns:
            多模态搜索响应
        """
        start_time = time.time()
        results: List[MultimodalSearchResult] = []

        # 获取查询的文本嵌入
        query_text_embedding = await self.image_embedder.embed_text(query)

        # 根据模态类型搜索
        if modality in [ModalityType.TEXT, ModalityType.HYBRID]:
            text_results = await self._search_text(
                query_text_embedding, chunks, text_embeddings, top_k
            )
            results.extend(text_results)

        if modality in [ModalityType.IMAGE, ModalityType.HYBRID]:
            image_results = await self._search_image(
                query_text_embedding, chunks, top_k
            )
            results.extend(image_results)

        # 合并和排序结果
        results = self._merge_results(results, top_k)

        search_time_ms = (time.time() - start_time) * 1000

        # 统计结果
        text_count = sum(1 for r in results if r.modality == ModalityType.TEXT)
        image_count = sum(1 for r in results if r.modality == ModalityType.IMAGE)

        return MultimodalSearchResponse(
            query=query,
            results=results,
            total_count=len(results),
            text_results_count=text_count,
            image_results_count=image_count,
            search_time_ms=search_time_ms,
            metadata={
                "modality": modality.value,
                "top_k": top_k,
            }
        )

    async def _search_text(
        self,
        query_embedding: List[float],
        chunks: List[MultimodalChunk],
        text_embeddings: Optional[List[List[float]]],
        top_k: int,
    ) -> List[MultimodalSearchResult]:
        """文本检索"""
        results = []

        for i, chunk in enumerate(chunks):
            if chunk.chunk_type == ChunkType.IMAGE_ONLY:
                continue

            # 获取文本嵌入
            if text_embeddings and i < len(text_embeddings):
                chunk_embedding = text_embeddings[i]
            elif chunk.text_embedding:
                chunk_embedding = chunk.text_embedding
            else:
                # 计算嵌入（实际应用中应该预计算）
                continue

            # 计算相似度
            similarity = self._cosine_similarity(query_embedding, chunk_embedding)

            if similarity >= self.config.similarity_threshold:
                results.append(MultimodalSearchResult(
                    result_id=chunk.chunk_id,
                    score=similarity,
                    chunk_type=chunk.chunk_type,
                    content=chunk.content,
                    modality=ModalityType.TEXT,
                    metadata={
                        "chunk_index": chunk.index,
                        "outline_path": chunk.outline_path,
                    }
                ))

        # 按分数排序
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    async def _search_image(
        self,
        query_text_embedding: List[float],
        chunks: List[MultimodalChunk],
        top_k: int,
    ) -> List[MultimodalSearchResult]:
        """图片检索（文本→图片）"""
        results = []

        for chunk in chunks:
            if chunk.chunk_type == ChunkType.TEXT_ONLY:
                continue

            # 获取图片嵌入
            image_embedding = await self._get_image_embedding(chunk)

            if image_embedding:
                # 计算文本和图片的跨模态相似度
                similarity = self._cosine_similarity(
                    query_text_embedding, image_embedding
                )

                if similarity >= self.config.similarity_threshold:
                    results.append(MultimodalSearchResult(
                        result_id=chunk.chunk_id,
                        score=similarity,
                        chunk_type=chunk.chunk_type,
                        image_id=chunk.image_id,
                        image_path=chunk.image_path,
                        text_snippet=chunk.content[:200] if chunk.content else "",
                        modality=ModalityType.IMAGE,
                        metadata={
                            "chunk_index": chunk.index,
                            "surrounding_text": getattr(chunk, 'surrounding_text', ''),
                        }
                    ))

        # 按分数排序
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    async def _get_image_embedding(
        self, chunk: MultimodalChunk
    ) -> Optional[List[float]]:
        """获取图片嵌入"""
        cache_key = chunk.image_id

        # 检查缓存
        if cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]

        # 计算嵌入
        if chunk.image_path and os.path.exists(chunk.image_path):
            embedding = await self.image_embedder.embed_image(chunk.image_path)
        elif chunk.image_embedding:
            embedding = chunk.image_embedding
        else:
            return None

        # 缓存结果
        self._embedding_cache[cache_key] = embedding
        return embedding

    def _merge_results(
        self,
        results: List[MultimodalSearchResult],
        top_k: int,
    ) -> List[MultimodalSearchResult]:
        """合并和去重结果"""
        # 按结果ID去重
        seen_ids: Set[str] = set()
        unique_results = []

        for result in results:
            if result.result_id not in seen_ids:
                seen_ids.add(result.result_id)
                unique_results.append(result)

        # 重新计算综合分数
        for result in unique_results:
            if result.modality == ModalityType.TEXT:
                result.score *= self.config.text_weight
            elif result.modality == ModalityType.IMAGE:
                result.score *= self.config.image_weight

        # 排序并返回 top_k
        unique_results.sort(key=lambda x: x.score, reverse=True)
        return unique_results[:top_k]

    def _cosine_similarity(
        self, vec1: List[float], vec2: List[float]
    ) -> float:
        """计算余弦相似度"""
        if not vec1 or not vec2:
            return 0.0

        # 确保维度一致
        min_len = min(len(vec1), len(vec2))
        vec1 = vec1[:min_len]
        vec2 = vec2[:min_len]

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a ** 2 for a in vec1) ** 0.5
        norm2 = sum(b ** 2 for b in vec2) ** 0.5

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)


# ============================================================
# MultimodalRAG 主类
# ============================================================

class MultimodalRAG:
    """
    多模态 RAG 主类
    整合图片嵌入、文档解析、跨模态检索
    """

    def __init__(
        self,
        config: Optional[MultimodalConfig] = None,
        image_embedder: Optional[BaseImageEmbedder] = None,
    ):
        self.config = config or MultimodalConfig()
        self.image_embedder = image_embedder or ImageEmbedderFactory.create(
            self.config.image_embedding_model,
            dimension=self.config.image_embedding_dimension,
        )
        self.document_parser = MultimodalDocumentParser(self.config)
        self.image_chunker = ImageChunker(self.config)
        self.retriever = CrossModalRetriever(self.image_embedder, self.config)

        # 文档缓存
        self._document_chunks: Dict[str, List[MultimodalChunk]] = {}
        self._document_embeddings: Dict[str, List[List[float]]] = {}

    async def index_document(
        self,
        file_path: str,
        document_id: str,
    ) -> Dict[str, Any]:
        """
        索引文档（提取图片、生成嵌入）

        Args:
            file_path: 文件路径
            document_id: 文档ID

        Returns:
            索引结果
        """
        start_time = time.time()

        # 1. 解析文档
        chunks = self.document_parser.parse(file_path, document_id)
        logger.info(f"Parsed {len(chunks)} chunks from {file_path}")

        # 2. 处理图片关联
        chunks = self.image_chunker.chunk(chunks, document_id)
        logger.info(f"After chunking: {len(chunks)} chunks")

        # 3. 生成文本嵌入
        text_chunks = [c for c in chunks if c.chunk_type != ChunkType.IMAGE_ONLY]
        # 注意：实际应用中应该使用 EmbeddingService 生成嵌入
        # 这里简化处理

        # 4. 缓存结果
        self._document_chunks[document_id] = chunks

        elapsed_time = time.time() - start_time

        return {
            "document_id": document_id,
            "total_chunks": len(chunks),
            "text_chunks": len(text_chunks),
            "image_chunks": len(chunks) - len(text_chunks),
            "elapsed_seconds": round(elapsed_time, 2),
        }

    async def search(
        self,
        query: str,
        document_id: Optional[str] = None,
        modality: ModalityType = ModalityType.HYBRID,
        top_k: int = 10,
    ) -> MultimodalSearchResponse:
        """
        执行多模态搜索

        Args:
            query: 查询文本
            document_id: 限制搜索的文档ID（可选）
            modality: 搜索模态
            top_k: 返回结果数量

        Returns:
            多模态搜索响应
        """
        # 收集可用的分块
        if document_id:
            chunks = self._document_chunks.get(document_id, [])
        else:
            chunks = []
            for doc_chunks in self._document_chunks.values():
                chunks.extend(doc_chunks)

        if not chunks:
            return MultimodalSearchResponse(
                query=query,
                results=[],
                total_count=0,
                text_results_count=0,
                image_results_count=0,
                search_time_ms=0,
                metadata={"error": "No documents indexed"}
            )

        # 执行搜索
        return await self.retriever.search(
            query=query,
            chunks=chunks,
            modality=modality,
            top_k=top_k,
        )

    def get_document_info(self, document_id: str) -> Optional[Dict[str, Any]]:
        """获取文档信息"""
        chunks = self._document_chunks.get(document_id)
        if not chunks:
            return None

        return {
            "document_id": document_id,
            "total_chunks": len(chunks),
            "text_chunks": sum(
                1 for c in chunks if c.chunk_type != ChunkType.IMAGE_ONLY
            ),
            "image_chunks": sum(
                1 for c in chunks if c.chunk_type != ChunkType.TEXT_ONLY
            ),
        }

    def clear_document(self, document_id: str) -> bool:
        """清除文档索引"""
        if document_id in self._document_chunks:
            del self._document_chunks[document_id]
            if document_id in self._document_embeddings:
                del self._document_embeddings[document_id]
            return True
        return False

    def clear_all(self):
        """清除所有索引"""
        self._document_chunks.clear()
        self._document_embeddings.clear()
        self.retriever._embedding_cache.clear()


# ============================================================
# 工厂类和全局实例
# ============================================================

class MultimodalRAGFactory:
    """MultimodalRAG 工厂"""

    @staticmethod
    def create(
        model_type: ImageEmbeddingModel = ImageEmbeddingModel.RANDOM,
        **kwargs
    ) -> MultimodalRAG:
        config = MultimodalConfig(
            image_embedding_model=model_type,
            **{k: v for k, v in kwargs.items() if hasattr(MultimodalConfig, k)}
        )
        image_embedder = ImageEmbedderFactory.create(
            model_type,
            dimension=config.image_embedding_dimension,
        )
        return MultimodalRAG(config=config, image_embedder=image_embedder)


# 全局 MultimodalRAG 实例
_multimodal_rag: Optional[MultimodalRAG] = None


def get_multimodal_rag(
    model_type: ImageEmbeddingModel = ImageEmbeddingModel.RANDOM,
    **kwargs
) -> MultimodalRAG:
    """
    获取全局 MultimodalRAG 实例

    Args:
        model_type: 图片嵌入模型类型
        **kwargs: 其他参数

    Returns:
        MultimodalRAG 实例
    """
    global _multimodal_rag

    if _multimodal_rag is None:
        _multimodal_rag = MultimodalRAGFactory.create(model_type, **kwargs)

    return _multimodal_rag


def reset_multimodal_rag():
    """重置全局 MultimodalRAG（用于测试）"""
    global _multimodal_rag
    if _multimodal_rag:
        _multimodal_rag.clear_all()
    _multimodal_rag = None
