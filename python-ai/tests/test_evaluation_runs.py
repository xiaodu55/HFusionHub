from app.core.rag.evaluation_runs import EvaluationRunStore


def _report(recall: float = 1.0):
    return {
        "summary": {
            "top_k": 5,
            "case_count": 2,
            "precision_at_k": 0.8,
            "recall_at_k": recall,
            "mean_reciprocal_rank": 0.75,
        },
        "cases": [
            {"case_id": "pass", "recall_at_k": 1.0, "query": "do not persist me"},
            {"case_id": "miss", "recall_at_k": recall, "query": "nor me"},
        ],
    }


def test_evaluation_run_store_persists_sanitized_history(tmp_path):
    database_path = tmp_path / "evaluation-runs.db"
    store = EvaluationRunStore(str(database_path))

    recorded = store.record(_report(recall=0.0), knowledge_base_id=8, label="release candidate")
    reloaded = EvaluationRunStore(str(database_path)).list(knowledge_base_id=8)

    assert recorded.failed_case_ids == ["miss"]
    assert len(reloaded) == 1
    assert reloaded[0]["label"] == "release candidate"
    assert reloaded[0]["failed_case_ids"] == ["miss"]
    assert "query" not in reloaded[0]


def test_evaluation_run_store_filters_by_knowledge_base(tmp_path):
    store = EvaluationRunStore(str(tmp_path / "evaluation-runs.db"))
    store.record(_report(), knowledge_base_id=1)
    store.record(_report(), knowledge_base_id=2)

    assert len(store.list(knowledge_base_id=1)) == 1
    assert store.list(knowledge_base_id=1)[0]["knowledge_base_id"] == 1
