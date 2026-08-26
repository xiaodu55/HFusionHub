"""ACL 越权回归矩阵（R16-14）——补第 36 批未覆盖的两条通道：

1. **向量通道后过滤管线端到端**：``_filtered_search`` 的「超额召回 → ACL
   谓词后过滤 → 截断 top_k」组合行为（此前仅单测过谓词本身与 BM25 通道）；
2. **直读端点**：``/api/search``、``/api/chunks/{document_id}``、
   ``/api/chunks/detail/{chunk_id}`` 按请求主体 clearance 强制执行
   （第 36 批修复了实现但未留 API 级回归）。

跨租户维度由 per-tenant co-store/collection 隔离保证
（见 tests/test_co_store_tenant_cache.py），此处不重复。
"""

from __future__ import annotations

import json
import threading

import pytest

from app.core.security.clearance import (
    build_acl_metadata_filter,
    clear_clearance,
    set_clearance,
)
from app.core.vectorstore.milvus_lite import MilvusLiteStore


def _candidate(chunk_id: str, visibility, as_json_string: bool = False) -> dict:
    metadata = {} if visibility is None else {"visibility": visibility}
    if as_json_string:
        metadata = json.dumps(metadata, ensure_ascii=False)
    return {
        "chunk_id": chunk_id,
        "document_id": "10",
        "knowledge_base_id": 1,
        "content": f"content of {chunk_id}",
        "score": 0.9,
        "block_type": "PARAGRAPH",
        "outline_path": [],
        "metadata": metadata,
    }


def _matrix_store(monkeypatch, candidates: list[dict]) -> MilvusLiteStore:
    """不启动嵌入式 milvus-lite 的 store 实例，向量召回以桩替换。"""
    store = object.__new__(MilvusLiteStore)
    store._base_collection = "hfusionhub_test"
    store._collection_name = "hfusionhub_test"
    store._client = None
    store._lock = threading.RLock()
    store._last_error = None

    def _fake_search_client(client, query_embedding, top_k, knowledge_base_id, document_id):
        return candidates[:top_k]

    monkeypatch.setattr(store, "_search_client", _fake_search_client)
    return store


# ---------------------------------------------------------------------------
# 向量通道：超额召回 → ACL 后过滤 → 截断
# ---------------------------------------------------------------------------

_CANDIDATES = [
    _candidate("c-general-1", "general"),
    _candidate("c-confidential-1", "confidential"),
    _candidate("c-general-2", "general"),
    _candidate("c-legacy", None),          # 旧分块无 visibility → 按 general
    _candidate("c-confidential-2", "confidential"),
    _candidate("c-general-json", "general", as_json_string=True),
]


def test_general_subject_never_receives_confidential(monkeypatch):
    store = _matrix_store(monkeypatch, _CANDIDATES)
    acl_filter = build_acl_metadata_filter("general")

    results = store._filtered_search(None, [0.0], 5, 1, None, acl_filter)

    ids = [r["chunk_id"] for r in results]
    assert "c-confidential-1" not in ids and "c-confidential-2" not in ids
    assert set(ids) == {"c-general-1", "c-general-2", "c-legacy", "c-general-json"}


def test_admin_has_no_filter_and_sees_all(monkeypatch):
    store = _matrix_store(monkeypatch, _CANDIDATES)

    results = store._filtered_search(None, [0.0], 5, 1, None, build_acl_metadata_filter("admin"))

    # admin 的 ACL 过滤器为 None → 走无过滤 top_k 直取路径，全量候选可见
    assert len(results) == 5
    assert "c-confidential-1" in {r["chunk_id"] for r in results}


def test_over_recall_truncates_to_top_k_preserving_order(monkeypatch):
    store = _matrix_store(monkeypatch, _CANDIDATES)
    acl_filter = build_acl_metadata_filter("general")

    results = store._filtered_search(None, [0.0], 2, 1, None, acl_filter)

    assert [r["chunk_id"] for r in results] == ["c-general-1", "c-general-2"]


