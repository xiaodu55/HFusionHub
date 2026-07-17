"""Mock contract tests for the runtime evaluation track.

These tests exercise the pure, network-free parts of ``scripts/eval_runtime.py``
(plus the shared suite-integrity check) with crafted payloads:

- SHA-256 integrity enforcement
- cross-KB scope violation detection
- request-failure handling
- refusal detection
- tool success/failure
- cost calculation from token usage
- key-fact-backed citation faithfulness
- gate thresholds and exit-code-driving failure list
"""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from eval_baseline import (
    CaseOutcome,
    EvalCase,
    verify_suite_integrity,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUITE_DIR = PROJECT_ROOT / "evaluation" / "suite"
KB_DIR = PROJECT_ROOT / "evaluation" / "kb"

_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "eval_runtime.py"
_spec = importlib.util.spec_from_file_location("eval_runtime_contract", _SCRIPT_PATH)
runtime = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runtime)

KNOWN_TITLES = {"云帆智能智能家居产品目录", "云帆智能订阅方案与价格"}
DOC_TEXT = {
    "云帆智能智能家居产品目录": "智能音箱 S1 支持两个唤醒词 小帆小帆 与 云帆云帆，内置 5W 扬声器。",
    "云帆智能订阅方案与价格": "基础版价格为每月 19 元，提供 30 天云录像。",
}


def _case(case_id="nq-001", expected=("云帆智能智能家居产品目录",),
          facts=("智能音箱 S1 支持两个唤醒词。",), refusal="none", tool=None):
    return EvalCase.from_dict({
        "id": case_id, "category": "normal", "query": "q", "kb_id": 101,
        "expected_chunk_ids": list(expected),
        "expected_document_names": list(expected),
        "key_facts": list(facts),
        "refusal": refusal,
        "risk_labels": [],
        "tool": tool,
    })


def _parse(data, case=None, prices=(0.10, 0.40), threshold=0.5, answer_threshold=0.5):
    return runtime.parse_chat_response(
        data, case if case is not None else _case(),
        prompt_price_per_1m=prices[0],
        completion_price_per_1m=prices[1],
        known_titles=KNOWN_TITLES,
        doc_text_by_title=DOC_TEXT,
        support_threshold=threshold,
        answer_threshold=answer_threshold,
    )


# ---------------------------------------------------------------------------
# Suite integrity (SHA-256)
# ---------------------------------------------------------------------------

def test_verify_suite_integrity_accepts_frozen_suite():
    manifest = verify_suite_integrity(SUITE_DIR / "cases.jsonl", SUITE_DIR / "suite_manifest.json")
    assert manifest["total_cases"] == 220


def test_verify_suite_integrity_rejects_tampered_cases(tmp_path):
    tampered = tmp_path / "cases.jsonl"
    tampered.write_bytes((SUITE_DIR / "cases.jsonl").read_bytes() + b"\n")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_suite_integrity(tampered, SUITE_DIR / "suite_manifest.json")


def test_verify_suite_integrity_rejects_missing_pin(tmp_path):
    cases = tmp_path / "cases.jsonl"
    cases.write_text("{}", encoding="utf-8")
    manifest = tmp_path / "suite_manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="missing cases_sha256"):
        verify_suite_integrity(cases, manifest)


# ---------------------------------------------------------------------------
# Scope violations / cross-KB leak
# ---------------------------------------------------------------------------

def test_scope_violation_detects_foreign_document():
    data = {
        "sources": [
            {"document_name": "云帆智能智能家居产品目录"},
            {"document_name": "某真实客户知识库文档"},  # leaked from another KB
        ]
    }
    assert _parse(data)["scope_violations"] == 1


def test_scope_violation_counts_untitled_source():
    data = {"sources": [{"document_id": 7, "chunk_id": 9}]}
    assert _parse(data)["scope_violations"] == 1


def test_scope_violation_zero_for_known_documents():
    data = {"sources": [{"document_name": "云帆智能智能家居产品目录"},
                        {"title": "云帆智能订阅方案与价格"}]}
    assert _parse(data)["scope_violations"] == 0


def test_scope_violation_detects_same_title_from_other_kb():
    # Same-titled document leaking from another knowledge base must be caught
    # by its authoritative knowledge_base_id, not its (colliding) title.
    data = {"sources": [
        {"document_name": "云帆智能智能家居产品目录", "knowledge_base_id": 999},
    ]}
    assert _parse(data)["scope_violations"] == 1


def test_scope_violation_zero_for_same_kb_with_known_title():
    data = {"sources": [
        {"document_name": "云帆智能智能家居产品目录", "knowledge_base_id": 101},
    ]}
    assert _parse(data)["scope_violations"] == 0


# ---------------------------------------------------------------------------
# Request failure handling
# ---------------------------------------------------------------------------

class _FailingClient:
    async def post(self, *args, **kwargs):
        raise RuntimeError("connection refused")


