#!/usr/bin/env python3
"""
RAG Evaluation Report Generator.

Performs end-to-end RAG evaluation using the Python AI service,
produces a markdown report with metrics, trends, and failure analysis.

Usage:
    python scripts/eval_report.py \\
        --kb-id 1 \\
        --dataset scripts/eval_example.jsonl \\
        --token dev-internal-token-change-me \\
        --output reports/eval_$(date +%Y%m%d).md
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass
class EvalCase:
    query: str
    expected_documents: list[str] = field(default_factory=list)
    expected_answer: str = ""


@dataclass
class EvalResult:
    case: EvalCase
    recall_at_5: float = 0.0
    recall_at_10: float = 0.0
    mrr: float = 0.0
    hit_at_1: bool = False
    hit_at_5: bool = False
    latency_ms: float = 0.0
    retrieved_docs: list[str] = field(default_factory=list)
    answer: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_dataset(path: Path) -> list[EvalCase]:
    cases = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            cases.append(EvalCase(
                query=obj["query"],
                expected_documents=obj.get("expected_documents", []),
                expected_answer=obj.get("expected_answer", ""),
            ))
    return cases


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_evaluation(
    base_url: str,
    token: str,
    kb_id: int,
    cases: list[EvalCase],
    top_k: int = 10,
) -> list[EvalResult]:
    results: list[EvalResult] = []
    headers = {
        "X-Internal-Token": token,
        "Content-Type": "application/json",
    }
    total = len(cases)

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, case in enumerate(cases):
            start = time.time()
            result = EvalResult(case=case)
            try:
                resp = await client.post(
                    f"{base_url}/api/chat",
                    json={
                        "message": case.query,
                        "knowledge_base_id": kb_id,
                        "stream": False,
                    },
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                result.answer = data.get("content", "")
                sources = data.get("sources", [])
                result.latency_ms = (time.time() - start) * 1000

                # Compute recall/mrr from sources
                expected = set(case.expected_documents)
                if expected:
                    doc_names = [s.get("document_name", "") for s in sources]
                    result.retrieved_docs = doc_names
                    top5 = set(doc_names[:5])
                    top10 = set(doc_names[:10])
                    result.recall_at_5 = 1.0 if expected & top5 else 0.0
                    result.recall_at_10 = 1.0 if expected & top10 else 0.0
                    result.hit_at_5 = result.recall_at_5 > 0
                    result.hit_at_1 = doc_names and doc_names[0] in expected
                    for j, d in enumerate(doc_names, 1):
                        if d in expected:
                            result.mrr = 1.0 / j
                            break

                print(f"  [{i+1}/{total}] {case.query[:60]}... R@5={result.recall_at_5:.0f} MRR={result.mrr:.2f}")

            except Exception as exc:
                result.error = str(exc)
                print(f"  [{i+1}/{total}] {case.query[:60]}... ERROR: {exc}")

            results.append(result)

    return results


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(results: list[EvalResult]) -> dict[str, Any]:
    valid = [r for r in results if not r.error]
    n = len(valid)
    if n == 0:
        return {"error": "no valid results"}

    latencies = [r.latency_ms for r in valid]
    latencies.sort()

    return {
        "total_cases": len(results),
        "valid_cases": n,
        "error_count": len(results) - n,
        "recall_at_5": sum(r.recall_at_5 for r in valid) / n,
        "recall_at_10": sum(r.recall_at_10 for r in valid) / n,
        "mrr": sum(r.mrr for r in valid) / n,
        "hit_at_1": sum(1 for r in valid if r.hit_at_1) / n,
        "hit_at_5": sum(1 for r in valid if r.hit_at_5) / n,
        "latency_p50_ms": latencies[len(latencies)//2] if latencies else 0,
        "latency_p95_ms": latencies[min(int(len(latencies)*0.95), len(latencies)-1)] if latencies else 0,
        "latency_avg_ms": sum(latencies) / n if latencies else 0,
    }


def find_failures(results: list[EvalResult]) -> list[EvalResult]:
    return [r for r in results if not r.error and r.mrr == 0.0]


# ---------------------------------------------------------------------------
# Report generator
# ---------------------------------------------------------------------------

def generate_report(
    results: list[EvalResult],
    metrics: dict[str, Any],
    kb_id: int,
    output: Path,
) -> str:
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    failures = find_failures(results)

    lines = [
        "# RAG Evaluation Report",
        "",
        f"**Generated**: {timestamp}  ",
        f"**Knowledge Base ID**: {kb_id}  ",
        f"**Total Cases**: {metrics.get('total_cases', 0)}  ",
        "",
        "## Summary",
        "",
        "| Metric | Value | Target | Status |",
        "|--------|-------|--------|--------|",
    ]

    targets = {
        "recall_at_5": (0.90, "R@5"),
        "recall_at_10": (0.95, "R@10"),
        "mrr": (0.70, "MRR"),
        "hit_at_1": (0.70, "Hit@1"),
        "hit_at_5": (0.90, "Hit@5"),
        "latency_p95_ms": (2000, "P95 Latency"),
    }

    for key, (target, label) in targets.items():
        val = metrics.get(key, 0)
        if key == "latency_p95_ms":
            status = "✅" if val < target else "⚠️"
            lines.append(f"| {label} | {val:.0f}ms | <{target:.0f}ms | {status} |")
        else:
            status = "✅" if val >= target else "❌"
            lines.append(f"| {label} | {val:.3f} | ≥{target:.2f} | {status} |")

    lines += [
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Valid Cases | {metrics.get('valid_cases', 0)} |",
        f"| Errors | {metrics.get('error_count', 0)} |",
        f"| Avg Latency | {metrics.get('latency_avg_ms', 0):.0f}ms |",
        f"| P50 Latency | {metrics.get('latency_p50_ms', 0):.0f}ms |",
        "",
    ]

    if failures:
        lines += [
            f"## Failures ({len(failures)} cases with MRR=0)",
            "",
        ]
        for f in failures[:10]:
            lines.append(f"- **Query**: {f.case.query[:100]}")
            lines.append(f"  - Expected: {f.case.expected_documents}")
            lines.append(f"  - Retrieved: {f.retrieved_docs[:5]}")
            lines.append("")

    lines += [
        "## Per-Case Detail",
        "",
        "| # | Query | R@5 | MRR | Latency |",
        "|---|-------|-----|-----|---------|",
    ]
    for i, r in enumerate(results, 1):
        status = "❌" if r.error else ("✅" if r.mrr > 0 else "⚠️")
        lines.append(f"| {i} | {status} {r.case.query[:60]} | {r.recall_at_5:.0f} | {r.mrr:.2f} | {r.latency_ms:.0f}ms |")

    report = "\n".join(lines)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(f"\nReport written to: {output}")
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="RAG Evaluation Report Generator")
    parser.add_argument("--kb-id", type=int, required=True, help="Knowledge base ID")
    parser.add_argument("--dataset", type=Path, required=True, help="JSONL dataset path")
    parser.add_argument("--token", type=str, required=True, help="Python AI internal token")
    parser.add_argument("--base-url", type=str, default="http://localhost:9000", help="Python AI URL")
    parser.add_argument("--output", type=Path, default=Path("reports/eval_report.md"), help="Output path")
    parser.add_argument("--top-k", type=int, default=10, help="Retrieval top-K")
    args = parser.parse_args()

    print(f"Loading dataset: {args.dataset}")
    cases = load_dataset(args.dataset)
    print(f"Loaded {len(cases)} evaluation cases")

    print(f"Running evaluation against KB {args.kb_id}...")
    results = await run_evaluation(args.base_url, args.token, args.kb_id, cases, args.top_k)

    metrics = compute_metrics(results)
    generate_report(results, metrics, args.kb_id, args.output)

    # Exit code: 0 if all targets met, 1 otherwise
    targets_met = (
        metrics.get("recall_at_5", 0) >= 0.90
        and metrics.get("mrr", 0) >= 0.70
        and metrics.get("hit_at_5", 0) >= 0.90
    )
    sys.exit(0 if targets_met else 1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
