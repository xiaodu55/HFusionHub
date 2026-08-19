"""第三十六批回归测试：ACL 直读路径收口 + metadata JSON 容错。

覆盖本批修复的关键契约：
- ``_matches_metadata_filter`` 对 JSON 字符串形态 metadata 的容错
  （此前 lite co-store 落盘为字符串，谓词恒 False 清空 BM25 通道）；
- ``KeywordChannel`` 携带 ACL/block_type 过滤器时仍能返回候选；
- ``subject_can_see_metadata`` 直读闸门（未知 visibility fail-closed）；
- ``read_chunk_tool`` / ``list_document_chunks_tool`` 的可见性强制；
- ``_expand_heading_context`` 邻块与标题块同过滤。
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.core.security.clearance import clear_clearance, get_clearance, set_clearance
from app.core.vectorstore.milvus_store import _matches_metadata_filter
from app.core.rag.query_router import ChannelConfig, ChannelType, KeywordChannel

# ---------------------------------------------------------------------------
# 谓词：JSON 字符串形态 metadata 容错
# ---------------------------------------------------------------------------


class TestMetadataJsonStringTolerance:
    def test_json_string_metadata_matches_acl_filter(self):
        # lite co-store 落盘形态：metadata 为 JSON 字符串
        metadata = json.dumps({"visibility": "general", "document_title": "t"})
        assert _matches_metadata_filter(metadata, {"visibility": ["general"]})

    def test_json_string_metadata_hidden_for_restricted_filter(self):
        metadata = json.dumps({"visibility": "confidential"})
        assert not _matches_metadata_filter(metadata, {"visibility": ["general"]})

    def test_invalid_json_string_fails_closed(self):
        assert not _matches_metadata_filter("not-json{", {"visibility": ["general"]})

    def test_json_string_block_type_filter(self):
        metadata = json.dumps({"block_type": "PARAGRAPH"})
        assert _matches_metadata_filter(metadata, {"block_type": "PARAGRAPH"})
        assert not _matches_metadata_filter(metadata, {"block_type": "TABLE"})

    def test_string_form_equivalent_to_dict_form(self):
        as_dict = {"visibility": "general", "block_type": "HEADING"}
        as_str = json.dumps(as_dict)
        pred = {"visibility": ["general"]}
        assert _matches_metadata_filter(as_dict, pred) == _matches_metadata_filter(as_str, pred)


# ---------------------------------------------------------------------------
# KeywordChannel：ACL 过滤下仍能返回候选（回归：此前命中恒 0）
# ---------------------------------------------------------------------------


def _chunk(chunk_id: str, visibility: str) -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": "10",
        "knowledge_base_id": 5,
        "content": "alpha beta content for search",
        "block_type": "PARAGRAPH",
        "metadata": json.dumps({"visibility": visibility, "block_type": "PARAGRAPH"}),
    }


class TestKeywordChannelWithAclFilter:
    @pytest.mark.asyncio
    async def test_acl_filter_keeps_general_candidates(self):
        # 回归：metadata 为 JSON 字符串时，旧实现对带 filter 的请求返回 []
        store = {"10": [_chunk("10_chunk_0000", "general"), _chunk("10_chunk_0001", "confidential")]}
        with patch("app.core.vectorstore.milvus_store._load_chunks_store", return_value=store):
            channel = KeywordChannel(config=ChannelConfig(channel_type=ChannelType.KEYWORD))
            results = await channel.search(
                query="alpha beta",
                knowledge_base_id=5,
                top_k=5,
                metadata_filter={"visibility": ["general"]},
            )
        assert [r.metadata["chunk_id"] for r in results] == ["10_chunk_0000"]

    @pytest.mark.asyncio
    async def test_admin_filter_none_returns_all(self):
        store = {"10": [_chunk("10_chunk_0000", "general"), _chunk("10_chunk_0001", "confidential")]}
        with patch("app.core.vectorstore.milvus_store._load_chunks_store", return_value=store):
            channel = KeywordChannel(config=ChannelConfig(channel_type=ChannelType.KEYWORD))
            results = await channel.search(
                query="alpha beta", knowledge_base_id=5, top_k=5, metadata_filter=None
            )
        assert len(results) == 2


# ---------------------------------------------------------------------------
# subject_can_see_metadata：直读闸门
# ---------------------------------------------------------------------------


class TestSubjectCanSeeMetadata:
    def setup_method(self):
        clear_clearance()

    def teardown_method(self):
        clear_clearance()

    def test_missing_clearance_is_least_privilege(self):
        assert get_clearance() == "general"
        assert not self._visible(json.dumps({"visibility": "confidential"}))
        assert self._visible(json.dumps({"visibility": "general"}))

    def test_admin_sees_everything(self):
        set_clearance("admin")
        assert self._visible(json.dumps({"visibility": "confidential"}))
        assert self._visible({})

    def test_unknown_visibility_fails_closed(self):
        # 未知等级按最敏感处理：general 不可见、admin 可见
        assert not self._visible(json.dumps({"visibility": "secret"}))
        set_clearance("admin")
        assert self._visible(json.dumps({"visibility": "secret"}))

    def test_legacy_chunk_without_visibility_is_general(self):
        assert self._visible(json.dumps({"document_title": "legacy"}))

    def _visible(self, metadata) -> bool:
        from app.core.security.clearance import subject_can_see_metadata

        return subject_can_see_metadata(metadata)


# ---------------------------------------------------------------------------
# 分块直读工具：可见性强制
# ---------------------------------------------------------------------------


def _detail(visibility: str) -> dict:
    return {
        "chunk_id": "10_chunk_0000",
        "document_id": "10",
        "knowledge_base_id": 5,
        "content": "secret body",
        "block_type": "PARAGRAPH",
        "metadata": json.dumps({"visibility": visibility}),
    }


class TestChunkToolsAcl:
    def setup_method(self):
        clear_clearance()

    def teardown_method(self):
        clear_clearance()

    @pytest.mark.asyncio
    async def test_read_chunk_denied_for_general(self):
        from app.core.tools.read_chunk_tool import ReadChunkTool

        with patch("app.core.vectorstore.milvus_store.get_chunk_detail", return_value=_detail("confidential")):
            result = await ReadChunkTool(knowledge_base_id=5).execute(
                chunk_id="10_chunk_0000", knowledge_base_id=5
            )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_read_chunk_allowed_for_admin(self):
        from app.core.tools.read_chunk_tool import ReadChunkTool

        set_clearance("admin")
        with patch("app.core.vectorstore.milvus_store.get_chunk_detail", return_value=_detail("confidential")):
            result = await ReadChunkTool(knowledge_base_id=5).execute(
                chunk_id="10_chunk_0000", knowledge_base_id=5
            )
        assert result.get("content") == "secret body"

    @pytest.mark.asyncio
    async def test_list_chunks_hides_confidential_for_general(self):
        from app.core.tools.list_document_chunks_tool import ListDocumentChunksTool

        records = [
            {"chunk_id": "10_chunk_0000", "knowledge_base_id": 5, "content": "pub", "metadata": json.dumps({"visibility": "general"})},
            {"chunk_id": "10_chunk_0001", "knowledge_base_id": 5, "content": "priv", "metadata": json.dumps({"visibility": "confidential"})},
        ]

        def fake_page(document_id, page=1, size=50):
            return {
                "code": 200,
                "data": {"records": records if page == 1 else [], "total": len(records)},
            }

        with patch(
            "app.core.vectorstore.milvus_store.get_document_chunks", side_effect=fake_page
        ):
            result = await ListDocumentChunksTool(knowledge_base_id=5).execute(document_id=10, knowledge_base_id=5)
        assert [c["chunk_id"] for c in result["chunks"]] == ["10_chunk_0000"]

    @pytest.mark.asyncio
    async def test_list_chunks_reveals_all_for_admin(self):
        from app.core.tools.list_document_chunks_tool import ListDocumentChunksTool

        set_clearance("admin")
        records = [
            {"chunk_id": "10_chunk_0000", "knowledge_base_id": 5, "content": "pub", "metadata": json.dumps({"visibility": "general"})},
            {"chunk_id": "10_chunk_0001", "knowledge_base_id": 5, "content": "priv", "metadata": json.dumps({"visibility": "confidential"})},
        ]

        def fake_page(document_id, page=1, size=50):
            return {
                "code": 200,
                "data": {"records": records if page == 1 else [], "total": len(records)},
            }

        with patch(
            "app.core.vectorstore.milvus_store.get_document_chunks", side_effect=fake_page
        ):
            result = await ListDocumentChunksTool(knowledge_base_id=5).execute(document_id=10, knowledge_base_id=5)
        assert len(result["chunks"]) == 2


# ---------------------------------------------------------------------------
# 标题扩展：邻块同过滤
# ---------------------------------------------------------------------------


class TestHeadingExpansionFilter:
    @pytest.mark.asyncio
    async def test_neighbor_filtered_by_acl(self):
        heading = {
            "chunk_id": "10_chunk_0000",
            "document_id": "10",
            "knowledge_base_id": 5,
            "content": "heading text",
            "block_type": "HEADING",
            "metadata": json.dumps({"visibility": "general"}),
        }
        neighbor = {
            "chunk_id": "10_chunk_0001",
            "document_id": "10",
            "knowledge_base_id": 5,
            "content": "classified neighbor",
            "block_type": "PARAGRAPH",
            "metadata": json.dumps({"visibility": "confidential"}),
        }
        store = {"10": [heading, neighbor]}
        with patch("app.core.vectorstore.milvus_store._load_chunks_store", return_value=store):
            channel = KeywordChannel(config=ChannelConfig(channel_type=ChannelType.KEYWORD))
            results = await channel.search(
                query="heading text",
                knowledge_base_id=5,
                top_k=5,
                metadata_filter={"visibility": ["general"]},
            )
        assert len(results) == 1
        assert "classified neighbor" not in results[0].content
        assert results[0].metadata["neighbor_chunk_ids"] == []
