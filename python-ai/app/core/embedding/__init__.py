"""
Embedding 模块 - 支持 Ollama Embedding 服务
策略: Ollama (BGE-M3 / qwen3-embedding) -> 随机向量（仅测试）
"""
import asyncio
import concurrent.futures
import hashlib
import logging
import os
import random
import threading
import time
from collections import OrderedDict

from app.core.embedding.ollama import OllamaEmbedding
from app.core.embedding.openai_compatible import OpenAICompatibleEmbedding
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

# ── 查询向量缓存（R16-5）───────────────────────────────────────────────────
# 检索侧同一 query 文本在一次请求内可能被多次嵌入（如 Agent 预检索与 ReAct
# 循环内 search_tool 命中同一文本），跨请求也会重复（重放压测/高频问法）。
# CPU 推理单次 ~2.5s（bge-m3 实测），缓存命中即省一次完整推理。
# key = provider|model|sha256(空白折叠后的文本)；容量与 TTL 见
# EMBEDDING_QUERY_CACHE_*（TTL=0 禁用）。锁只护字典操作，不跨网络等待——
# 并发同 key 未命中时各算一次再写回，属可接受的 stampede 代价。
_query_cache: "OrderedDict[str, tuple[float, list[float]]]" = OrderedDict()
_query_cache_lock = threading.Lock()
_query_cache_stats = {"hits": 0, "misses": 0}


def _query_cache_key(text: str, provider: str, model: str) -> str:
    normalized = " ".join(text.split())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"{provider}|{model}|{digest}"


def get_query_cache_stats() -> dict:
    """查询缓存命中统计（可观测：压测/排障时核对实际省掉的推理次数）。"""
    with _query_cache_lock:
        return {"size": len(_query_cache), **_query_cache_stats}


class EmbeddingService:
    """Ollama Embedding 服务"""

    def __init__(
        self,
        dimension: int = 1024,
        ollama_base_url: str | None = None,
        ollama_model: str | None = None
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
        # Batch 5：OpenAI 兼容通道（通义/OpenAI 等），EMBEDDING_PROVIDER=openai_compatible
        # 且三项配置齐全时优先使用；维度 fail-closed 校验保护 collection 完整性。
        self._openai_compatible = OpenAICompatibleEmbedding(
            base_url=config.EMBEDDING_OPENAI_BASE_URL,
            api_key=config.EMBEDDING_OPENAI_API_KEY,
            model=config.EMBEDDING_OPENAI_MODEL,
            dimension=config.EMBEDDING_OPENAI_DIMENSION or dimension,
        )

    def _use_openai_compatible(self) -> bool:
        return (config.EMBEDDING_PROVIDER == "openai_compatible"
                and self._openai_compatible.is_configured)

    async def generate(self, text: str, model: str = None) -> list[float]:
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
        # 优先：OpenAI 兼容通道（EMBEDDING_PROVIDER=openai_compatible）
        if self._use_openai_compatible():
            try:
                embedding = await self._openai_compatible.generate(text)
                logger.info("OpenAI-compatible embedding successful")
                return embedding
            except Exception as e:
                logger.warning(f"OpenAI-compatible embedding failed: {e}")

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

    def get_embedding(self, text: str) -> list[float]:
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

    def get_embedding_batch(self, texts: list[str]) -> list[list[float]]:
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

    # ── 检索侧缓存路径（R16-5）──────────────────────────────────────────

    def _query_cache_key(self, text: str) -> str:
        if self._use_openai_compatible():
            provider, model = "openai_compatible", self._openai_compatible.model
        else:
            provider, model = "ollama", self._ollama.model
        return _query_cache_key(text, provider, model)

    async def generate_query(self, text: str, model: str = None) -> list[float]:
        """
        生成检索侧 query embedding（LRU+TTL 缓存）。

        只用于检索路径的短文本 query（向量通道/搜索工具/图谱入口）；文档
        分块向量请走 generate/generate_batch——分块文本唯一，入缓存只会
        挤占查询热点条目。命中返回向量的副本，调用方改写不影响缓存。
        """
        ttl = config.EMBEDDING_QUERY_CACHE_TTL_SECONDS
        if ttl <= 0:
            return await self.generate(text, model)

        key = self._query_cache_key(text)
        now = time.monotonic()
        with _query_cache_lock:
            cached = _query_cache.get(key)
            if cached is not None and now - cached[0] <= ttl:
                _query_cache.move_to_end(key)
                _query_cache_stats["hits"] += 1
                return list(cached[1])

        embedding = await self.generate(text, model)

        with _query_cache_lock:
            _query_cache_stats["misses"] += 1
            _query_cache[key] = (time.monotonic(), embedding)
            _query_cache.move_to_end(key)
            max_entries = max(1, config.EMBEDDING_QUERY_CACHE_MAX_ENTRIES)
            while len(_query_cache) > max_entries:
                _query_cache.popitem(last=False)
        return list(embedding)

    def get_query_embedding(self, text: str) -> list[float]:
        """
        同步版本 - 获取带缓存的查询 Embedding（向量库检索路径专用）。

        与 get_embedding 的差异仅在缓存语义；事件循环/线程池策略一致。
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return _embedding_executor.submit(asyncio.run, self.generate_query(text)).result()
            else:
                return loop.run_until_complete(self.generate_query(text))
        except RuntimeError:
            return asyncio.run(self.generate_query(text))

    async def generate_batch(self, texts: list[str]) -> list[list[float]]:
        """
        批量生成 Embedding

        Args:
            texts: 输入文本列表

        Returns:
            Embedding 向量列表

        Raises:
            EmbeddingException: 嵌入服务不可用
        """
        # 优先：OpenAI 兼容通道
        if self._use_openai_compatible():
            try:
                embeddings = await self._openai_compatible.generate_batch(texts)
                logger.info("OpenAI-compatible batch embedding successful")
                return embeddings
            except Exception as e:
                logger.warning(f"OpenAI-compatible batch embedding failed: {e}")

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

    def _generate_random_vector(self) -> list[float]:
        """生成随机归一化向量（作为最终降级方案）"""
        vec = [random.gauss(0, 1) for _ in range(self.dimension)]
        norm = sum(x**2 for x in vec) ** 0.5
        return [x / norm for x in vec]


# 全局 Embedding 服务实例
_embedding_service: EmbeddingService | None = None
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


__all__ = ["EmbeddingService", "get_embedding_service", "get_query_cache_stats"]
