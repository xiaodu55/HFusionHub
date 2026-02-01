"""
Embedding 模块 - 支持多种 Embedding 服务
策略: Ollama BGE-M3 -> DeepSeek -> 随机向量
"""
import os
import random
import logging
from typing import List, Optional

from app.core.embedding.deepseek import DeepSeekEmbedding
from app.core.embedding.ollama import OllamaEmbedding

logger = logging.getLogger(__name__)


class EmbeddingService:
    """多策略 Embedding 服务"""

    def __init__(
        self,
        dimension: int = 1024,
        deepseek_api_key: Optional[str] = None,
        deepseek_base_url: Optional[str] = None,
        ollama_base_url: Optional[str] = None,
        ollama_model: Optional[str] = None
    ):
        """
        初始化 Embedding 服务

        Args:
            dimension: 向量维度
            deepseek_api_key: DeepSeek API Key
            deepseek_base_url: DeepSeek API 地址
            ollama_base_url: Ollama API 地址
            ollama_model: Ollama Embedding 模型名称
        """
        self.dimension = dimension

        # DeepSeek Embedding
        self._deepseek = DeepSeekEmbedding(
            api_key=deepseek_api_key,
            base_url=deepseek_base_url,
            dimension=dimension
        )

        # Ollama Embedding (BGE-M3)
        self._ollama = OllamaEmbedding(
            base_url=ollama_base_url,
            model=ollama_model,
            dimension=dimension
        )

    async def generate(self, text: str) -> List[float]:
        """
        生成单个文本的 Embedding
        策略: Ollama -> DeepSeek -> 随机向量

        Args:
            text: 输入文本

        Returns:
            Embedding 向量
        """
        # 1. 尝试 Ollama BGE-M3
        if self._ollama.is_available:
            try:
                logger.info("Trying Ollama BGE-M3 embedding...")
                embedding = await self._ollama.generate(text)
                logger.info("Ollama BGE-M3 embedding successful")
                return embedding
            except Exception as e:
                logger.warning(f"Ollama BGE-M3 failed: {e}, trying DeepSeek...")
        else:
            logger.info("Ollama not available, trying DeepSeek...")

        # 2. 尝试 DeepSeek API
        try:
            embedding = await self._deepseek.generate(text)
            logger.info("DeepSeek embedding successful")
            return embedding
        except Exception as e:
            logger.warning(f"DeepSeek failed: {e}, using random vectors...")

        # 3. 降级为随机向量
        logger.warning("Using random vectors as fallback")
        return self._generate_random_vector()

    async def generate_batch(self, texts: List[str]) -> List[List[float]]:
        """
        批量生成 Embedding

        Args:
            texts: 输入文本列表

        Returns:
            Embedding 向量列表
        """
        # 1. 尝试 Ollama BGE-M3
        if self._ollama.is_available:
            try:
                logger.info("Trying Ollama BGE-M3 batch embedding...")
                embeddings = await self._ollama.generate_batch(texts)
                logger.info("Ollama BGE-M3 batch embedding successful")
                return embeddings
            except Exception as e:
                logger.warning(f"Ollama BGE-M3 batch failed: {e}, trying DeepSeek...")
        else:
            logger.info("Ollama not available, trying DeepSeek...")

        # 2. 尝试 DeepSeek API
        try:
            embeddings = await self._deepseek.generate_batch(texts)
            logger.info("DeepSeek batch embedding successful")
            return embeddings
        except Exception as e:
            logger.warning(f"DeepSeek batch failed: {e}, using random vectors...")

        # 3. 降级为随机向量
        logger.warning("Using random vectors as fallback")
        return [self._generate_random_vector() for _ in texts]

    def _generate_random_vector(self) -> List[float]:
        """生成随机归一化向量（作为最终降级方案）"""
        vec = [random.gauss(0, 1) for _ in range(self.dimension)]
        norm = sum(x**2 for x in vec) ** 0.5
        return [x / norm for x in vec]


# 全局 Embedding 服务实例
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """获取全局 Embedding 服务"""
    global _embedding_service
    if _embedding_service is None:
        from app.utils.config import config

        # 从环境变量获取配置
        dimension = int(os.getenv("EMBEDDING_DIMENSION", "1024"))

        _embedding_service = EmbeddingService(
            dimension=dimension,
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY"),
            deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            ollama_model=os.getenv("OLLAMA_EMBEDDING_MODEL", "bge-m3")
        )
    return _embedding_service


__all__ = ["EmbeddingService", "get_embedding_service"]
