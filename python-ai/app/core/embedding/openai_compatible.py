"""OpenAI 兼容 Embedding 通道 — 通义/OpenAI/任意 /v1/embeddings 端点。

设计要点：
- 与 ModelGateway 的 openai_compatible 通道同构：Bearer 认证 + /v1/embeddings，
  复用共享连接池与 P3 有界重试（429/5xx + jitter）。
- 维度校验 fail-closed：返回向量维度 ≠ 配置维度时抛 EmbeddingException——
  Milvus collection 以固定维度建表，写入异维向量会污染整个知识库索引。
  切换 embedding 供应商需要重建索引（重跑向量化），这是有意的硬约束。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class OpenAICompatibleEmbedding:
    """OpenAI chat-completions 协议族Embedding 客户端。"""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        dimension: int = 1024,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.model = model or ""
        self.dimension = dimension

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.model and self.api_key)

    async def generate(self, text: str) -> list[float]:
        embeddings = await self._call_api([text])
        return embeddings[0]

    async def generate_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await self._call_api(texts)

    async def _call_api(self, inputs: list[str]) -> list[list[float]]:
        if not self.is_configured:
            raise ValueError(
                "OpenAI 兼容 embedding 未配置：需要 EMBEDDING_OPENAI_BASE_URL / "
                "EMBEDDING_OPENAI_API_KEY / EMBEDDING_OPENAI_MODEL"
            )
        from app.core.exceptions import EmbeddingException
        from app.core.llm.http_client import get_shared_client, post_with_retry

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        client = get_shared_client(owner="embedding:openai_compatible")
        response = await post_with_retry(
            client,
            f"{self.base_url}/v1/embeddings",
            headers=headers,
            json={"model": self.model, "input": inputs},
        )
        if response.is_error:
            detail = response.text[:500]
            logger.warning("OpenAI-compatible embedding failed (%s): %s",
                           response.status_code, detail)
            raise EmbeddingException(
                f"Embedding 请求失败（{response.status_code}）：{detail}"
            )
        data = response.json()
        items = (data or {}).get("data") or []
        if len(items) != len(inputs):
            raise EmbeddingException(
                f"Embedding 返回条数不匹配：期望 {len(inputs)}，实际 {len(items)}"
            )
        embeddings: list[list[float]] = []
        for item in items:
            vector = item.get("embedding") or []
            if self.dimension and len(vector) != self.dimension:
                raise EmbeddingException(
                    f"Embedding 维度不匹配：模型 {self.model!r} 返回 {len(vector)} 维，"
                    f"collection 期望 {self.dimension} 维——切换供应商需重建向量索引"
                )
            embeddings.append(vector)
        return embeddings


__all__ = ["OpenAICompatibleEmbedding"]
