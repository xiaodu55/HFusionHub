import pytest

from app.core.rag.reranker import (
    DisabledReranker,
    LexicalReranker,
    _get_configured_reranker,
    _resolve_reranker,
)


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


# ── 上线后的解析与降级行为 ─────────────────────────────────────────

def test_resolve_reranker_flag_off_returns_disabled():
    reranker = _resolve_reranker(flag_enabled=False, mode="lexical", model_name="x")
    assert reranker.name == "disabled"
    assert reranker.reason == "rag.reranker.enabled is OFF via feature flag"


def test_resolve_reranker_flag_on_lexical_mode():
    reranker = _resolve_reranker(flag_enabled=True, mode="lexical", model_name="x")
    assert isinstance(reranker, LexicalReranker)


def test_resolve_reranker_empty_or_disabled_mode_maps_to_lexical():
    for mode in ("", "disabled", "off", "none"):
        reranker = _resolve_reranker(flag_enabled=True, mode=mode, model_name="x")
        assert isinstance(reranker, LexicalReranker), mode


def test_resolve_reranker_unsupported_mode_is_disabled():
    reranker = _resolve_reranker(flag_enabled=True, mode="bogus", model_name="x")
    assert reranker.name == "disabled"
    assert "unsupported_mode" in reranker.reason


def test_cross_encoder_falls_back_when_library_missing(monkeypatch):
    """Without sentence-transformers available, cross_encoder must degrade to
    DisabledReranker with an observable reason — never an outage, and never a
    silent no-op pretending to have reranked."""
    import sys
    # Force the import to fail regardless of whether the lib is installed, and
    # use a distinct model name so a cached real instance can't leak in.
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    reranker = _get_configured_reranker("cross_encoder", "__unittest_fake_model__")
    assert reranker.name == "disabled"
    assert "cross_encoder_unavailable" in reranker.reason


def test_get_reranker_caches_resolution():
    """The same (flag, mode, model) triple must return the identical cached
    instance — config parsing happens once, not per retrieval."""
    first = _resolve_reranker(True, "lexical", "model-x")
    second = _resolve_reranker(True, "lexical", "model-x")
    assert first is second