@pytest.mark.asyncio
async def test_run_case_surfaces_request_exception():
    case = _case(case_id="nq-001")
    headers = {"X-Internal-Token": "t", "Content-Type": "application/json"}
    outcome = await runtime.run_case(
        _FailingClient(), "http://localhost:9000", headers, case,
        prompt_price_per_1m=0.1, completion_price_per_1m=0.4,
        known_titles=KNOWN_TITLES, doc_text_by_title=DOC_TEXT, support_threshold=0.5,
        answer_threshold=0.5,
    )
    assert outcome.error == "connection refused"
    assert outcome.retrieved_chunk_ids == []
    assert outcome.tokens is None


# ---------------------------------------------------------------------------
# Refusal detection
# ---------------------------------------------------------------------------

def test_refusal_detected_for_refusal_required_case():
    case = _case(refusal="required")
    data = {"sources": [], "content": "抱歉，我无法回答该问题。", "status": "completed"}
    assert _parse(data, case)["refusal_correct"] is True


def test_refusal_detected_for_insufficient_evidence():
    case = _case(refusal="required")
    data = {"sources": [], "content": "让我查一下。", "status": "insufficient_evidence"}
    assert _parse(data, case)["refusal_correct"] is True


def test_refusal_not_detected_when_answer_leaks():
    case = _case(refusal="required")
    data = {"sources": [], "content": "系统密码每 90 天更换一次。", "status": "completed"}
    assert _parse(data, case)["refusal_correct"] is False


def test_refusal_na_for_non_refusal_case():
    data = {"sources": [], "content": "答非所问。", "status": "completed"}
    assert _parse(data)["refusal_correct"] is None


# ---------------------------------------------------------------------------
# Tool success / failure
# ---------------------------------------------------------------------------

def test_tool_success_when_invoked_and_completed():
    case = _case(case_id="tl-001", tool={"name": "query_order_logistics"})
    data = {"sources": [], "content": "已完成", "status": "completed",
            "tool_calls_count": 2, "failed_tool": None}
    assert _parse(data, case)["tool_success"] is True


def test_tool_failure_when_tool_failed():
    case = _case(case_id="tl-001", tool={"name": "query_order_logistics"})
    data = {"sources": [], "content": "", "status": "tool_error",
            "tool_calls_count": 1, "failed_tool": "query_order_logistics"}
    assert _parse(data, case)["tool_success"] is False


def test_tool_failure_when_not_invoked():
    case = _case(case_id="tl-001", tool={"name": "query_order_logistics"})
    data = {"sources": [], "content": "抱歉无法执行", "status": "completed",
            "tool_calls_count": 0, "failed_tool": None}
    assert _parse(data, case)["tool_success"] is False


def test_tool_success_na_for_non_tool_case():
    data = {"sources": [], "content": "ok", "status": "completed", "tool_calls_count": 0}
    assert _parse(data)["tool_success"] is None


# ---------------------------------------------------------------------------
# Cost calculation
# ---------------------------------------------------------------------------

def test_cost_calculation_uses_token_usage_and_prices():
    data = {
        "sources": [],
        "content": "ok",
        "token_usage": {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500},
    }
    raw = _parse(data, prices=(1.0, 4.0))  # $1/$4 per 1M tokens
    assert raw["cost_usd"] == pytest.approx((1000 * 1.0 + 500 * 4.0) / 1_000_000)


def test_tokens_falls_back_to_token_count():
    data = {"sources": [], "content": "ok", "token_count": 300}
    assert _parse(data)["tokens"] == 300


# ---------------------------------------------------------------------------
# Key-fact-backed citation faithfulness (answer content + citations)
# ---------------------------------------------------------------------------

def test_runtime_citation_faithfulness_supported_by_cited_doc():
    case = _case(facts=("智能音箱 S1 支持两个唤醒词。",))
    data = {
        "sources": [{"document_name": "云帆智能智能家居产品目录"}],
        "content": "智能音箱 S1 支持两个唤醒词。",
    }
    assert _parse(data, case)["citation_faithfulness"] == pytest.approx(1.0)


def test_runtime_citation_faithfulness_zero_when_uncited():
    case = _case(facts=("智能音箱 S1 支持两个唤醒词。",))
    data = {
        "sources": [],
        "content": "智能音箱 S1 支持两个唤醒词。",
    }
    assert _parse(data, case)["citation_faithfulness"] == pytest.approx(0.0)


def test_runtime_citation_faithfulness_zero_when_wrong_doc():
    case = _case(facts=("智能音箱 S1 支持两个唤醒词。",))
    data = {
        "sources": [{"document_name": "云帆智能订阅方案与价格"}],
        "content": "智能音箱 S1 支持两个唤醒词。",
    }
    assert _parse(data, case)["citation_faithfulness"] == pytest.approx(0.0)


