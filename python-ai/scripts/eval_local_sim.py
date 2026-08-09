#!/usr/bin/env python
"""Local eval simulation for demonstrating the eval flow.

Generates a synthetic eval-runtime-report that mirrors the real eval_runtime.py
output format. Used for local verification when no staging environment is available.

Usage:
    python scripts/eval_local_sim.py [--update-baseline]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
# 显式插入脚本目录：PYTHONSAFEPATH=1（python -P）会取消脚本目录自动入表
for _path in (str(SCRIPTS_DIR), str(PROJECT_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from eval_baseline import (
    EvaluationReport,
    aggregate_metrics,
    load_cases,
    render_markdown,
    save_baseline,
    verify_suite_integrity,
)

SUITE_DIR = PROJECT_ROOT / "evaluation" / "suite"
REPORT_DIR = PROJECT_ROOT / "evaluation" / "reports"
BASELINE_DIR = PROJECT_ROOT / "evaluation" / "baseline"


def simulate_outcomes(cases: list, seed: int = 42) -> list[dict]:
    """Generate realistic simulated CaseOutcome dicts."""
    rng = random.Random(seed)
    outcomes = []
    for case in cases:
        is_refusal = case.refusal == "required"
        if is_refusal:
            success = rng.random() < 0.94
        else:
            success = rng.random() < 0.97

        latency_ms = rng.uniform(800, 4000) if not is_refusal else rng.uniform(500, 2000)
        tokens = rng.randint(200, 800)

        outcomes.append({
            "case_id": case.case_id,
            "category": case.category,
            "retrieved_chunk_ids": list(case.expected_document_names[:3]) if success else [],
            "cited_chunk_ids": list(case.expected_document_names[:2]) if success else [],
            "expected_chunk_ids": tuple(case.expected_document_names),
            "expected_document_names": tuple(case.expected_document_names),
            "scope_violations": 0,
            "citation_faithfulness": rng.uniform(0.65, 0.95) if success else 0.0,
            "refusal_expected": is_refusal,
            "refusal_correct": success if is_refusal else None,
            "tool": case.tool,
            "latency_ms": latency_ms,
            "tokens": tokens,
            "cost_usd": tokens * 0.0000003,
            "tool_success": (True if case.tool and rng.random() < 0.98 else None) if case.tool else None,
            "error": None,
        })
    return outcomes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    suite_manifest = verify_suite_integrity(
        SUITE_DIR / "cases.jsonl", SUITE_DIR / "suite_manifest.json"
    )
    cases = load_cases(SUITE_DIR / "cases.jsonl")

    print(f"Simulating runtime evaluation for {len(cases)} cases...")
    raw_outcomes = simulate_outcomes(cases)

    # Convert to CaseOutcome objects
    from eval_baseline import CaseOutcome
    outcomes = [CaseOutcome(**o) for o in raw_outcomes]

    metrics = aggregate_metrics(outcomes, top_k=10, exclude_refusal_from_citation=True)
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

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
        baseline_metrics={},
        diffs={},
        regressions=[],
        gate_failures=[],
        outcomes=outcomes,
    )

    report_path = REPORT_DIR / f"runtime_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path = report_path.with_suffix(".md")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")

    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    print(f"\nreport: {report_path}")
    print(f"markdown: {markdown_path}")

    if args.update_baseline:
        save_baseline(
            report.metrics, BASELINE_DIR / "runtime_baseline.json",
            track="runtime",
            suite_version=report.suite_version,
            kb_version=report.kb_version,
            suite_sha256=report.suite_sha256,
            generated_at=now,
        )
        print("baseline updated")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
