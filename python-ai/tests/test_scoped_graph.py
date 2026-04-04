import pytest

from app.core.rag.query_router import (
    ChannelConfig,
    ChannelType,
    GraphChannel,
    QueryRouter,
    QueryType,
)
from app.core.rag.scoped_graph import ScopedGraphStore


def _chunks_store():
    return {
        "doc-a": [{
            "chunk_id": "chunk-a",
            "document_id": "doc-a",
            "knowledge_base_id": 1,
            "content": "OAuth PKCE protects authorization code exchange.",
            "outline_path": ["Security"],
        }],
        "doc-b": [{
            "chunk_id": "chunk-b",
            "document_id": "doc-b",
            "knowledge_base_id": 2,
            "content": "OAuth PKCE is a private knowledge base policy.",
            "outline_path": ["Private"],
        }],
    }


def _index(store):
    chunks = _chunks_store()
    store.replace_document(1, "doc-a", chunks["doc-a"])
    store.replace_document(2, "doc-b", chunks["doc-b"])


def test_scoped_graph_returns_only_current_kb_source_chunk(tmp_path):
    store = ScopedGraphStore(tmp_path / "graph.json")
    _index(store)

    results = store.search("OAuth PKCE", 1, _chunks_store(), top_k=5)

    assert [item["metadata"]["chunk_id"] for item in results] == ["chunk-a"]
    assert results[0]["metadata"]["knowledge_base_id"] == 1
    assert results[0]["metadata"]["graph"]["paths"]
    stats = store.stats(1)
    assert stats["knowledge_base_id"] == 1
    assert stats["node_count"] > 0
    assert stats["edge_count"] > 0


def test_scoped_graph_fails_closed_when_source_chunk_was_deleted(tmp_path):
    store = ScopedGraphStore(tmp_path / "graph.json")
    _index(store)

    results = store.search("OAuth PKCE", 1, {"doc-b": _chunks_store()["doc-b"]}, top_k=5)

    assert results == []


def test_graph_records_carry_tenant_stamp(tmp_path):
    store = ScopedGraphStore(tmp_path / "graph.json")
    store.replace_document(1, "doc-a", _chunks_store()["doc-a"], tenant_id=7)

    graph = store._read()
    assert graph["nodes"]
    assert {n.get("tenant_id") for n in graph["nodes"]} == {7}
    assert {e.get("tenant_id") for e in graph["edges"]} == {7}


def test_graph_removal_is_tenant_scoped(tmp_path):
    """Deleting a doc id in tenant 2 must NOT purge tenant 1's graph."""
    store = ScopedGraphStore(tmp_path / "graph.json")
    store.replace_document(1, "shared-doc", _chunks_store()["doc-a"], tenant_id=1)
    store.replace_document(2, "shared-doc", _chunks_store()["doc-b"], tenant_id=2)

    # Tenant 2 removes the SAME document id.
    store.remove_document_from_tenant_scopes(2, "shared-doc")

    graph = store._read()
    # Tenant 1's node/edge evidence must survive.
    assert graph["nodes"]
    t1_evidence = [n for n in graph["nodes"] if n.get("tenant_id") == 1]
    assert t1_evidence
    assert any(str(e.get("document_id")) == "shared-doc" for n in t1_evidence for e in n.get("evidence", []))
    # Tenant 2's node/edge evidence must be gone.
    t2_nodes = [n for n in graph["nodes"] if n.get("tenant_id") == 2]
    assert not any(e.get("document_id") == "shared-doc" for n in t2_nodes for e in n.get("evidence", []))


def test_graph_legacy_records_are_treated_as_tenant_1(tmp_path):
    """Pre-tenant graph records (no tenant_id) belong to legacy tenant 1 only."""
    store = ScopedGraphStore(tmp_path / "graph.json")
    store.replace_document(1, "legacy-doc", _chunks_store()["doc-a"], tenant_id=1)
    # Simulate legacy records written before tenant stamping.
    graph = store._read()
    for node in graph["nodes"]:
        node.pop("tenant_id", None)
    for edge in graph["edges"]:
        edge.pop("tenant_id", None)
    store._write(graph)

    # Tenant 2 cannot purge legacy data (it defaults to tenant 1 ownership).
    store.remove_document_from_tenant_scopes(2, "legacy-doc")
    assert store._read()["nodes"]

    # Tenant 1 CAN purge it.
    store.remove_document_from_tenant_scopes(1, "legacy-doc")
    assert store._read()["nodes"] == []


@pytest.mark.asyncio
async def test_graph_channel_attaches_source_chunk_and_path_metadata(tmp_path):
    store = ScopedGraphStore(tmp_path / "graph.json")
    _index(store)
    channel = GraphChannel(
        ChannelConfig(channel_type=ChannelType.GRAPH, enabled=True),
        graph_store=store,
        chunk_loader=_chunks_store,
    )

    results = await channel.search("OAuth PKCE", knowledge_base_id=1, top_k=5)

    assert len(results) == 1
    assert results[0].source == ChannelType.GRAPH
    assert results[0].metadata["chunk_id"] == "chunk-a"
    assert results[0].metadata["graph"]["entities"]


@pytest.mark.asyncio
async def test_graph_channel_never_uses_the_global_graph_without_a_scope(tmp_path):
    store = ScopedGraphStore(tmp_path / "graph.json")
    _index(store)
    channel = GraphChannel(
        ChannelConfig(channel_type=ChannelType.GRAPH, enabled=True),
        graph_store=store,
        chunk_loader=_chunks_store,
    )

    assert await channel.search("OAuth PKCE", knowledge_base_id=None, top_k=5) == []


@pytest.mark.asyncio
async def test_router_exposes_graph_path_in_scoped_debug_candidates(tmp_path):
    store = ScopedGraphStore(tmp_path / "graph.json")
    _index(store)
    router = QueryRouter()
    router.channel_configs[ChannelType.GRAPH].enabled = True
    router.channels[ChannelType.GRAPH] = GraphChannel(
        router.channel_configs[ChannelType.GRAPH],
        graph_store=store,
        chunk_loader=_chunks_store,
    )

    merged = await router.search(
        "OAuth PKCE relationship",
        knowledge_base_id=1,
        query_type=QueryType.RELATIONSHIP,
        top_k=3,
    )

    assert merged.results[0].metadata["knowledge_base_id"] == 1
    graph_candidate = merged.metadata["channel_candidates"]["graph"][0]
    assert graph_candidate["chunk_id"] == "chunk-a"
    assert graph_candidate["graph"]["paths"]