def test_runtime_citation_faithfulness_zero_when_answer_hallucinated():
    # An answer that cites the correct documents but never actually states the
    # key facts (fabricated / off-topic answer) must NOT score full marks.
    case = _case(facts=("智能音箱 S1 支持两个唤醒词。",))
    data = {
        "sources": [{"document_name": "云帆智能智能家居产品目录"}],
        "content": "我们目前没有智能家居产品。",
    }
    assert _parse(data, case)["citation_faithfulness"] == pytest.approx(0.0)


def test_runtime_citation_faithfulness_na_without_key_facts():
    case = _case(facts=())
    data = {"sources": [{"document_name": "云帆智能智能家居产品目录"}]}
    assert _parse(data, case)["citation_faithfulness"] is None


# ---------------------------------------------------------------------------
# Gates and exit-code-driving failure list
# ---------------------------------------------------------------------------

def _args(**overrides):
    defaults = dict(
        minimum_recall=0.85, minimum_ndcg=0.75,
        minimum_citation_accuracy=0.85, minimum_citation_faithfulness=0.60,
        minimum_refusal_correctness=0.90, minimum_tool_success=0.80,
        maximum_p95_latency_ms=3000.0, maximum_error_rate=0.02,
        maximum_scope_violations=0, fail_on_regression=False,
        update_baseline=False,
        baseline=PROJECT_ROOT / "evaluation" / "baseline" / "missing_runtime_baseline.json",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _ok_outcome(scope_violations=0):
    return CaseOutcome(
        case_id="ok", category="normal",
        retrieved_chunk_ids=["云帆智能智能家居产品目录"],
        cited_chunk_ids=["云帆智能智能家居产品目录"],
        expected_chunk_ids=("云帆智能智能家居产品目录",),
        expected_document_names=("云帆智能智能家居产品目录",),
        scope_violations=scope_violations,
        citation_faithfulness=1.0,
        refusal_expected=False, refusal_correct=None,
        tool=None, latency_ms=100.0, tokens=100, cost_usd=0.001, tool_success=None,
    )


def _errored_outcome():
    return CaseOutcome(
        case_id="err", category="normal", retrieved_chunk_ids=[], cited_chunk_ids=[],
        expected_chunk_ids=(), expected_document_names=(),
        scope_violations=0, citation_faithfulness=None,
        refusal_expected=False, refusal_correct=None,
        tool=None, error="timeout",
    )


def test_gate_failures_include_error_rate_for_mass_failures():
    report, failures = runtime.build_report_and_failures(
        _args(), [], {"category_counts": {}}, [_ok_outcome(), _errored_outcome()], "now"
    )
    assert report.metrics.error_rate == pytest.approx(0.5)
    assert any("错误率" in f for f in failures)


def test_gate_failures_include_scope_violations():
    report, failures = runtime.build_report_and_failures(
        _args(), [], {"category_counts": {}}, [_ok_outcome(scope_violations=3)], "now"
    )
    assert report.metrics.scope_violations == 3
    assert any("越界" in f for f in failures)


def test_gate_failures_empty_for_healthy_run():
    _, failures = runtime.build_report_and_failures(
        _args(), [], {"category_counts": {}}, [_ok_outcome()], "now"
    )
    assert failures == []


def test_gate_failure_drives_nonzero_exit_semantics():
    # build_report_and_failures failures list is what main() maps to exit code 1.
    report, failures = runtime.build_report_and_failures(
        _args(), [], {"category_counts": {}}, [_ok_outcome(scope_violations=3)], "now"
    )
    assert report.gate_failures == failures
    assert failures, "scope violation must fail the gate"


def test_runtime_report_track_is_runtime():
    report, _ = runtime.build_report_and_failures(
        _args(), [], {"category_counts": {}}, [_ok_outcome()], "now"
    )
    assert report.track == "runtime"
    assert report.metrics.p95_latency_ms == pytest.approx(100.0)


def test_runtime_report_rejects_baseline_from_other_suite(tmp_path):
    baseline_path = tmp_path / "runtime_baseline.json"
    baseline_path.write_text(json.dumps({
        "track": "runtime",
        "suite_sha256": "sha-old",
        "metrics": {"recall_at_5": 0.95},
    }), encoding="utf-8")
    suite_manifest = {"category_counts": {}, "cases_sha256": "sha-new"}
    with pytest.raises(ValueError, match="re-run with --update-baseline"):
        runtime.build_report_and_failures(
            _args(baseline=baseline_path), [], suite_manifest, [_ok_outcome()], "now"
        )


def test_runtime_report_accepts_baseline_from_same_suite(tmp_path):
    baseline_path = tmp_path / "runtime_baseline.json"
    baseline_path.write_text(json.dumps({
        "track": "runtime",
        "suite_sha256": "sha-new",
        "metrics": {"recall_at_5": 0.95},
    }), encoding="utf-8")
    suite_manifest = {"category_counts": {}, "cases_sha256": "sha-new"}
    report, _ = runtime.build_report_and_failures(
        _args(baseline=baseline_path), [], suite_manifest, [_ok_outcome()], "now"
    )
    assert report.baseline_metrics["recall_at_5"] == pytest.approx(0.95)