def test_missing_clearance_is_least_privilege(monkeypatch):
    clear_clearance()
    store = _matrix_store(monkeypatch, _CANDIDATES)
    # 未设置 clearance 时调用方必须按 general 兜底（fail-closed 契约）
    assert build_acl_metadata_filter(None) == build_acl_metadata_filter("general")


# ---------------------------------------------------------------------------
# 直读端点：/api/search、/api/chunks、/api/chunks/detail
# ---------------------------------------------------------------------------

def _records() -> list[dict]:
    return [
        {"chunk_id": "10_chunk_0000", "content": "公开内容", "metadata": {"visibility": "general"},
         "block_type": "PARAGRAPH", "outline_path": "[]", "score": 0.9, "document_id": "10",
         "knowledge_base_id": 1},
        {"chunk_id": "10_chunk_0001", "content": "机密内容", "metadata": {"visibility": "confidential"},
         "block_type": "PARAGRAPH", "outline_path": "[]", "score": 0.95, "document_id": "10",
         "knowledge_base_id": 1},
    ]


@pytest.fixture
def endpoints(monkeypatch):
    from app.api import vectorization

    records = _records()
    monkeypatch.setattr(
        vectorization, "get_document_chunks",
        lambda document_id, page=1, size=20, block_type=None: {
            "code": 200, "data": {"records": records, "total": len(records)}},
    )

    def _fake_search(query_text, top_k=5, knowledge_base_id=None, metadata_filter=None,
                     **_):
        # 模拟存储层语义：无过滤直取 top_k；有过滤按谓词后过滤
        if not metadata_filter:
            return records[:top_k]
        from app.core.vectorstore.milvus_store import _matches_metadata_filter
        matched = [r for r in records if _matches_metadata_filter(r.get("metadata"), metadata_filter)]
        return matched[:top_k]

    monkeypatch.setattr(vectorization, "search_similar", _fake_search)
    return vectorization


@pytest.fixture(autouse=True)
def _clear_subject():
    clear_clearance()
    yield
    clear_clearance()


@pytest.mark.asyncio
async def test_list_chunks_hides_confidential_for_general(endpoints):
    set_clearance("general")
    resp = await endpoints.get_chunks(document_id="10")
    contents = [c.content for c in resp.chunks]
    assert contents == ["公开内容"]


@pytest.mark.asyncio
async def test_list_chunks_reveals_all_for_admin(endpoints):
    set_clearance("admin")
    resp = await endpoints.get_chunks(document_id="10")
    assert len(resp.chunks) == 2


@pytest.mark.asyncio
async def test_chunk_detail_confidential_is_invisible_for_general(endpoints):
    set_clearance("general")
    from app.core.exceptions import HFusionHubException
    with pytest.raises(HFusionHubException) as excinfo:
        await endpoints.get_chunk_detail(chunk_id="10_chunk_0001", document_id="10")
    assert excinfo.value.code == 404  # 按不存在处理，不泄漏存在性


@pytest.mark.asyncio
async def test_chunk_detail_confidential_ok_for_admin(endpoints):
    set_clearance("admin")
    resp = await endpoints.get_chunk_detail(chunk_id="10_chunk_0001", document_id="10")
    assert resp.content == "机密内容"


@pytest.mark.asyncio
async def test_search_applies_acl_filter_by_subject(endpoints):
    set_clearance("general")
    from app.models.document import SearchRequest
    resp = await endpoints.search_chunks(SearchRequest(query="内容", top_k=5, knowledge_base_id=1))
    assert [r.chunk_id for r in resp.results] == ["10_chunk_0000"]

    set_clearance("admin")
    resp = await endpoints.search_chunks(SearchRequest(query="内容", top_k=5, knowledge_base_id=1))
    assert len(resp.results) == 2


@pytest.mark.asyncio
async def test_search_defaults_to_general_when_subject_unset(endpoints):
    clear_clearance()
    from app.models.document import SearchRequest
    resp = await endpoints.search_chunks(SearchRequest(query="内容", top_k=5, knowledge_base_id=1))
    assert [r.chunk_id for r in resp.results] == ["10_chunk_0000"]  # fail-closed
