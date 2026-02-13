#!/usr/bin/env python
"""Evaluate the configured router against a JSONL retrieval ground-truth suite."""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.rag.query_router import get_router
from app.core.rag.retrieval_evaluator import evaluate_sync, load_cases


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True, help="JSONL retrieval evaluation suite")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--minimum-recall", type=float, default=0.0)
    parser.add_argument("--minimum-mrr", type=float, default=0.0)
    parser.add_argument("--maximum-scope-violations", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = evaluate_sync(get_router(), load_cases(args.cases), top_k=args.top_k)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    failures = []
    if report.recall_at_k < args.minimum_recall:
        failures.append(f"recall@{args.top_k}={report.recall_at_k:.3f} is below {args.minimum_recall:.3f}")
    if report.mrr_at_k < args.minimum_mrr:
        failures.append(f"MRR@{args.top_k}={report.mrr_at_k:.3f} is below {args.minimum_mrr:.3f}")
    if report.scope_violation_count > args.maximum_scope_violations:
        failures.append(
            f"scope violations={report.scope_violation_count} exceeds {args.maximum_scope_violations}"
        )
    if failures:
        print("Evaluation failed: " + "; ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
