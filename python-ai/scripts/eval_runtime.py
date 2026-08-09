#!/usr/bin/env python
"""Runtime evaluation track (Nightly/Staging).

Runs the frozen Phase-1 suite against the live Python AI service and produces
the same fixed-format report as the offline track, with the answer-layer
metrics filled in: P95/P50/avg latency, tokens per task, cost per task,
refusal correctness and tool success rate.

Guarantees:
- the frozen ``cases.jsonl`` is SHA-256 verified against ``suite_manifest.json``
  before any request is sent (see ``verify_suite_integrity``);
- the baseline is bound to the frozen suite's ``cases_sha256`` — a baseline from
  a different suite refuses to compare (``--update-baseline`` re-freezes);
- cross-KB scope violations are detected by the source's authoritative
  ``knowledge_base_id`` (a same-titled document leaked from another KB is still
  a violation); sources without a KB id fall back to the title check;
- ``error_rate`` is gated, so mass request failures exit non-zero;
- runtime citation faithfulness is backed by ``key_facts`` AND the answer text:
  a key fact scores only when the answer actually states it AND a cited
  document supports it (a fabricated answer citing the right docs scores 0).

Cost is derived from the ``token_usage`` response using configurable
per-1M-token prices (no price data exists in the service today).

Usage:
    python scripts/eval_runtime.py --token <internal-token> [--base-url http://localhost:9000]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
# 显式插入脚本目录：PYTHONSAFEPATH=1（python -P）会取消脚本目录自动入表
for _path in (str(SCRIPTS_DIR), str(PROJECT_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from eval_baseline import (  # noqa: E402
    CaseOutcome,
    EvaluationReport,
    aggregate_metrics,
    check_gates,
    diff_against_baseline,
    load_baseline,
    load_cases,
    render_markdown,
    runtime_citation_faithfulness,
    save_baseline,
    verify_suite_integrity,
)

SUITE_DIR = PROJECT_ROOT / "evaluation" / "suite"
REPORT_DIR = PROJECT_ROOT / "evaluation" / "reports"
BASELINE_DIR = PROJECT_ROOT / "evaluation" / "baseline"

_REFUSAL_MARKERS = (
    "无法回答", "无法提供", "不能提供", "无法确认", "抱歉", "拒绝回答",
    "没有相关信息", "无权", "不在我的", "无法满足", "不能回答",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token", required=True, help="X-Internal-Token for the Python AI service")
    parser.add_argument("--tenant-id", type=int, default=1,
                        help="X-Tenant-Id for multi-tenant fail-closed resolution (eval-nightly 的 EVAL_TENANT_ID)")
    parser.add_argument("--base-url", default="http://localhost:9000")
    parser.add_argument("--cases", type=Path, default=SUITE_DIR / "cases.jsonl")
    parser.add_argument("--suite-manifest", type=Path, default=SUITE_DIR / "suite_manifest.json")
    parser.add_argument("--kb-manifest", type=Path,
                        default=PROJECT_ROOT / "evaluation" / "kb" / "kb_manifest.json",
                        help="synthetic KB manifest used for scope/citation checks")
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--markdown", type=Path, default=None)
    parser.add_argument("--baseline", type=Path, default=None)
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--prompt-price-per-1m", type=float, default=0.10,
                        help="USD per 1M prompt tokens")
    parser.add_argument("--completion-price-per-1m", type=float, default=0.40,
                        help="USD per 1M completion tokens")
    parser.add_argument("--concurrency", type=int, default=4,
                        help="bounded number of concurrent /api/chat requests")
    parser.add_argument("--support-threshold", type=float, default=0.5,
                        help="fraction of a key fact's tokens that must appear in cited text")
    parser.add_argument("--answer-threshold", type=float, default=0.5,
                        help="fraction of a key fact's tokens that must appear in the answer text")
    parser.add_argument("--minimum-recall", type=float, default=0.85)
    parser.add_argument("--minimum-ndcg", type=float, default=0.75)
    parser.add_argument("--minimum-citation-accuracy", type=float, default=0.85)
    parser.add_argument("--minimum-citation-faithfulness", type=float, default=0.60)
    parser.add_argument("--minimum-refusal-correctness", type=float, default=0.90)
    parser.add_argument("--minimum-tool-success", type=float, default=0.80)
    parser.add_argument("--maximum-p95-latency-ms", type=float, default=3000.0)
    parser.add_argument("--maximum-error-rate", type=float, default=0.02)
    parser.add_argument("--maximum-scope-violations", type=int, default=0)
    parser.add_argument("--fail-on-regression", action="store_true")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Pure, testable helpers
# ---------------------------------------------------------------------------

def _doc_name(source: dict) -> str:
    return str(source.get("document_name") or source.get("title") or "").strip()


def cited_docs_from_response(data: dict, sources: list) -> list[str]:
    """A3 引用对齐：答案实际标注的引用（cited_chunk_ids）→ 文档名列表。

    响应的 ``cited_chunk_ids`` 是答案用 ``[n]`` 标注实际引用的 chunk 级 id
    （由 react 管线解析答案文本得到），经响应 ``sources`` 列表映射回文档名。
    响应未携带该字段（旧服务/未标注）时返回空列表，调用方回退检索集，
    保持 A3 之前的行为。
    """
    chunk_to_name: dict[str, str] = {}
    for source in sources:
        chunk_id = str(source.get("chunk_id") or "")
        name = _doc_name(source)
        if chunk_id and name:
            chunk_to_name.setdefault(chunk_id, name)
    cited: list[str] = []
    for cid in data.get("cited_chunk_ids") or []:
        name = chunk_to_name.get(str(cid))
        if name and name not in cited:
            cited.append(name)
    return cited


def _detect_refusal(answer: str, status: str) -> bool:
    if status == "insufficient_evidence":
        return True
    return any(marker in answer for marker in _REFUSAL_MARKERS)


def load_kb_docs(kb_manifest_path: Any) -> tuple[set[str], dict[str, str]]:
    """Return ``(known_document_titles, doc_text_by_title)`` for the synthetic KB."""
    manifest = json.loads(Path(kb_manifest_path).read_text(encoding="utf-8"))
    base_dir = Path(kb_manifest_path).parent
    known_titles: set[str] = set()
    doc_text_by_title: dict[str, str] = {}
    for doc in manifest["documents"]:
        title = str(doc["title"])
        known_titles.add(title)
        text = (base_dir / doc["filename"]).read_text(encoding="utf-8")
        doc_text_by_title.setdefault(title, "")
        doc_text_by_title[title] += "\n" + text
    return known_titles, doc_text_by_title


def compute_scope_violations(
    sources: list[dict], known_titles: set[str], kb_id: int
) -> int:
    """A scope violation is a cited source that escaped the expected knowledge
    base.  A source carrying an authoritative ``knowledge_base_id`` is judged on
    that identity (so a same-titled document from another KB is detected even
    when its title collides with the synthetic KB); otherwise it falls back to
    the title check (title missing or not part of the synthetic KB)."""
    violations = 0
    for source in sources:
        source_kb = source.get("knowledge_base_id")
        if source_kb is not None:
            try:
                source_kb = int(source_kb)
            except (TypeError, ValueError):
                source_kb = None
            if source_kb != kb_id:
                violations += 1
                continue
        name = _doc_name(source)
        if not name or name not in known_titles:
            violations += 1
    return violations


def parse_chat_response(
    data: dict,
    case,
    *,
    prompt_price_per_1m: float,
    completion_price_per_1m: float,
    known_titles: set[str],
    doc_text_by_title: dict[str, str],
    support_threshold: float,
    answer_threshold: float,
) -> dict:
    """Turn a ``/api/chat`` response into a ``CaseOutcome`` raw dict.

    Pure: no I/O, no network — fully testable with crafted payloads.
    """
    sources = data.get("sources") or []
    retrieved_docs: list[str] = []
    for source in sources:
        name = _doc_name(source)
        if name and name not in retrieved_docs:
            retrieved_docs.append(name)

    token_usage = data.get("token_usage") or {}
    prompt_tokens = int(token_usage.get("prompt_tokens", 0) or 0)
    completion_tokens = int(token_usage.get("completion_tokens", 0) or 0)
    total_tokens = int(token_usage.get("total_tokens", 0) or data.get("token_count", 0) or 0)

    expected_docs = list(case.expected_document_names)
    status = str(data.get("status", "completed"))
    answer = str(data.get("content") or data.get("answer") or "")
    failed_tool = data.get("failed_tool")
    tool_calls_count = int(data.get("tool_calls_count", 0) or 0)

    # A3 引用对齐：优先用答案实际标注的引用；未标注（空）回退检索集
    cited_docs = cited_docs_from_response(data, sources) or retrieved_docs

    return {
        "case_id": case.case_id,
        "category": case.category,
        "retrieved_chunk_ids": retrieved_docs,
        "cited_chunk_ids": cited_docs,
        "expected_chunk_ids": tuple(expected_docs),
        "expected_document_names": tuple(expected_docs),
        "scope_violations": compute_scope_violations(sources, known_titles, case.kb_id),
        "citation_faithfulness": runtime_citation_faithfulness(
            answer, cited_docs, case.key_facts, doc_text_by_title,
            support_threshold=support_threshold,
            answer_threshold=answer_threshold,
        ),
        "refusal_expected": case.refusal == "required",
        "refusal_correct": (
            _detect_refusal(answer, status) if case.refusal == "required" else None
        ),
        "tool": case.tool,
        "latency_ms": 0.0,  # filled by run_case after measuring
        "tokens": total_tokens,
        "cost_usd": (
            (prompt_tokens * prompt_price_per_1m
             + completion_tokens * completion_price_per_1m) / 1_000_000
        ),
        "tool_success": (
            bool(tool_calls_count > 0 and failed_tool is None and status == "completed")
            if case.tool is not None else None
        ),
    }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_case(client: httpx.AsyncClient, base_url: str, headers: dict, case, *,
                   prompt_price_per_1m: float, completion_price_per_1m: float,
                   known_titles: set[str], doc_text_by_title: dict[str, str],
                   support_threshold: float, answer_threshold: float) -> CaseOutcome:
    start = time.perf_counter()
    try:
        resp = await client.post(
            f"{base_url}/api/chat",
            json={"message": case.query, "knowledge_base_id": case.kb_id, "stream": False},
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        raw = parse_chat_response(
            data, case,
            prompt_price_per_1m=prompt_price_per_1m,
            completion_price_per_1m=completion_price_per_1m,
            known_titles=known_titles,
            doc_text_by_title=doc_text_by_title,
            support_threshold=support_threshold,
            answer_threshold=answer_threshold,
        )
        raw["latency_ms"] = (time.perf_counter() - start) * 1000
        return CaseOutcome(**raw)
    except Exception as exc:  # noqa: BLE001
        return CaseOutcome(
            case_id=case.case_id,
            category=case.category,
            retrieved_chunk_ids=[],
            cited_chunk_ids=[],
            expected_chunk_ids=tuple(case.expected_document_names),
            expected_document_names=tuple(case.expected_document_names),
            scope_violations=0,
            citation_faithfulness=None,
            refusal_expected=case.refusal == "required",
            refusal_correct=None,
            tool=case.tool,
            error=str(exc),
        )


async def run_all(args) -> list[CaseOutcome]:
    cases = load_cases(args.cases)
    known_titles, doc_text_by_title = load_kb_docs(args.kb_manifest)
    headers = {
        "X-Internal-Token": args.token,
        # 多租户 fail-closed：缺租户头会被服务端整体拒绝（A4 排障发现）
        "X-Tenant-Id": str(getattr(args, "tenant_id", 1) or 1),
        "Content-Type": "application/json",
    }
    semaphore = asyncio.Semaphore(max(1, args.concurrency))

    async def worker(case) -> CaseOutcome:
        async with semaphore:
            # 60s 对"RAG 检索 + LLM 生成"的全链路偏紧（DeepSeek 高峰 30-90s），
            # 超时会被记成 error 污染 error_rate 门禁
            async with httpx.AsyncClient(timeout=180.0) as client:
                outcome = await run_case(
                    client, args.base_url, headers, case,
                    prompt_price_per_1m=args.prompt_price_per_1m,
                    completion_price_per_1m=args.completion_price_per_1m,
                    known_titles=known_titles,
                    doc_text_by_title=doc_text_by_title,
                    support_threshold=args.support_threshold,
                    answer_threshold=args.answer_threshold,
                )
        status = "ERR" if outcome.error else "ok"
        print(f"  {case.case_id:>8} {status} ({case.query[:40]})", flush=True)
        return outcome

    return await asyncio.gather(*(worker(case) for case in cases))


# ---------------------------------------------------------------------------
# Report assembly (pure; drives gate + exit-code logic)
# ---------------------------------------------------------------------------

def build_report_and_failures(args, cases, suite_manifest, outcomes, now: str):
    """Assemble the report, compute gates and return ``(report, failures)``."""
    metrics = aggregate_metrics(outcomes, top_k=10, exclude_refusal_from_citation=True)
    thresholds = {
        "recall_at_5": args.minimum_recall,
        "ndcg_at_10": args.minimum_ndcg,
        "citation_accuracy": args.minimum_citation_accuracy,
        "citation_faithfulness": args.minimum_citation_faithfulness,
        "refusal_correctness": args.minimum_refusal_correctness,
        "tool_success_rate": args.minimum_tool_success,
        "p95_latency_ms": args.maximum_p95_latency_ms,
        "error_rate": args.maximum_error_rate,
        "scope_violations": args.maximum_scope_violations,
    }
    gate_failures = check_gates(metrics, thresholds)

    baseline_path = args.baseline or (BASELINE_DIR / "runtime_baseline.json")
    baseline = None
    if not getattr(args, "update_baseline", False):
        # --update-baseline explicitly re-freezes the baseline, so it must
        # bypass the stale-suite guard rather than being blocked by it.
        baseline = load_baseline(
            baseline_path,
            required_suite_sha256=str(suite_manifest.get("cases_sha256") or ""),
        )
    diffs, regressions = {}, []
    if baseline:
        diffs, regressions = diff_against_baseline(metrics, baseline)

    report = EvaluationReport(
        track="runtime",
        suite_version=str(suite_manifest.get("suite_version", "?")),
        kb_id=int(suite_manifest.get("kb_id", 0)),
        kb_version=str(suite_manifest.get("kb_version", "?")),
        suite_sha256=str(suite_manifest.get("cases_sha256", "")),
        generated_at=now,
        case_count=len(cases),
        category_counts=suite_manifest.get("category_counts", {}),
        metrics=metrics,
        baseline_metrics=baseline or {},
        diffs=diffs,
        regressions=regressions,
        gate_failures=gate_failures,
        outcomes=outcomes,
    )

    failures = list(gate_failures)
    if args.fail_on_regression and regressions:
        failures.extend(regressions)
    return report, failures


def main() -> int:
    args = parse_args()
    try:
        suite_manifest = verify_suite_integrity(args.cases, args.suite_manifest)
    except ValueError as error:
        print(f"Suite integrity check failed: {error}", file=sys.stderr)
        return 1
    cases = load_cases(args.cases)

    print(f"Running runtime evaluation against {args.base_url} "
          f"({len(cases)} cases, concurrency={max(1, args.concurrency)})...")
    outcomes = asyncio.run(run_all(args))

    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        report, failures = build_report_and_failures(
            args, cases, suite_manifest, outcomes, now
        )
    except ValueError as error:
        print(f"Baseline validation failed: {error}", file=sys.stderr)
        return 1

    report_path = args.report or (
        REPORT_DIR / f"runtime_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path = args.markdown or report_path.with_suffix(".md")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")

    # Record citation faithfulness for Prometheus monitoring
    try:
        from app.api.metrics import set_citation_faithfulness
        cf = report.metrics.get("citation_faithfulness")
        if cf is not None:
            set_citation_faithfulness(float(cf))
    except Exception:
        pass

    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    print(f"\nmarkdown report: {markdown_path}")

    if args.update_baseline:
        save_baseline(
            report.metrics, args.baseline or (BASELINE_DIR / "runtime_baseline.json"),
            track="runtime",
            suite_version=report.suite_version,
            kb_version=report.kb_version,
            suite_sha256=report.suite_sha256,
            generated_at=now,
        )
        print(f"baseline updated: {args.baseline or (BASELINE_DIR / 'runtime_baseline.json')}")

    if failures:
        print("Evaluation failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        # Record gate failure metric for Prometheus alerting
        try:
            from app.api.metrics import record_eval_gate_failure
            record_eval_gate_failure()
        except Exception:
            pass
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
