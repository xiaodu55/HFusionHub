#!/usr/bin/env python
"""Hermetic offline evaluation track (PR/CI gate).

Runs the frozen Phase-1 suite against the deterministic synthetic index, writes
a fixed-format JSON + Markdown report, compares against a stored baseline and
exits non-zero on any gate failure or baseline regression.

Usage:
    python scripts/eval_offline.py                       # defaults
    python scripts/eval_offline.py --update-baseline     # record current as baseline
    python scripts/eval_offline.py --minimum-recall 0.90 --minimum-ndcg 0.80
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.rag.eval_baseline import (  # noqa: E402
    EvaluationReport,
    check_gates,
    compute_citation_faithfulness,
    diff_against_baseline,
    load_baseline,
    load_cases,
    render_markdown,
    save_baseline,
    verify_suite_integrity,
)
from app.core.rag.synthetic_index import SyntheticRouter  # noqa: E402

SUITE_DIR = PROJECT_ROOT / "evaluation" / "suite"
REPORT_DIR = PROJECT_ROOT / "evaluation" / "reports"
BASELINE_DIR = PROJECT_ROOT / "evaluation" / "baseline"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=SUITE_DIR / "cases.jsonl")
    parser.add_argument("--suite-manifest", type=Path, default=SUITE_DIR / "suite_manifest.json")
    parser.add_argument("--kb-manifest", type=Path, default=None,
                        help="synthetic KB manifest path (default evaluation/kb/kb_manifest.json; "
                             "bid suite uses evaluation/kb_bid/kb_manifest.json)")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--citation-top-k", type=int, default=3,
                        help="how many retrieved chunks the extractive answer model cites")
    parser.add_argument("--min-score", type=float, default=1.0,
                        help="relevance threshold for the synthetic index")
    parser.add_argument("--report", type=Path, default=None,
                        help="output JSON report path (default evaluation/reports/offline_<date>.json)")
    parser.add_argument("--markdown", type=Path, default=None,
                        help="output Markdown report path")
    parser.add_argument("--baseline", type=Path, default=None,
                        help="baseline JSON path (default evaluation/baseline/offline_baseline.json)")
    parser.add_argument("--update-baseline", action="store_true",
                        help="write the current metrics as the new baseline")
    parser.add_argument("--minimum-recall", type=float, default=0.85)
    parser.add_argument("--minimum-ndcg", type=float, default=0.75)
    parser.add_argument("--minimum-citation-accuracy", type=float, default=0.85)
    parser.add_argument("--minimum-citation-faithfulness", type=float, default=0.30)
    parser.add_argument("--maximum-scope-violations", type=int, default=0)
    # 招投标领域门槛（B2 垂直化）：默认不设限，bid 套件显式传入
    parser.add_argument("--minimum-qualification-recall", type=float, default=0.0)
    parser.add_argument("--minimum-disqualification-clause-recall", type=float, default=0.0)
    parser.add_argument("--minimum-scoring-point-accuracy", type=float, default=0.0)
    parser.add_argument("--minimum-bid-terminology-accuracy", type=float, default=0.0)
    parser.add_argument("--fail-on-regression", action="store_true",
                        help="fail the gate when a baseline regression is detected")
    return parser.parse_args()


def _compute_bid_metrics(case, retrieved_chunk_ids: list[str], router) -> Optional[dict[str, float]]:
    """招投标领域指标：对每条期望事实子串，在检索命中的 chunk 内容中做
    确定性子串匹配（无需 LLM，保持离线轨密闭）。返回 {metric_key: 命中率}。
    """
    facts = getattr(case, "bid_facts", None)
    if not facts:
        return None
    content_by_chunk = getattr(getattr(router, "index", None), "get_chunk_content", None)
    if content_by_chunk is None:
        return None
    corpus = "".join(
        content_by_chunk(str(chunk_id)) or "" for chunk_id in retrieved_chunk_ids
    )
    bid: dict[str, float] = {}
    for metric_key, expected_facts in facts.items():
        if not isinstance(expected_facts, list) or not expected_facts:
            continue
        hit = sum(1 for fact in expected_facts if str(fact) in corpus)
        bid[metric_key] = hit / len(expected_facts)
    return bid or None


async def evaluate_offline(router, cases, top_k: int, citation_top_k: int = 3) -> list:
    outcomes = []
    for case in cases:
        merged = await router.search(case.query, case.kb_id, top_k)
        seen: list[str] = []
        scope_violations = 0
        for result in merged.results:
            metadata = result.metadata or {}
            if metadata.get("knowledge_base_id") != case.kb_id:
                scope_violations += 1
            chunk_id = metadata.get("chunk_id")
            if chunk_id is not None and str(chunk_id) not in seen:
                seen.append(str(chunk_id))
        cited = seen[:citation_top_k]
        outcomes.append(
            {
                "case_id": case.case_id,
                "category": case.category,
                "retrieved_chunk_ids": seen,
                "expected_chunk_ids": case.expected_chunk_ids,
                "expected_document_names": case.expected_document_names,
                "scope_violations": scope_violations,
                "citation_faithfulness": compute_citation_faithfulness(
                    cited, case.expected_chunk_ids
                ),
                "refusal_expected": case.refusal == "required",
                "refusal_correct": None,
                "tool": case.tool,
                "cited_chunk_ids": cited,
                "bid": _compute_bid_metrics(case, seen, router),
            }
        )
    return outcomes


def main() -> int:
    args = parse_args()
    try:
        suite_manifest = verify_suite_integrity(args.cases, args.suite_manifest)
    except ValueError as error:
        print(f"Suite integrity check failed: {error}", file=sys.stderr)
        return 1
    cases = load_cases(args.cases)

    # 支持领域套件（如 suite_bid）指向独立合成 KB 清单
    from app.core.rag.synthetic_index import SyntheticIndex
    kb_manifest = args.kb_manifest or (PROJECT_ROOT / "evaluation" / "kb" / "kb_manifest.json")
    router = SyntheticRouter(index=SyntheticIndex(manifest_path=kb_manifest),
                             min_score=args.min_score)
    raw_outcomes = asyncio.run(
        evaluate_offline(router, cases, args.top_k, args.citation_top_k)
    )

    from app.core.rag.eval_baseline import CaseOutcome, aggregate_metrics

    outcomes = [CaseOutcome(**raw) for raw in raw_outcomes]
    metrics = aggregate_metrics(outcomes, top_k=args.top_k)

    thresholds = {
        "recall_at_5": args.minimum_recall,
        "ndcg_at_10": args.minimum_ndcg,
        "citation_accuracy": args.minimum_citation_accuracy,
        "citation_faithfulness": args.minimum_citation_faithfulness,
        "scope_violations": args.maximum_scope_violations,
        "qualification_recall": args.minimum_qualification_recall,
        "disqualification_clause_recall": args.minimum_disqualification_clause_recall,
        "scoring_point_accuracy": args.minimum_scoring_point_accuracy,
        "bid_terminology_accuracy": args.minimum_bid_terminology_accuracy,
    }
    gate_failures = check_gates(metrics, thresholds)

    baseline_path = args.baseline or (BASELINE_DIR / "offline_baseline.json")
    baseline = None
    if not args.update_baseline:
        # --update-baseline explicitly re-freezes the baseline, so it must
        # bypass the stale-suite guard rather than being blocked by it.
        try:
            baseline = load_baseline(
                baseline_path,
                required_suite_sha256=str(suite_manifest.get("cases_sha256") or ""),
            )
        except ValueError as error:
            print(f"Baseline validation failed: {error}", file=sys.stderr)
            return 1
    diffs, regressions = {}, []
    if baseline:
        diffs, regressions = diff_against_baseline(metrics, baseline)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = EvaluationReport(
        track="offline",
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

    report_path = args.report or (
        REPORT_DIR / f"offline_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path = args.markdown or report_path.with_suffix(".md")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")

    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    print(f"\nmarkdown report: {markdown_path}")

    if args.update_baseline:
        save_baseline(
            metrics, baseline_path,
            track="offline",
            suite_version=report.suite_version,
            kb_version=report.kb_version,
            suite_sha256=report.suite_sha256,
            generated_at=now,
        )
        print(f"baseline updated: {baseline_path}")

    failures = list(gate_failures)
    if args.fail_on_regression and regressions:
        failures.extend(regressions)
    if failures:
        print("Evaluation failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
