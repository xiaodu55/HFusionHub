"""跨租户语料缓存隔离回归（第十五轮 P0-2，R15-2）。

旧实现：``_co_store_cache`` 以文件 ``(mtime_ns, size)`` 为键，但缓存值是
「单个租户」的作用域语料——双租户交替读取（期间文件无写入，mtime/size 不变）
时，后到的租户会直接命中前一个租户的缓存语料，构成跨租户数据泄漏。

新实现：缓存按租户分键（tenant_id → (file_sig, scoped)），LRU 封顶。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.core.tenant.context import clear_tenant_id, set_tenant_id
from app.core.vectorstore import milvus_store


def _chunk(doc_id: str, content: str) -> dict:
    return {
        "chunk_id": f"{doc_id}-c0",
        "document_id": doc_id,
        "knowledge_base_id": 1,
        "tenant_id": None,
        "content": content,
        "embedding": [0.0],
        "metadata": {},
    }


@pytest.fixture
def co_store_file(tmp_path, monkeypatch):
    """lite 模式 + 指向临时文件的 co-store，测试结束清理租户上下文。"""
    path = tmp_path / "chunks_store.json"
    monkeypatch.setattr(milvus_store, "CHUNKS_STORE_PATH", str(path))
    monkeypatch.setattr(milvus_store.config, "VECTOR_STORE_MODE", "lite")
    monkeypatch.setattr(milvus_store, "_get_store", lambda: object())
    milvus_store._co_store_cache.clear()
    yield path
    clear_tenant_id()
    milvus_store._co_store_cache.clear()


def _write_corpus(path: Path, corpus: dict) -> None:
    path.write_text(json.dumps(corpus), encoding="utf-8")


def test_second_tenant_does_not_inherit_first_tenant_cached_corpus(co_store_file):
    _write_corpus(
        co_store_file,
        {"1": {"docA": [_chunk("docA", "tenant one secret")]},
         "2": {"docB": [_chunk("docB", "tenant two data")]}},
    )

    set_tenant_id(1)
    first = milvus_store._load_chunks_store()
    assert set(first.keys()) == {"docA"}

    # 关键回归点：文件未变（mtime/size 相同），切换租户后不得命中租户 1 的缓存
    set_tenant_id(2)
    second = milvus_store._load_chunks_store()
    assert set(second.keys()) == {"docB"}
    assert "tenant one secret" not in json.dumps(second, ensure_ascii=False)


def test_cache_hit_only_for_same_tenant_and_file_signature(co_store_file, monkeypatch):
    calls = {"n": 0}
    real_open = Path.open

    def counting_open(self, *args, **kwargs):
        calls["n"] += 1
        return real_open(self, *args, **kwargs)

    _write_corpus(co_store_file, {"7": {"docX": [_chunk("docX", "x")]}})
    set_tenant_id(7)
    milvus_store._load_chunks_store()
    # 同租户同文件签名：第二次读取走缓存（不再打开文件）
    monkeypatch.setattr(Path, "open", counting_open)
    again = milvus_store._load_chunks_store()
    assert set(again.keys()) == {"docX"}
    assert calls["n"] == 0, "同租户同签名应命中缓存而非重新读文件"


def test_file_write_invalidates_cache_for_all_tenants(co_store_file):
    _write_corpus(co_store_file, {"1": {"docA": [_chunk("docA", "v1")]}})
    set_tenant_id(1)
    assert milvus_store._load_chunks_store().keys() == {"docA"}

    # 写入（os.replace → mtime/size 变化）后同租户读到新语料
    _write_corpus(co_store_file, {"1": {"docA2": [_chunk("docA2", "v2")]}})
    os.utime(co_store_file, None)  # 确保签名变化
    refreshed = milvus_store._load_chunks_store()
    assert set(refreshed.keys()) == {"docA2"}


def test_missing_tenant_context_returns_empty_without_poisoning_cache(co_store_file):
    _write_corpus(co_store_file, {"1": {"docA": [_chunk("docA", "a")]}})
    set_tenant_id(1)
    assert milvus_store._load_chunks_store().keys() == {"docA"}
    clear_tenant_id()
    assert milvus_store._load_chunks_store() == {}
    # 无租户上下文不得清掉已有租户的合法缓存条目
    set_tenant_id(1)
    assert milvus_store._load_chunks_store().keys() == {"docA"}
