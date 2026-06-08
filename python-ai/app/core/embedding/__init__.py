"""
Embedding 模块 - 支持 Ollama Embedding 服务
策略: Ollama (BGE-M3 / qwen3-embedding) -> 随机向量（仅测试）
"""
import os
import random
import time
import logging
import asyncio
import concurrent.futures
from typing import List, Optional

from app.core.embedding.ollama import OllamaEmbedding
from app.core.exceptions import EmbeddingException
from app.utils.config import config

logger = logging.getLogger(__name__)

# Shared thread-pool for the synchronous embedding wrappers. Creating a fresh
# ThreadPoolExecutor() per call (each wrapping a fresh asyncio.run loop) churned
# threads and event loops on every query embedding; a module-level pool is
# reused across calls, matching the llm-probe executor pattern in
# app.core.llm.
_embedding_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="embedding-sync"
)


class EmbeddingService:
    """Ollama Embedding 服务"""

    def __init__(
        self,
        dimension: int = 1024,
        ollama_base_url: Optional[str] = None,
        ollama_model: Optional[str] = None
    ):
        """
        初始化 Embedding 服务

        Args:
            dimension: 向量维度
            ollama_base_url: Ollama API 地址
            ollama_model: Ollama Embedding 模型名称
        """
        self.dimension = dimension

        # Ollama Embedding (BGE-M3 or qwen3-embedding)
        self._ollama = OllamaEmbedding(
            base_url=ollama_base_url,
            model=ollama_model,
            dimension=dimension
        )

    async def generate(self, text: str, model: str = None) -> List[float]:
        """
        生成单个文本的 Embedding
        策略: Ollama -> (测试环境) 随机向量

        Args:
            text: 输入文本
            model: 指定使用的模型 (ollama)，None 则按默认策略

        Returns:
            Embedding 向量

        Raises:
            EmbeddingException: 嵌入服务不可用
        """
        # 尝试 Ollama
        if self._ollama.is_available:
            try:
                logger.info("Trying Ollama embedding...")
                embedding = await self._ollama.generate(text)
                logger.info("Ollama embedding successful")
                return embedding
            except Exception as e:
                logger.warning(f"Ollama failed: {e}")
        else:
            logger.info("Ollama not available")

        # 仅在测试配置下允许随机向量降级
        if config.EMBEDDING_ALLOW_FALLBACK:
            logger.warning("Using random vectors as fallback (test mode)")
            return self._generate_random_vector()

        logger.error("Ollama embedding failed, no fallback available")
        raise EmbeddingException("无法生成向量嵌入：Ollama 服务不可用")

    def get_embedding(self, text: str) -> List[float]:
        """
        同步版本 - 获取单个文本的 Embedding
        用于非异步环境（如 Milvus search_similar）

        Args:
            text: 输入文本

        Returns:
            Embedding 向量
        """
        try:
            # 尝试获取当前事件循环
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果循环正在运行，在共享线程池中跑一个新事件循环，避免阻塞
                # 正在运行的 loop（线程池模块级复用，不再每次新建）。
                return _embedding_executor.submit(asyncio.run, self.generate(text)).result()
            else:
                return loop.run_until_complete(self.generate(text))
        except RuntimeError:
            # 没有事件循环，创建一个新的
            return asyncio.run(self.generate(text))

    def get_embedding_batch(self, texts: List[str]) -> List[List[float]]:
        """
        同步版本 - 批量获取 Embedding

        Args:
            texts: 输入文本列表

        Returns:
            Embedding 向量列表
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return _embedding_executor.submit(asyncio.run, self.generate_batch(texts)).result()
            else:
                return loop.run_until_complete(self.generate_batch(texts))
        except RuntimeError:
            return asyncio.run(self.generate_batch(texts))

    async def generate_batch(self, texts: List[str]) -> List[List[float]]:
        """
        批量生成 Embedding

        Args:
            texts: 输入文本列表

        Returns:
            Embedding 向量列表

        Raises:
            EmbeddingException: 嵌入服务不可用
        """
        # 尝试 Ollama
        if self._ollama.is_available:
            try:
                logger.info("Trying Ollama batch embedding...")
                embeddings = await self._ollama.generate_batch(texts)
                logger.info("Ollama batch embedding successful")
                return embeddings
            except Exception as e:
                logger.warning(f"Ollama batch failed: {e}")
        else:
            logger.info("Ollama not available")

        # 仅在测试配置下允许随机向量降级
        if config.EMBEDDING_ALLOW_FALLBACK:
            logger.warning("Using random vectors as fallback (test mode)")
            return [self._generate_random_vector() for _ in texts]

        logger.error("Ollama embedding failed, no fallback available")
        raise EmbeddingException("无法生成向量嵌入：Ollama 服务不可用")

    def _generate_random_vector(self) -> List[float]:
        """生成随机归一化向量（作为最终降级方案）"""
        vec = [random.gauss(0, 1) for _ in range(self.dimension)]
        norm = sum(x**2 for x in vec) ** 0.5
        return [x / norm for x in vec]


# 全局 Embedding 服务实例
_embedding_service: Optional[EmbeddingService] = None
_last_probe_at: float = 0.0
_PROBE_TTL_SECONDS = 60.0


def _probe_ollama_once(service: EmbeddingService) -> None:
    """单次可用性探测（get_embedding_service 复用）。"""
    import httpx
    try:
        response = httpx.get(f"{service._ollama.base_url}/api/tags", timeout=5.0)
        if response.status_code == 200:
            models = response.json().get("models", [])
            model_names = [m["name"] for m in models]
            # Check if the configured model exists
            if service._ollama.model in model_names:
                service._ollama.set_available(True)
                logger.info(f"Ollama embedding available with model: {service._ollama.model}")
            elif any("embedding" in name.lower() for name in model_names):
                # Use the first embedding model found
                embedding_model = next(name for name in model_names if "embedding" in name.lower())
                service._ollama.model = embedding_model
                service._ollama.set_available(True)
                logger.info(f"Ollama embedding available with model: {embedding_model}")
            else:
                logger.warning(f"Ollama available but no embedding models found: {model_names}")
        else:
            logger.warning(f"Ollama not available: {response.status_code}")
    except Exception as e:
        logger.warning(f"Ollama connection failed: {e}")


def get_embedding_service() -> EmbeddingService:
    """获取全局 Embedding 服务"""
    global _embedding_service, _last_probe_at
    if _embedding_service is None:
        from app.utils.config import config

        # 从环境变量获取配置
        dimension = int(os.getenv("EMBEDDING_DIMENSION", "1024"))

        _embedding_service = EmbeddingService(
            dimension=dimension,
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            ollama_model=os.getenv("OLLAMA_EMBEDDING_MODEL", "qwen3-embedding:8b-fp16")
        )

        # Check if Ollama is available
        _probe_ollama_once(_embedding_service)
        _last_probe_at = time.monotonic()

    # R15-15：探活 TTL 化——旧实现只在进程首次取单例时探测一次，Ollama
    # 若当时不可用则 is_available 永久为 False（即使服务随后恢复也一直
    # 拒绝/降级）。不可用状态下每 TTL 秒重探一次（成功即恢复）。
    if not _embedding_service._ollama.is_available:
        if time.monotonic() - _last_probe_at > _PROBE_TTL_SECONDS:
            _last_probe_at = time.monotonic()
            _probe_ollama_once(_embedding_service)

    return _embedding_service


__all__ = ["EmbeddingService", "get_embedding_service"]
