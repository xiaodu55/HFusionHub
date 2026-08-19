"""Subject-level ACL（主体级文档可见性）单元测试。

覆盖三层契约：
- clearance 上下文与等级归一化（app.core.security.clearance）；
- 存储层元数据过滤谓词的集合成员/缺省 visibility 语义（milvus_store）；
- 中间件对 X-User-Clearance 头的接受/拒绝/缺省（tenant_middleware）；
- 运行时评测轨道的主体选择策略（scripts/eval_runtime.subject_for_case）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.security.clearance import (
    DEFAULT_CLEARANCE,
    DEFAULT_VISIBILITY,
    allowed_visibilities,
    build_acl_metadata_filter,
    clear_clearance,
    get_clearance,
    normalize_clearance,
    normalize_visibility,
    set_clearance,
)
from app.core.vectorstore.milvus_store import _matches_metadata_filter
from app.api.tenant_middleware import TenantMiddleware

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
for _path in (str(SCRIPTS_DIR), str(PROJECT_ROOT)):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from eval_runtime import subject_for_case  # noqa: E402


# ---------------------------------------------------------------------------
# clearance 上下文与等级模型
# ---------------------------------------------------------------------------

class TestClearanceLevels:
    def test_allowed_visibilities_for_general_is_general_only(self):
        assert allowed_visibilities("general") == frozenset({"general"})

    def test_allowed_visibilities_for_admin_is_all_levels(self):
        assert allowed_visibilities("admin") == frozenset({"general", "confidential"})

    def test_unknown_clearance_falls_back_to_least_privilege(self):
        assert normalize_clearance("root") == DEFAULT_CLEARANCE
        assert normalize_clearance(None) == DEFAULT_CLEARANCE
        assert normalize_clearance("") == DEFAULT_CLEARANCE
        assert allowed_visibilities("root") == frozenset({"general"})

    def test_unknown_visibility_normalizes_to_default(self):
        assert normalize_visibility(None) == DEFAULT_VISIBILITY
        assert normalize_visibility("") == DEFAULT_VISIBILITY
        assert normalize_visibility("general") == "general"
        assert normalize_visibility("CONFIDENTIAL") == "confidential"

    def test_context_defaults_to_least_privilege(self):
        clear_clearance()
        assert get_clearance() == DEFAULT_CLEARANCE

    def test_set_and_get_roundtrip(self):
        clear_clearance()
        set_clearance("admin")
        assert get_clearance() == "admin"
        set_clearance("nonsense")  # 经 set 归一化，不会带入非法值
        assert get_clearance() == DEFAULT_CLEARANCE
        clear_clearance()


class TestAclFilter:
    def test_admin_gets_no_filter(self):
        assert build_acl_metadata_filter("admin") is None

    def test_general_gets_general_only_filter(self):
        assert build_acl_metadata_filter("general") == {"visibility": ["general"]}

    def test_missing_clearance_gets_least_privilege_filter(self):
        assert build_acl_metadata_filter(None) == {"visibility": ["general"]}


# ---------------------------------------------------------------------------
# 存储层谓词：集合成员 + 缺省 visibility
# ---------------------------------------------------------------------------

class TestMetadataFilterPredicate:
    def test_membership_matches_stored_visibility(self):
        pred = {"visibility": ["general", "confidential"]}
        assert _matches_metadata_filter({"visibility": "general"}, pred)
        assert _matches_metadata_filter({"visibility": "confidential"}, pred)
        assert not _matches_metadata_filter({"visibility": "secret"}, pred)

    def test_missing_visibility_treated_as_general(self):
        # V85 之前的存量向量没有 visibility 字段，语义等价 DB DEFAULT 'general'
        pred = {"visibility": ["general"]}
        assert _matches_metadata_filter({}, pred)
        assert _matches_metadata_filter({"document_title": "x"}, pred)
        # 但对"仅机密可见"的过滤器仍不可见（不存在这种合法过滤器，防御性）
        pred_all_restricted = {"visibility": ["confidential"]}
        assert not _matches_metadata_filter({}, pred_all_restricted)

    def test_value_level_string_tolerance(self):
        # 后端在调用谓词前已把 metadata JSON 反序列化为 dict；谓词对
        # 值级 str 形态归一化（str(actual) == str(expected)）
        pred = {"visibility": ["general"]}
        assert _matches_metadata_filter({"visibility": "general"}, pred)
        assert not _matches_metadata_filter(
            "not-a-dict", pred)  # 整段 JSON 字符串不是合法 metadata

    def test_scalar_equality_semantics_unchanged(self):
        assert _matches_metadata_filter(
            {"block_type": "TABLE"}, {"block_type": "TABLE"})
        assert not _matches_metadata_filter(
            {"block_type": "TABLE"}, {"block_type": "HEADING"})

    def test_empty_filter_always_true(self):
        assert _matches_metadata_filter(None, None)
        assert _matches_metadata_filter({}, {})
        assert _matches_metadata_filter({"visibility": "confidential"}, None)

    def test_non_dict_metadata_with_filter_is_false(self):
        assert not _matches_metadata_filter("not-a-dict", {"visibility": ["general"]})

    def test_acl_filter_hides_confidential_from_general_subject(self):
        acl = build_acl_metadata_filter("general")
        assert _matches_metadata_filter({"visibility": "general"}, acl)
        assert not _matches_metadata_filter({"visibility": "confidential"}, acl)
        assert not _matches_metadata_filter({}, {"visibility": ["confidential"]})


# ---------------------------------------------------------------------------
# 中间件：X-User-Clearance 传播
# ---------------------------------------------------------------------------

@pytest.fixture
def clearance_app():
    """带 TenantMiddleware 的最小应用，回显当前 clearance。"""
    from app.core.security.clearance import get_clearance as _get

    app = FastAPI()
    app.add_middleware(TenantMiddleware)

    @app.get("/echo-clearance")
    async def echo():
        return {"clearance": _get()}

    return app


class TestClearanceMiddleware:
    @pytest.mark.asyncio
    async def test_missing_header_defaults_to_general(self, clearance_app):
        async with AsyncClient(
            transport=ASGITransport(app=clearance_app), base_url="http://test"
        ) as client:
            resp = await client.get("/echo-clearance")
        assert resp.status_code == 200
        assert resp.json()["clearance"] == "general"

    @pytest.mark.asyncio
    async def test_admin_header_propagates(self, clearance_app):
        async with AsyncClient(
            transport=ASGITransport(app=clearance_app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/echo-clearance", headers={"X-User-Clearance": "admin"})
        assert resp.status_code == 200
        assert resp.json()["clearance"] == "admin"

    @pytest.mark.asyncio
    async def test_invalid_header_rejected(self, clearance_app):
        async with AsyncClient(
            transport=ASGITransport(app=clearance_app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/echo-clearance", headers={"X-User-Clearance": "superuser"})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_clearance_does_not_leak_across_requests(self, clearance_app):
        async with AsyncClient(
            transport=ASGITransport(app=clearance_app), base_url="http://test"
        ) as client:
            await client.get(
                "/echo-clearance", headers={"X-User-Clearance": "admin"})
            resp = await client.get("/echo-clearance")
        assert resp.json()["clearance"] == "general"


# ---------------------------------------------------------------------------
# 运行时评测轨道：主体选择策略
# ---------------------------------------------------------------------------

class _Case:
    def __init__(self, category: str):
        self.category = category


class TestSubjectForCase:
    def test_permission_cases_run_as_least_privilege(self):
        assert subject_for_case(_Case("permission")) == "general"

    @pytest.mark.parametrize("category", [
        "normal", "cross_document", "refusal", "injection", "tool", "long_document",
    ])
    def test_other_cases_run_as_admin(self, category):
        assert subject_for_case(_Case(category)) == "admin"
