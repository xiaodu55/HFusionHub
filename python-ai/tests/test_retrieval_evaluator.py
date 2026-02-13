import json
import math

import pytest

from app.core.rag.query_router import ChannelType, MergedResult, SearchResult
from app.core.rag.retrieval_evaluator import (
    RetrievalCase,
    RetrievalEvaluator,
    load_cases,
)


class FakeRouter:
    async def search(self, query, knowledge_base_id, top_k):
        results = {
            "deployment": [
                SearchResult("foreign", 0.9, ChannelType.VECTOR, metadata={"chunk_id": "foreign", "knowledge_base_id": 2}),
                SearchResult("relevant", 0.8, ChannelType.VECTOR, metadata={"chunk_id": "chunk-a", "knowledge_base_id": 1}),
                SearchResult("duplicate", 0.7, ChannelType.KEYWORD, metadata={"chunk_id": "chunk-a", "knowledge_base_id": 1}),
            ],
            "rollback": [
                SearchResult("relevant", 0.9, ChannelType.VECTOR, metadata={"chunk_id": "chunk-c", "knowledge_base_id": 1}),
            ],
        }[query]
        return MergedResult(results=results[:top_k], total_count=len(results[:top_k]), channels_used=[])


@pytest.mark.asyncio
async def test_evaluator_reports_ranking_metrics_and_scope_violations():
    cases = [
        RetrievalCase("deployment", "deployment", 1, {"chunk-a", "chunk-b"}),
        RetrievalCase("rollback", "rollback", 1, {"chunk-c"}),
    ]

    report = await RetrievalEvaluator(FakeRouter(), top_k=5).evaluate(cases)

    assert report.case_count == 2
    assert report.recall_at_k == pytest.approx(2 / 3)
    assert report.hit_rate_at_k == 1.0
    assert report.mrr_at_k == pytest.approx(0.75)
    expected_first_ndcg = (1 / math.log2(3)) / (1 + 1 / math.log2(3))
    assert report.ndcg_at_k == pytest.approx((expected_first_ndcg + 1) / 2)
    assert report.scope_violation_count == 1
    assert report.cases[0].retrieved_chunk_ids == ["foreign", "chunk-a"]


def test_load_cases_validates_jsonl_and_duplicate_ids(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_text(
        json.dumps({"id": "one", "query": "q", "knowledge_base_id": 7, "relevant_chunk_ids": ["c"]}) + "\n",
        encoding="utf-8",
    )
    assert load_cases(path) == [RetrievalCase("one", "q", 7, {"c"})]

    path.write_text(
        "\n".join([
            json.dumps({"id": "one", "query": "q", "knowledge_base_id": 7, "relevant_chunk_ids": ["c"]}),
            json.dumps({"id": "one", "query": "q2", "knowledge_base_id": 7, "relevant_chunk_ids": ["d"]}),
        ]),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate evaluation case id"):
        load_cases(path)
