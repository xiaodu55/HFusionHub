"""
Ollama Embedding 模块 - 支持本地 BGE-M3 等模型
"""
import os
import asyncio
import logging
from typing import List, Optional
import httpx

logger = logging.getLogger(__name__)


class OllamaEmbedding:
    """Ollama Embedding 接口"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        dimension: int = 1024  # BGE-M3 输出维度
    ):
        """
        初始化 Ollama Embedding

        Args:
            base_url: Ollama API 地址
            model: Embedding 模型名称
            dimension: 向量维度
        """
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.model = model or os.getenv("OLLAMA_EMBEDDING_MODEL", "bge-m3")
        self.dimension = dimension
        # 默认不可用，启动时异步检查
        self._is_available = False

    async def generate(self, text: str) -> List[float]:
        """
        生成单个文本的 Embedding

        Args:
            text: 输入文本

        Returns:
            Embedding 向量
        """
        try:
            return await self._call_api(text)
        except Exception as e:
            logger.error(f"Ollama embedding failed: {e}")
            raise

    async def generate_batch(self, texts: List[str]) -> List[List[float]]:
        """
        批量生成 Embedding

        Args:
            texts: 输入文本列表

        Returns:
            Embedding 向量列表
        """
        # Ollama API 支持单个文本，批量需要逐个调用
        embeddings = []
        for text in texts:
            try:
                embedding = await self._call_api(text)
                embeddings.append(embedding)
            except Exception as e:
                logger.error(f"Ollama batch embedding failed for text: {text[:50]}... Error: {e}")
                raise
        return embeddings

    async def _call_api(self, text: str) -> List[float]:
        """调用 Ollama API"""
        url = f"{self.base_url}/api/embed"

        payload = {
            "model": self.model,
            "input": text
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=30.0)
            response.raise_for_status()
            result = response.json()

            # Ollama 返回格式: {"embeddings": [[...]]}
            embeddings = result.get("embeddings", [])
            if not embeddings or not embeddings[0]:
                raise ValueError(f"Ollama returned empty embeddings: {result}")

            return embeddings[0]

    @property
    def is_available(self) -> bool:
        """检查 Ollama 是否可用（默认不可用，直接使用DeepSeek）"""
        return self._is_available

    def set_available(self, available: bool):
        """手动设置Ollama可用状态"""
        self._is_available = available
