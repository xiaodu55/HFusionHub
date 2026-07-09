"""Batch 5 单元测试：Embedding 多通道路由 + Milvus 元数据过滤。"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

import app.core.embedding as embedding_pkg
from app.core.embedding.openai_compatible import OpenAICompatibleEmbedding
from app.core.vectorstore.milvus_store import _matches_metadata_filter


# ── OpenAICompatibleEmbedding ─────────────────────────────────────────────


class _FakePostResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200
        self.text = ""

    @property
    def is_error(self):
        return False

    def json(self):
        return self._payload


def _patch_transport(monkeypatch, payload, captured):
    async def fake_post_with_retry(client, url, headers=None, json=None):
        captured.append({"url": url, "json": json, "headers": headers})
        return _FakePostResponse(payload)

    monkeypatch.setattr("app.core.llm.http_client.post_with_retry", fake_post_with_retry)
    monkeypatch.setattr("app.core.llm.http_client.get_shared_client", lambda **kw: MagicMock())


def _payload(dim=4, n=1):
    return {"data": [{"embedding": [0.1] * dim} for _ in range(n)]}


class TestOpenAICompatibleEmbedding:
    def test_unconfigured_not_available(self):
        client = OpenAICompatibleEmbedding(base_url="", api_key="", model="", dimension=4)
        assert client.is_configured is False

    @pytest.mark.asyncio
    async def test_generate_parses_embedding(self, monkeypatch):
        captured: List[Dict[str, Any]] = []
        _patch_transport(monkeypatch, _payload(dim=4), captured)
        client = OpenAICompatibleEmbedding(
            base_url="https://api.test", api_key="sk-x", model="text-embedding-v3", dimension=4)

        vector = await client.generate("你好")
        assert vector == [0.1] * 4
        assert captured[0]["url"].endswith("/v1/embeddings")
        assert captured[0]["json"] == {"model": "text-embedding-v3", "input": ["你好"]}
        assert captured[0]["headers"]["Authorization"] == "Bearer sk-x"

    @pytest.mark.asyncio
    async def test_dimension_mismatch_fails_closed(self, monkeypatch):
        captured: List[Dict[str, Any]] = []
        _patch_transport(monkeypatch, _payload(dim=8), captured)
        client = OpenAICompatibleEmbedding(
            base_url="https://api.test", api_key="sk-x", model="m", dimension=4)

        from app.core.exceptions import EmbeddingException
        with pytest.raises(EmbeddingException, match="维度不匹配"):
            await client.generate("你好")


class TestEmbeddingServiceRouting:
    def _service(self):
        from app.core.embedding import EmbeddingService

        return EmbeddingService(dimension=4)

    @pytest.mark.asyncio
    async def test_openai_provider_takes_priority(self, monkeypatch):
        from app.utils.config import config

        monkeypatch.setattr(config, "EMBEDDING_PROVIDER", "openai_compatible")
        monkeypatch.setattr(config, "EMBEDDING_OPENAI_BASE_URL", "https://api.test")
        monkeypatch.setattr(config, "EMBEDDING_OPENAI_API_KEY", "sk-x")
        monkeypatch.setattr(config, "EMBEDDING_OPENAI_MODEL", "m")
        monkeypatch.setattr(config, "EMBEDDING_OPENAI_DIMENSION", 4)

        service = self._service()
        calls = {"openai": 0, "ollama": 0}

        async def fake_openai_generate(text):
            calls["openai"] += 1
            return [0.1] * 4

        monkeypatch.setattr(service._openai_compatible, "generate", fake_openai_generate)
        monkeypatch.setattr(
            service._ollama, "is_available", property(lambda self: calls.__setitem__("ollama", calls["ollama"] + 1) or False)
        ) if False else None

        vector = await service.generate("文本")
        assert vector == [0.1] * 4
        assert calls["openai"] == 1

    @pytest.mark.asyncio
    async def test_falls_back_to_ollama_on_openai_failure(self, monkeypatch):
        from app.utils.config import config

        monkeypatch.setattr(config, "EMBEDDING_PROVIDER", "openai_compatible")
        monkeypatch.setattr(config, "EMBEDDING_OPENAI_BASE_URL", "https://api.test")
        monkeypatch.setattr(config, "EMBEDDING_OPENAI_API_KEY", "sk-x")
        monkeypatch.setattr(config, "EMBEDDING_OPENAI_MODEL", "m")
        monkeypatch.setattr(config, "EMBEDDING_OPENAI_DIMENSION", 4)
        # 允许随机降级以免测试依赖真实 Ollama
        monkeypatch.setattr(config, "EMBEDDING_ALLOW_FALLBACK", True)

        service = self._service()

        async def boom(text):
            raise RuntimeError("downstream down")

        monkeypatch.setattr(service._openai_compatible, "generate", boom)
        # Ollama 不可用 → 走允许的随机降级路径
        monkeypatch.setattr(type(service._ollama), "is_available", property(lambda self: False))

        vector = await service.generate("文本")
        assert len(vector) == 4

    @pytest.mark.asyncio
    async def test_ollama_default_unchanged(self, monkeypatch):
        from app.utils.config import config

        monkeypatch.setattr(config, "EMBEDDING_PROVIDER", "ollama")
        monkeypatch.setattr(config, "EMBEDDING_ALLOW_FALLBACK", True)
        service = self._service()
        monkeypatch.setattr(type(service._ollama), "is_available", property(lambda self: False))

        vector = await service.generate("文本")
        assert len(vector) == 4  # 随机降级路径（仅测试模式）


# ── 元数据过滤谓词 ─────────────────────────────────────────────────────────


class TestMetadataFilterPredicate:
    def test_empty_filter_always_true(self):
        assert _matches_metadata_filter(None, None) is True
        assert _matches_metadata_filter({}, {}) is True
        assert _matches_metadata_filter({"a": 1}, None) is True

    def test_string_normalization(self):
        meta = {"block_type": "TABLE", "count": 3}
        assert _matches_metadata_filter(meta, {"block_type": "TABLE"}) is True
        assert _matches_metadata_filter(meta, {"count": "3"}) is True  # int↔str 归一化
        assert _matches_metadata_filter(meta, {"block_type": "PARAGRAPH"}) is False

    def test_missing_key_fails(self):
        assert _matches_metadata_filter({"a": 1}, {"b": 1}) is False
        assert _matches_metadata_filter(None, {"a": 1}) is False

    def test_multiple_keys_are_and(self):
        meta = {"a": "1", "b": "2"}
        assert _matches_metadata_filter(meta, {"a": "1", "b": "2"}) is True
        assert _matches_metadata_filter(meta, {"a": "1", "b": "3"}) is False


# ── lite 存储后过滤 ────────────────────────────────────────────────────────


class TestLiteFilteredSearch:
    def _store(self):
        from app.core.vectorstore.milvus_lite import MilvusLiteStore

        store = MilvusLiteStore.__new__(MilvusLiteStore)  # 跳过 init（无真实 Milvus）
        return store

    def test_no_filter_delegates_directly(self, monkeypatch):
        store = self._store()
        calls = []

        def fake_search_client(client, embedding, top_k, kb_id, doc_id):
            calls.append(top_k)
            return [{"metadata": {}, "score": 1.0}]

        monkeypatch.setattr(store, "_search_client", fake_search_client)
        result = store._filtered_search(None, [0.1], 5, None, None, None)
        assert calls == [5]
        assert len(result) == 1

    def test_filter_overfetches_and_trims(self, monkeypatch):
        store = self._store()
        calls = []

        def fake_search_client(client, embedding, top_k, kb_id, doc_id):
            calls.append(top_k)
            return [
                {"metadata": {"block_type": "TABLE" if i % 10 == 0 else "PARAGRAPH"},
                 "score": 1.0 - i * 0.01}
                for i in range(top_k)
            ]

        monkeypatch.setattr(store, "_search_client", fake_search_client)
        result = store._filtered_search(
            None, [0.1], 3, None, None, {"block_type": "TABLE"})

        assert calls == [20]  # min(max(3*4, 20), 200)
        assert len(result) == 2  # 20 条里 i%10==0 的只有 2 条
        assert all(r["metadata"]["block_type"] == "TABLE" for r in result)


# ── 通道透传 ───────────────────────────────────────────────────────────────


class TestChannelPassThrough:
    @pytest.mark.asyncio
    async def test_vector_channel_forwards_filter(self, monkeypatch):
        from app.core.rag.query_router import VectorChannel

        captured = {}

        def fake_search_similar(**kwargs):
            captured.update(kwargs)
            return [{"content": "x", "score": 0.9, "metadata": {}, "document_id": "1",
                     "chunk_id": "c1", "knowledge_base_id": 7, "outline_path": []}]

        monkeypatch.setattr("app.core.vectorstore.milvus_store.search_similar", fake_search_similar)
        # VectorChannel 内部 from ... import search_similar 是运行时导入，patch 源头即可

        import app.core.rag.query_router as qr
        channel = VectorChannel(qr.ChannelConfig(channel_type=qr.ChannelType.VECTOR))
        results = await channel.search(
            "query", knowledge_base_id=7, top_k=5,
            metadata_filter={"block_type": "TABLE"})

        assert captured.get("metadata_filter") == {"block_type": "TABLE"}
        assert captured.get("knowledge_base_id") == 7
        assert len(results) == 1
