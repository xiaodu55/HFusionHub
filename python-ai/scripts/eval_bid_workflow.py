#!/usr/bin/env python
"""招投标撰写/自检工作流离线评测门禁（P1-4，CI bid 领域 gate）。

密闭环境（免模型 / 免数据库 / 免网络）跑通 ``BidWriteWorkflow`` 与
``BidCheckWorkflow``，对产出做确定性校验（子串匹配）。任一指标低于
门槛（默认全部 1.0）即非零退出阻断 —— ``bid_*`` 改动必须过此门禁。

用法::

    python scripts/eval_bid_workflow.py
    python scripts/eval_bid_workflow.py --report evaluation/reports/bid_workflow_<date>.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.bid.eval_gate import GATE_THRESHOLDS, check_gates, run_all  # noqa: E402

REPORT_DIR = PROJECT_ROOT / "evaluation" / "reports"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=None,
                        help="output JSON report path (default evaluation/reports/bid_workflow_<date>.json)")
    parser.add_argument("--print-report", action="store_true",
                        help="print the full JSON report to stdout")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    metrics = run_all()
    failures = check_gates(metrics, GATE_THRESHOLDS)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = {
        "track": "bid_workflow",
        "generated_at": now,
        "description": "标书撰写/废标自检工作流确定性门禁（免模型）",
        "metrics": metrics,
        "thresholds": GATE_THRESHOLDS,
        "passed": not failures,
        "failures": failures,
    }

    report_path = args.report or (REPORT_DIR / f"bid_workflow_{now[:10].replace('-', '')}.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("bid workflow gate (P1-4):")
    for key, value in metrics.items():
        mark = "ok" if value >= GATE_THRESHOLDS[key] else "FAIL"
        print(f"  {key:<28} {value:.3f}  [{mark}]")
    if args.print_report:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"report: {report_path}")

    if failures:
        print("Bid workflow gate FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
