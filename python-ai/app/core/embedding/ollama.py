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
        self.model = model or os.getenv("OLLAMA_EMBEDDING_MODEL", "qwen3-embedding:8b-fp16")
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
            embeddings = await self._call_api([text])
            return embeddings[0]
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
        if not texts:
            return []
        try:
            return await self._call_api(texts)
        except Exception as e:
            logger.error(f"Ollama batch embedding failed: {e}")
            raise

    async def _call_api(self, texts: List[str]) -> List[List[float]]:
        """Call Ollama's batch embedding API with retry and dimension checks."""
        url = f"{self.base_url}/api/embed"

        payload = {
            "model": self.model,
            "input": texts,
            "dimensions": self.dimension,
        }

        max_retries = int(os.getenv("EMBEDDING_MAX_RETRIES", "3"))
        retry_delay = float(os.getenv("EMBEDDING_RETRY_DELAY", "1.0"))

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(url, json=payload, timeout=60.0)
                    response.raise_for_status()
                    result = response.json()

                    embeddings = result.get("embeddings", [])
                    if len(embeddings) != len(texts):
                        if attempt < max_retries - 1:
                            logger.warning(
                                "Ollama returned %s embeddings for %s inputs "
                                "(attempt %s/%s), retrying...",
                                len(embeddings),
                                len(texts),
                                attempt + 1,
                                max_retries,
                            )
                            await asyncio.sleep(retry_delay)
                            continue
                        raise ValueError(
                            f"Ollama returned {len(embeddings)} embeddings "
                            f"for {len(texts)} inputs"
                        )

                    invalid_dimensions = [
                        len(embedding)
                        for embedding in embeddings
                        if len(embedding) != self.dimension
                    ]
                    if invalid_dimensions:
                        raise ValueError(
                            "Ollama embedding dimension mismatch: "
                            f"expected {self.dimension}, got {invalid_dimensions[0]}"
                        )

                    return embeddings
            except httpx.TimeoutException:
                if attempt < max_retries - 1:
                    logger.warning(f"Ollama timeout (attempt {attempt + 1}/{max_retries}), retrying...")
                    await asyncio.sleep(retry_delay)
                    continue
                raise
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Ollama error (attempt {attempt + 1}/{max_retries}): {e}, retrying...")
                    await asyncio.sleep(retry_delay)
                    continue
                raise

    @property
    def is_available(self) -> bool:
        """检查 Ollama 是否可用（默认不可用，直接使用DeepSeek）"""
        return self._is_available

    def set_available(self, available: bool):
        """手动设置Ollama可用状态"""
        self._is_available = available
