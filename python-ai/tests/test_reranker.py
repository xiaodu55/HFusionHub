import pytest

from app.core.rag.reranker import DisabledReranker, LexicalReranker


@pytest.mark.asyncio
async def test_lexical_reranker_promotes_better_term_coverage():
    reranker = LexicalReranker()
    results, debug = await reranker.rerank("hybrid retrieval", [
        {"content": "retrieval only", "score": 0.99, "metadata": {}},
        {"content": "hybrid retrieval combines vector and BM25", "score": 0.20, "metadata": {}},
    ])

    assert debug["applied"] is True
    assert results[0]["content"].startswith("hybrid retrieval")
    assert results[0]["metadata"]["reranker"] == "lexical"


@pytest.mark.asyncio
async def test_disabled_reranker_preserves_first_stage_order():
    candidates = [{"content": "first", "score": 0.2}, {"content": "second", "score": 0.1}]
    results, debug = await DisabledReranker().rerank("anything", candidates)

    assert results == candidates
    assert debug == {"applied": False, "reranker": "disabled", "reason": "disabled"}
