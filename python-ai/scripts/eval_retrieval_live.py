#!/usr/bin/env python
"""纯检索 recall@5 归因探针（R16-1 残余差异归因工具，R17-1 升级为双模式）。

不经 LLM 答案层，对冻结套件逐用例检索并按 expected_document_names 计算
doc 级 recall@5，用于把 runtime 轨的检索指标变化拆分为两段责任：

1. **检索栈本身**（embedding / 通道 / RRF / ACL 过滤）——本探针的输出；
2. **答案层**（runtime 的 sources 从 /api/chat 响应提取，受模型行为、
   压缩、sources 附加策略影响）——runtime 基线与本探针的差值。

两种模式::

- 进程内（默认，本地归因）：直连 Milvus + 本地 embedding 服务，
  需 VECTOR_STORE_MODE 与 embedding 提供方可用；
- HTTP（``--base-url`` + ``--token``，nightly/对远端栈）：逐用例 POST
  ``/api/rag/eval``（生产 router/retriever 链路、无答案生成），ACL 由
  ``X-User-Clearance`` 头经检索内部 ``get_clearance()`` 生效。

文档名解析：优先读 chunk metadata 的 ``document_title``（入库管线自带；
HTTP 模式由 /api/rag/eval 响应的 ``document_name`` 暴露）；``--docmap``
仅作为旧语料无 metadata 标题时的可选回退。

基线与门禁::

    --update-baseline 把 recall@5 冻结进 evaluation/baseline/
    retrieval_baseline.json（带 suite_sha256 钉扎）；带基线运行时输出
    diff，``--fail`` 使 recall 低于 ``--minimum-recall``（默认 0.80）
    或相对基线回退超 ``--regression-tolerance``（默认 0.03）时退出码 1。

2026-09-09 首次归因结论（真机栈，进程内模式）：纯检索 OVERALL 0.830
（normal 0.986 / cross_document 0.983 / long_document 1.0 / tool 0.9 /
injection 0.84 / refusal 1.0 / permission 0——ACL 正确拦截；permission
按 admin 老口径 = 1.0），证明检索栈与 2026-09-06 旧基线（0.856）同水平；
runtime 答案层 0.550 与纯检索 0.830 的差值在答案层（与单任务 token
1582→774 同源的模型侧行为漂移），与本仓代码改动无关。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_BASELINE = ROOT / "evaluation" / "baseline" / "retrieval_baseline.json"
DEFAULT_MANIFEST = ROOT / "evaluation" / "suite" / "suite_manifest.json"
DEFAULT_MINIMUM_RECALL = 0.80
DEFAULT_REGRESSION_TOLERANCE = 0.03


def compute_cases_sha(cases_path: Path) -> str:
    return hashlib.sha256(Path(cases_path).read_bytes()).hexdigest()


def load_suite_version(manifest_path: Path | None) -> str:
    if manifest_path and Path(manifest_path).exists():
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        return str(manifest.get("suite_version", "unknown"))
    return "unknown"


def subject_for(category: str) -> str:
    """与 eval_runtime.subject_for_case 一致：permission 走最低权限主体。"""
    return "general" if category == "permission" else "admin"


# ---------------------------------------------------------------------------
# 逐用例检索（双模式）
# ---------------------------------------------------------------------------


def retrieve_inprocess(svc, case: dict, subject: str, top_k: int) -> list[dict]:
    """进程内模式：直接调用 milvus_store 门面，ACL 经 clearance 上下文生效。"""
    from app.core.security.clearance import (
        build_acl_metadata_filter,
        set_clearance,
    )
    from app.core.vectorstore.milvus_store import search_similar

    set_clearance(subject)
    embedding = svc.get_query_embedding(case["query"])
    return search_similar(
        query_embedding=embedding,
        knowledge_base_id=case["kb_id"],
        top_k=top_k,
        metadata_filter=build_acl_metadata_filter(subject),
    )


def retrieve_http(case: dict, subject: str, top_k: int, args) -> list[dict]:
    """HTTP 模式：POST /api/rag/eval（生产 router/retriever 链路，无答案生成）。

    ACL 由 X-User-Clearance 头经检索内部 get_clearance() 生效。
    """
    import httpx

    resp = httpx.post(
        f"{args.base_url.rstrip('/')}/api/rag/eval",
        json={
            "query": case["query"],
            "knowledge_base_id": case["kb_id"],
            "top_k": top_k,
            "enable_rewrite": False,
        },
        headers={
            "X-Internal-Token": args.token,
            "X-Tenant-Id": str(args.tenant_id),
            "X-User-Clearance": subject,
        },
        timeout=120.0,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "completed":
        # clarification_required / no_knowledge_route：无检索结果
        return []
    retrieval = data.get("retrieval") or {}
    return [
        {
            "document_id": item.get("document_id"),
            "document_name": item.get("document_name"),
        }
        for item in (retrieval.get("results") or [])
    ]


# ---------------------------------------------------------------------------
# 报告 / 基线 / 门禁
# ---------------------------------------------------------------------------


def build_report(args, results_by_category: dict, overall: float) -> dict:
    sha = compute_cases_sha(args.cases)
    report = {
        "track": "retrieval",
        "suite_version": load_suite_version(args.suite_manifest),
        "suite_sha256": sha,
        "generated_at": datetime.now(UTC).isoformat(),
        "metrics": {
            "recall_at_5": round(overall, 4),
            "per_category": {
                cat: round(bucket["sum"] / bucket["n"], 4)
                for cat, bucket in sorted(results_by_category.items())
            },
        },
    }
    baseline = load_baseline(args.baseline)
    if baseline is not None:
        if baseline.get("suite_sha256") != sha:
            report["baseline_note"] = (
                "基线属于其它套件版本（suite_sha256 不一致），跳过对比"
            )
        else:
            base_recall = (baseline.get("metrics") or {}).get("recall_at_5")
            report["baseline_metrics"] = {"recall_at_5": base_recall}
            if base_recall is not None:
                delta = round(overall - base_recall, 4)
                report["diffs"] = {"recall_at_5": delta}
    return report


def load_baseline(path: Path) -> dict | None:
    if not Path(path).exists():
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def gate_failures(report: dict, minimum_recall: float, regression_tolerance: float) -> list[str]:
    failures: list[str] = []
    recall = report["metrics"]["recall_at_5"]
    if recall < minimum_recall:
        failures.append(f"recall_at_5={recall} is below minimum {minimum_recall}")
    diffs = report.get("diffs") or {}
    delta = diffs.get("recall_at_5")
    if delta is not None and delta < -regression_tolerance:
        failures.append(
            f"recall_at_5 regression vs baseline: {delta} exceeds tolerance "
            f"-{regression_tolerance}"
        )
    return failures


def render_markdown(report: dict, failures: list[str]) -> str:
    metrics = report["metrics"]
    lines = [
        "# HFusionHub 评测报告 (retrieval)",
        "",
        f"- **suite_version**: {report.get('suite_version')}",
        f"- **cases_sha256**: {report['suite_sha256'][:16]}…",
        f"- **generated_at**: {report['generated_at']}",
        "",
        "| 指标 | 本次 | 基线 | 差异 |",
        "|------|------|------|------|",
    ]
    base = (report.get("baseline_metrics") or {}).get("recall_at_5")
    delta = (report.get("diffs") or {}).get("recall_at_5")
    lines.append(
        f"| recall@5 | {metrics['recall_at_5']} | "
        f"{base if base is not None else 'N/A'} | "
        f"{delta if delta is not None else 'N/A'} |"
    )
    lines.append("")
    lines.append("## 分类明细")
    lines.append("")
    lines.append("| 类别 | recall@5 |")
    lines.append("|------|----------|")
    for cat, value in metrics.get("per_category", {}).items():
        lines.append(f"| {cat} | {value} |")
    lines.append("")
    if failures:
        lines.append("## 门禁")
        lines.append("")
        lines.extend(f"- ❌ {f}" for f in failures)
    else:
        lines.append("## 门禁")
        lines.append("")
        lines.append("- ✅ 全部通过")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cases", required=True, help="冻结套件 cases.jsonl")
    parser.add_argument("--docmap", default=None, help="可选回退：doc id → 标题 JSON（仅旧语料无 metadata 标题时需要）")
    parser.add_argument("--base-url", default=None, help="HTTP 模式：Python AI 服务地址（缺省为进程内模式）")
    parser.add_argument("--token", default=None, help="HTTP 模式：X-Internal-Token")
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--suite-manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--report", default=None, help="JSON 报告输出路径")
    parser.add_argument("--markdown", default=None, help="Markdown 报告输出路径")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--minimum-recall", type=float, default=DEFAULT_MINIMUM_RECALL)
    parser.add_argument(
        "--regression-tolerance", type=float, default=DEFAULT_REGRESSION_TOLERANCE
    )
    parser.add_argument("--fail", action="store_true", help="门禁失败时退出码 1")
    args = parser.parse_args()

    cases = [
        json.loads(line)
        for line in open(args.cases, encoding="utf-8")
        if line.strip()
    ]
    docmap = {}
    if args.docmap:
        docmap = {int(k): v for k, v in json.load(open(args.docmap, encoding="utf-8")).items()}
    http_mode = bool(args.base_url)

    if http_mode and not args.token:
        parser.error("--base-url 模式需要 --token")

    svc = None
    if not http_mode:
        from app.core.embedding import get_embedding_service
        from app.core.tenant.context import set_tenant_id

        set_tenant_id(1)
        svc = get_embedding_service()

    def titles_of(rows: list[dict]) -> set[str]:
        out: set[str] = set()
        for r in rows:
            title = (
                r.get("document_name") if http_mode
                else (r.get("metadata") or {}).get("document_title")
            )
            if not title and docmap:
                try:
                    title = docmap.get(int(r.get("document_id")))
                except (TypeError, ValueError):
                    title = None
            if title:
                out.add(title)
        return out

    stats: dict[str, dict] = defaultdict(lambda: {"sum": 0.0, "n": 0})
    admin_variant_perm = {"sum": 0.0, "n": 0}
    started = time.time()

    for i, case in enumerate(cases):
        expected = set(case["expected_document_names"])
        subject = subject_for(case["category"])
        if http_mode:
            rows = retrieve_http(case, subject, args.top_k, args)
        else:
            rows = retrieve_inprocess(svc, case, subject, args.top_k)
        recall = (
            len(expected & titles_of(rows)) / max(1, len(expected)) if expected else 1.0
        )
        bucket = stats[case["category"]]
        bucket["sum"] += recall
        bucket["n"] += 1
        if case["category"] == "permission":
            # 老口径对照：permission 用例若按 admin 检索（ACL 前）的召回，
            # 用于量化「ACL 拒答不贡献检索召回」的口径变化幅度
            admin_rows = (
                retrieve_http(case, "admin", args.top_k, args)
                if http_mode
                else retrieve_inprocess(svc, case, "admin", args.top_k)
            )
            recall_admin = (
                len(expected & titles_of(admin_rows)) / max(1, len(expected))
                if expected
                else 1.0
            )
            admin_variant_perm["sum"] += recall_admin
            admin_variant_perm["n"] += 1
        if (i + 1) % 60 == 0:
            print(f"... {i + 1}/{len(cases)} ({time.time() - started:.0f}s)", flush=True)
    if not http_mode:
        from app.core.security.clearance import clear_clearance

        clear_clearance()

    total_sum = sum(b["sum"] for b in stats.values())
    total_n = sum(b["n"] for b in stats.values())
    overall = total_sum / max(1, total_n)

    report = build_report(args, stats, overall)
    failures = gate_failures(report, args.minimum_recall, args.regression_tolerance)
    report["gate_failures"] = failures

    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if args.markdown:
        Path(args.markdown).parent.mkdir(parents=True, exist_ok=True)
        Path(args.markdown).write_text(
            render_markdown(report, failures), encoding="utf-8"
        )

    print(f"\n=== 纯检索 recall@{args.top_k}（按各自主体权限，复刻 runtime 语义）===")
    for category, bucket in sorted(stats.items()):
        print(f"{category:16s} {bucket['sum'] / bucket['n']:.3f}  (n={bucket['n']})")
    print(f"{'OVERALL':16s} {overall:.4f}  (n={total_n})")
    if admin_variant_perm["n"]:
        print(
            f"permission 按 admin 检索（老口径）: "
            f"{admin_variant_perm['sum'] / max(1, admin_variant_perm['n']):.3f} "
            f"(n={admin_variant_perm['n']})"
        )
    if args.update_baseline:
        Path(args.baseline).parent.mkdir(parents=True, exist_ok=True)
        payload = dict(report)
        payload.pop("baseline_metrics", None)
        payload.pop("diffs", None)
        payload.pop("baseline_note", None)
        payload.pop("gate_failures", None)
        Path(args.baseline).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"baseline updated: {args.baseline}")
    for failure in failures:
        print(f"❌ {failure}")
    if args.fail and failures:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
