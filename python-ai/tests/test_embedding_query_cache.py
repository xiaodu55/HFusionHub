"""Tests for the R16-5 query-embedding cache (LRU + TTL) on EmbeddingService.

覆盖点：同文本命中省一次推理、归一化空白命中、不同模型隔离、TTL 过期、
TTL=0 禁用、容量 LRU 淘汰、命中返回副本。文档分块路径（generate/generate_batch）
不入缓存——分块文本唯一，缓存命中反而意味着错误的 key 设计。
"""

import pytest

from app.core.embedding import (
    EmbeddingService,
    _query_cache,
    _query_cache_stats,
    get_query_cache_stats,
)
from app.utils.config import config

_DIM = 8


def _make_service(monkeypatch, model="bge-m3:latest") -> EmbeddingService:
    service = EmbeddingService(dimension=_DIM, ollama_model=model)

    async def _fake_generate(text, model=None):
        # 可计数且可区分文本的假向量：每个文本只应真正推理一次
        return [float(len(text))] * _DIM

    monkeypatch.setattr(service, "generate", _fake_generate)
    return service


@pytest.fixture(autouse=True)
def _clear_cache():
    _query_cache.clear()
    _query_cache_stats["hits"] = 0
    _query_cache_stats["misses"] = 0
    yield
    _query_cache.clear()
    _query_cache_stats["hits"] = 0
    _query_cache_stats["misses"] = 0


@pytest.mark.asyncio
async def test_identical_query_is_served_from_cache(monkeypatch):
    service = _make_service(monkeypatch)
    monkeypatch.setattr(config, "EMBEDDING_QUERY_CACHE_TTL_SECONDS", 600)

    first = await service.generate_query("云帆智能的退款政策是什么")
    second = await service.generate_query("云帆智能的退款政策是什么")

    assert first == second
    assert get_query_cache_stats() == {"size": 1, "hits": 1, "misses": 1}


@pytest.mark.asyncio
async def test_whitespace_only_difference_hits_cache(monkeypatch):
    service = _make_service(monkeypatch)
    monkeypatch.setattr(config, "EMBEDDING_QUERY_CACHE_TTL_SECONDS", 600)

    await service.generate_query("退货  流程")
    await service.generate_query("退货 流程")

    assert get_query_cache_stats()["misses"] == 1  # 空白折叠后同一 key


@pytest.mark.asyncio
async def test_different_model_does_not_share_entries(monkeypatch):
    service_a = _make_service(monkeypatch, model="bge-m3:latest")
    service_b = _make_service(monkeypatch, model="qwen3-embedding:8b")
    monkeypatch.setattr(config, "EMBEDDING_QUERY_CACHE_TTL_SECONDS", 600)

    await service_a.generate_query("同一问题")
    await service_b.generate_query("同一问题")

    assert get_query_cache_stats()["misses"] == 2  # key 含模型名
    assert get_query_cache_stats()["size"] == 2


@pytest.mark.asyncio
async def test_expired_entry_recomputes(monkeypatch):
    service = _make_service(monkeypatch)
    monkeypatch.setattr(config, "EMBEDDING_QUERY_CACHE_TTL_SECONDS", 600)

    await service.generate_query("过期问题")
    key = next(iter(_query_cache.keys()))
    cached_at, cached_vec = _query_cache[key]
    _query_cache[key] = (cached_at - 9999, cached_vec)

    await service.generate_query("过期问题")
    assert get_query_cache_stats()["misses"] == 2  # TTL 外重新推理


@pytest.mark.asyncio
async def test_ttl_zero_disables_cache(monkeypatch):
    service = _make_service(monkeypatch)
    monkeypatch.setattr(config, "EMBEDDING_QUERY_CACHE_TTL_SECONDS", 0)

    await service.generate_query("禁用缓存")
    await service.generate_query("禁用缓存")

    assert get_query_cache_stats()["size"] == 0
    assert get_query_cache_stats()["misses"] == 0  # 直通路径不记统计


@pytest.mark.asyncio
async def test_lru_eviction_respects_capacity(monkeypatch):
    service = _make_service(monkeypatch)
    monkeypatch.setattr(config, "EMBEDDING_QUERY_CACHE_TTL_SECONDS", 600)
    monkeypatch.setattr(config, "EMBEDDING_QUERY_CACHE_MAX_ENTRIES", 2)

    await service.generate_query("问题一")
    await service.generate_query("问题二")
    await service.generate_query("问题三")  # 挤出「问题一」

    assert get_query_cache_stats()["size"] == 2
    await service.generate_query("问题一")  # 已被淘汰 → 重新推理
    assert get_query_cache_stats()["misses"] == 4


@pytest.mark.asyncio
async def test_hit_returns_a_copy(monkeypatch):
    service = _make_service(monkeypatch)
    monkeypatch.setattr(config, "EMBEDDING_QUERY_CACHE_TTL_SECONDS", 600)

    first = await service.generate_query("可变性问题")
    first[0] = -999.0
    second = await service.generate_query("可变性问题")

    assert second[0] != -999.0  # 调用方改写不污染缓存


@pytest.mark.asyncio
async def test_document_chunk_path_bypasses_cache(monkeypatch):
    """generate/generate_batch（文档分块）不入缓存——防止分块文本挤占热点。"""
    service = _make_service(monkeypatch)
    monkeypatch.setattr(config, "EMBEDDING_QUERY_CACHE_TTL_SECONDS", 600)

    await service.generate("某文档某分块的唯一长文本……")
    await service.generate_batch(["分块甲", "分块乙"])

    assert get_query_cache_stats()["size"] == 0
