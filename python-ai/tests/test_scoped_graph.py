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
