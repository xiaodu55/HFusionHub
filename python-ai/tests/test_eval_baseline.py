"""Tests for the Phase-1 evaluation baseline:

- suite build determinism and reference validity
- fixed-format metric aggregation
- baseline diff / regression detection
- hermetic synthetic router determinism
"""

import hashlib
import importlib.util
import json
import math
from pathlib import Path

import pytest

from app.core.rag.eval_baseline import (
    CaseOutcome,
    Metrics,
    aggregate_metrics,
    check_gates,
    compute_citation_faithfulness,
    diff_against_baseline,
    load_baseline,
    load_cases,
    save_baseline,
)
from app.core.rag.synthetic_index import (
    SyntheticIndex,
    SyntheticRouter,
    _extract_sections,
    tokenize,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # python-ai/
SUITE_DIR = PROJECT_ROOT / "evaluation" / "suite"
KB_DIR = PROJECT_ROOT / "evaluation" / "kb"


def _load_module(name: str, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Suite construction
# ---------------------------------------------------------------------------

def test_suite_has_required_size_and_categories():
    suite_manifest = json.loads((SUITE_DIR / "suite_manifest.json").read_text(encoding="utf-8"))
    assert suite_manifest["total_cases"] >= 200
    counts = suite_manifest["category_counts"]
    assert counts["normal"] >= 15
    assert counts["cross_document"] >= 15
    assert counts["refusal"] >= 15
    assert counts["permission"] >= 15
    assert counts["injection"] >= 15
    assert counts["tool"] >= 15
    assert counts["long_document"] >= 15


def test_cases_file_is_pinned_by_suite_manifest():
    suite_manifest = json.loads((SUITE_DIR / "suite_manifest.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256((SUITE_DIR / "cases.jsonl").read_bytes()).hexdigest()
    assert digest == suite_manifest["cases_sha256"]


def test_cases_file_is_deterministic_after_rebuild(tmp_path):
    build_suite = _load_module("build_suite", SUITE_DIR / "build_suite.py")
    manifest = json.loads((KB_DIR / "kb_manifest.json").read_text(encoding="utf-8"))
    definitions = _load_module(
        "suite_definitions", SUITE_DIR / "suite_definitions.py"
    )
    cases, _ = build_suite.validate(definitions, manifest)
    assert len(cases) >= 200

    rebuild_path = tmp_path / "rebuild.jsonl"
    build_suite.emit_cases(cases, rebuild_path)
    assert hashlib.sha256(rebuild_path.read_bytes()).hexdigest() == hashlib.sha256(
        (SUITE_DIR / "cases.jsonl").read_bytes()
    ).hexdigest()


def test_all_expected_chunks_exist_in_kb_manifest():
    kb_manifest = json.loads((KB_DIR / "kb_manifest.json").read_text(encoding="utf-8"))
    sections = {
        (doc["doc_id"], section["section_id"])
        for doc in kb_manifest["documents"]
        for section in doc["sections"]
    }
    cases = load_cases(SUITE_DIR / "cases.jsonl")
    for case in cases:
        for chunk in case.expected_chunk_ids:
            doc_id, _, section_id = chunk.partition("#")
            assert (doc_id, section_id) in sections, f"{case.case_id}: {chunk}"


def test_load_cases_rejects_duplicates(tmp_path):
    path = tmp_path / "cases.jsonl"
    line = json.dumps({
        "id": "x-1", "category": "normal", "query": "q", "kb_id": 101,
        "expected_chunk_ids": ["a#b"], "expected_document_names": ["doc"],
    })
    path.write_text(line + "\n" + line, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate evaluation case id"):
        load_cases(path)


def test_load_cases_rejects_missing_fields(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps({"id": "x-1", "query": "q"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing fields"):
        load_cases(path)


# ---------------------------------------------------------------------------
# Synthetic index determinism
# ---------------------------------------------------------------------------

def test_tokenize_is_deterministic():
    text = "智能音箱 S1 支持蓝牙 5.2 与 Wi-Fi 2.4G"
    assert tokenize(text) == tokenize(text)
    assert tokenize(text)
    assert "s1" in tokenize(text)


def test_extract_sections_from_markdown():
    md = "# Doc\n\n## [one] Title A\nbody one\n\n## [two] Title B\nbody two\n"
    sections = _extract_sections(md)
    assert sections == [("one", "Title A\nbody one"), ("two", "Title B\nbody two")]


@pytest.mark.asyncio
async def test_synthetic_router_is_deterministic_and_scoped():
    index = SyntheticIndex()
    router = SyntheticRouter(index=index)
    merged = await router.search("智能音箱 S1 支持哪些唤醒词", index.kb_id, 10)
    first = [(r.metadata["chunk_id"], r.score) for r in merged.results]
    merged_again = await router.search("智能音箱 S1 支持哪些唤醒词", index.kb_id, 10)
    assert first == [(r.metadata["chunk_id"], r.score) for r in merged_again.results]
    assert first[0][0] == "product-catalog#smart-speaker"
    assert all(r.metadata["knowledge_base_id"] == index.kb_id for r in merged.results)


@pytest.mark.asyncio
async def test_synthetic_router_returns_empty_for_foreign_kb():
    router = SyntheticRouter()
    merged = await router.search("任意查询", 999, 5)
    assert merged.results == []


def test_known_queries_retrieve_their_ground_truth():
    index = SyntheticIndex()
    cases = load_cases(SUITE_DIR / "cases.jsonl")
    checked = 0
    for case in cases:
        if not case.expected_chunk_ids or case.category not in ("normal", "long_document"):
            continue
        retrieved = [r.metadata["chunk_id"] for r in index.search_ranked(case.query, 101, 5)]
        assert set(case.expected_chunk_ids) & set(retrieved), case.case_id
        checked += 1
        if checked >= 20:
            break
    assert checked == 20


# ---------------------------------------------------------------------------
# Metrics aggregation
# ---------------------------------------------------------------------------

def _outcome(case_id="c1", category="normal", retrieved=None, expected=None,
             cited=None, faithfulness=None, refusal_expected=False,
             refusal_correct=None, tool=None, tool_success=None,
             latency=None, tokens=None, cost=None, error=None):
    return CaseOutcome(
        case_id=case_id,
        category=category,
        retrieved_chunk_ids=retrieved or [],
        expected_chunk_ids=tuple(expected or []),
        expected_document_names=tuple(),
        scope_violations=0,
        citation_faithfulness=faithfulness,
        refusal_expected=refusal_expected,
        refusal_correct=refusal_correct,
        tool=tool,
        cited_chunk_ids=cited or [],
        latency_ms=latency,
        tokens=tokens,
        cost_usd=cost,
        tool_success=tool_success,
        error=error,
    )


def test_aggregate_metrics_computes_fixed_format_fields():
    outcomes = [
        _outcome("a", retrieved=["x1", "x2", "x3"], expected=["x1"],
                 cited=["x1", "x2"], faithfulness=1 / 2,
                 latency=100, tokens=500, cost=0.001),
        _outcome("b", retrieved=["y1", "y2", "y3"], expected=["y1", "y2"],
                 cited=["y1"], faithfulness=1.0,
                 latency=300, tokens=700, cost=0.002),
        _outcome("c", retrieved=["z1"], expected=[], cited=[], faithfulness=None,
                 latency=200, tokens=300, cost=0.001),
    ]
    metrics = aggregate_metrics(outcomes, top_k=10)
    # recall@5: (1 + 2) / 3 expected chunks
    assert metrics.recall_at_5 == pytest.approx(1.0)
    # citation accuracy over cases with expected chunks: 2/2
    assert metrics.citation_accuracy == pytest.approx(1.0)
    # mean citation faithfulness over non-null: (0.5 + 1.0)/2
    assert metrics.citation_faithfulness == pytest.approx(0.75)
    # latencies [100, 200, 300]
    assert metrics.p50_latency_ms == pytest.approx(200)
    assert metrics.p95_latency_ms == pytest.approx(300)
    assert metrics.tokens_per_task == pytest.approx(500)
    assert metrics.cost_usd_per_task == pytest.approx((0.001 + 0.002 + 0.001) / 3)
    assert metrics.error_rate == 0.0


def test_aggregate_metrics_refusal_and_tool():
    outcomes = [
        _outcome("r1", refusal_expected=True, refusal_correct=True),
        _outcome("r2", refusal_expected=True, refusal_correct=False),
        _outcome("t1", tool={"name": "x"}, tool_success=True),
        _outcome("t2", tool={"name": "x"}, tool_success=False),
        _outcome("n1"),
    ]
    metrics = aggregate_metrics(outcomes)
    assert metrics.refusal_correctness == pytest.approx(0.5)
    assert metrics.tool_success_rate == pytest.approx(0.5)


def test_ndcg_math():
    # expected {a, b, c}; retrieved ranks: a@1 (hit), d@2 (miss), c@3 (hit), b@4 (hit)
    outcomes = [
        _outcome("x", retrieved=["a", "d", "c", "b"], expected=["a", "b", "c"]),
    ]
    metrics = aggregate_metrics(outcomes, top_k=10)
    dcg = 1 + 1 / math.log2(4) + 1 / math.log2(5)
    ideal_dcg = 1 + 1 / math.log2(3) + 1 / math.log2(4)
    assert metrics.ndcg_at_10 == pytest.approx(dcg / ideal_dcg)


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

def test_check_gates_respects_direction():
    metrics = Metrics(recall_at_5=0.9, ndcg_at_10=0.7, p95_latency_ms=2500, error_rate=0.01)
    failures = check_gates(metrics, {
        "recall_at_5": 0.95,        # higher is better -> fail
        "ndcg_at_10": 0.60,         # pass
        "p95_latency_ms": 2000,     # lower is better -> fail
        "error_rate": 0.05,         # pass
    })
    assert any("Recall@5" in f for f in failures)
    assert any("P95" in f for f in failures)
    assert len(failures) == 2


def test_check_gates_skips_none_metrics():
    metrics = Metrics(recall_at_5=None, refusal_correctness=None)
    failures = check_gates(metrics, {"recall_at_5": 0.9, "refusal_correctness": 0.9})
    assert failures == []


# ---------------------------------------------------------------------------
# Baseline diff
# ---------------------------------------------------------------------------

def test_diff_against_baseline_detects_quality_regression():
    baseline = {"recall_at_5": 0.95, "ndcg_at_10": 0.90}
    current = Metrics(recall_at_5=0.88, ndcg_at_10=0.90)  # recall dropped 0.07
    deltas, regressions = diff_against_baseline(current, baseline)
    assert deltas["recall_at_5"] == pytest.approx(-0.07)
    assert any("Recall@5" in r for r in regressions)
    assert deltas["ndcg_at_10"] == pytest.approx(0.0)
    assert not any("ndcg_at_10" in r for r in regressions)


def test_diff_against_baseline_allows_small_drop_within_tolerance():
    baseline = {"recall_at_5": 0.95}
    current = Metrics(recall_at_5=0.93)  # drop 0.02 < tolerance 0.03
    _, regressions = diff_against_baseline(current, baseline)
    assert regressions == []


def test_diff_against_baseline_detects_latency_and_cost_increases():
    baseline = {"p95_latency_ms": 1000.0, "tokens_per_task": 500.0}
    current = Metrics(p95_latency_ms=1400.0, tokens_per_task=600.0)
    deltas, regressions = diff_against_baseline(current, baseline)
    # p95 +40% > 20% tolerance
    assert any("P95" in r for r in regressions)
    # tokens +20% > 15% tolerance
    assert any("Token" in r for r in regressions)
    assert deltas["p95_latency_ms"] == pytest.approx(400.0)


def test_baseline_round_trip(tmp_path):
    path = tmp_path / "baseline.json"
    metrics = Metrics(recall_at_5=0.93, p95_latency_ms=1200.0, refusal_correctness=None)
    save_baseline(metrics, path, track="offline", suite_version="1.0.0",
                  kb_version="1.0.0", suite_sha256="sha-abc", generated_at="now")
    loaded = load_baseline(path, required_suite_sha256="sha-abc")
    assert loaded["recall_at_5"] == pytest.approx(0.93)
    assert loaded["p95_latency_ms"] == pytest.approx(1200.0)
    assert loaded["refusal_correctness"] is None


def test_load_baseline_returns_none_when_absent(tmp_path):
    assert load_baseline(tmp_path / "missing.json") is None


def test_load_baseline_rejects_mismatched_suite_sha(tmp_path):
    path = tmp_path / "baseline.json"
    metrics = Metrics(recall_at_5=0.93)
    save_baseline(metrics, path, track="offline", suite_version="1.0.0",
                  kb_version="1.0.0", suite_sha256="sha-old", generated_at="now")
    with pytest.raises(ValueError, match="re-run with --update-baseline"):
        load_baseline(path, required_suite_sha256="sha-new")


def test_load_baseline_rejects_unpinned_baseline(tmp_path):
    # A baseline recorded before the pin existed must not silently compare.
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"metrics": {"recall_at_5": 0.93}}), encoding="utf-8")
    with pytest.raises(ValueError, match="unpinned"):
        load_baseline(path, required_suite_sha256="sha-new")


def test_load_baseline_ignores_sha_when_not_required(tmp_path):
    path = tmp_path / "baseline.json"
    metrics = Metrics(recall_at_5=0.93)
    save_baseline(metrics, path, track="offline", suite_version="1.0.0",
                  kb_version="1.0.0", suite_sha256="sha-old", generated_at="now")
    assert load_baseline(path)["recall_at_5"] == pytest.approx(0.93)


def test_citation_faithfulness_edge_cases():
    assert compute_citation_faithfulness([], ["a#b"]) is None
    assert compute_citation_faithfulness(["a#b", "x#y"], []) is None
    assert compute_citation_faithfulness(["a#b", "x#y"], ["a#b", "c#d"]) == pytest.approx(0.5)
