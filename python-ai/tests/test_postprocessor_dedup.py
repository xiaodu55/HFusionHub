"""Tests for the near-linear token-Jaccard dedup (MinHash + LSH banding, P5)."""

from app.core.rag.postprocessor import Postprocessor


def _result(content, score=0.8, cid="c"):
    return {
        "content": content,
        "score": score,
        "document_id": "d",
        "metadata": {"chunk_id": cid, "evidence_score": 0.9},
    }


def test_exact_duplicates_are_deduplicated():
    text = "深度学习是机器学习的一个分支，它使用多层神经网络来学习数据的表示。"
    pp = Postprocessor(dedup_threshold=0.95)
    out, decisions = pp.process_with_debug(
        [_result(text, score=0.9, cid="a"), _result(text, score=0.8, cid="b")],
        top_k=5,
    )
    assert len(out) == 1
    assert decisions[0]["decision"] == "accepted"
    assert decisions[1]["decision"] == "filtered_duplicate"
    assert decisions[1]["duplicate_of_input_rank"] == 1


def test_near_duplicates_are_deduplicated_via_signatures():
    # Distinct CJK single-char tokens, one extra char in the second chunk.
    # Content differs (so the fingerprint fast path is bypassed) but shingle
    # Jaccard is 40/41 ≈ 0.976 > 0.95 → caught via LSH band candidates.
    base = "".join(chr(0x4E00 + i) for i in range(40))
    variant = base + chr(0x4E00 + 50)
    pp = Postprocessor(dedup_threshold=0.95)
    out, decisions = pp.process_with_debug(
        [_result(base, score=0.9, cid="a"), _result(variant, score=0.8, cid="b")],
        top_k=5,
    )
    assert len(out) == 1
    assert decisions[1]["decision"] == "filtered_duplicate"


def test_unrelated_content_is_not_deduplicated():
    a = "深度学习使用多层神经网络进行特征学习。"
    b = "今天北京的天气很好，适合出去散步。"
    pp = Postprocessor(dedup_threshold=0.95)
    out, decisions = pp.process_with_debug(
        [_result(a, score=0.9, cid="a"), _result(b, score=0.8, cid="b")],
        top_k=5,
    )
    assert len(out) == 2
    assert decisions[0]["decision"] == "accepted"
    assert decisions[1]["decision"] == "accepted"


def test_similarity_uses_shingles_not_raw_characters():
    pp = Postprocessor()
    # Identical character sets but different ordering: raw character-set
    # Jaccard would score 0.5; shingle Jaccard must be near zero.
    a = "的" * 10
    b = "的是" * 5
    assert pp._calculate_similarity(a, b) < 0.5
