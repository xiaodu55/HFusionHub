"""markdown 评估报告生成。"""

from __future__ import annotations

from pathlib import Path

from .schemas import MetricResult

# 指标显示名与参考目标（HUMAN_READABLE 顺序即报告展示顺序）
_DISPLAY: list[tuple] = [
    ("retrieval_hit@5", "检索 Hit@5", "≥ 0.90"),
    ("retrieval_recall@5", "检索 Recall@5", "≥ 0.90"),
    ("retrieval_mrr@5", "检索 MRR@5", "≥ 0.70"),
    ("refusal_when_required_rate", "该答未答率", "0"),
    ("fallback_when_required_rate", "回退话术率", "越低越好"),
    ("over_retrieval_rate", "过度检索率", "0"),
    ("ttft_p50_ms", "首字延迟 P50 (ms)", "< 3000"),
    ("ttft_mean_ms", "首字延迟均值 (ms)", "< 3000"),
    ("latency_mean_ms", "总延迟均值 (ms)", "< 15000"),
    ("judge_faithfulness_mean", "忠实度 (LLM 评审)", "≥ 0.80"),
    ("judge_answer_correctness_mean", "答案正确性 (LLM 评审)", "≥ 0.75"),
    ("judge_answer_relevancy_mean", "答案相关性 (LLM 评审)", "≥ 0.75"),
]


def render_markdown(result: MetricResult, title: str = "") -> str:
    meta = result.meta
    lines = [
        f"# HFusionHub 评估报告{' — ' + title if title else ''}",
        "",
        f"- 运行文件：`{result.run_file}`",
        f"- 记录条数：{meta.get('record_count', 0)}（要求 RAG：{meta.get('requires_rag_count', 0)}）",
        f"- LLM 评审：{'启用' if meta.get('judge_enabled') else '未启用'}"
        f"（评审 {meta.get('judge_cases', 0)} 条，跳过 {meta.get('judge_skipped', 0)} 条）",
        "",
        "## 指标汇总",
        "",
        "| 指标 | 数值 | 参考目标 |",
        "|------|------|---------|",
    ]
    for key, label, target in _DISPLAY:
        if key in result.overall:
            value = result.overall[key]
            shown = f"{value:.4f}" if isinstance(value, float) and value <= 1.5 else f"{value:,.1f}"
            lines.append(f"| {label} | {shown} | {target} |")
    if not any(k in result.overall for _, k, _ in _DISPLAY):
        lines.append("| （无可用指标） | - | - |")

    errors = meta.get("record_errors") or []
    if errors:
        lines += ["", "## 记录阶段错误", ""]
        for e in errors[:10]:
            lines.append(f"- `{e['query_id']}`: {e['error']}")

    failures = [c for c in result.cases if c.skip_reason]
    if failures:
        lines += ["", "## 评审跳过原因", ""]
        for c in failures[:10]:
            lines.append(f"- `{c.query_id}`: {c.skip_reason}")

    flag_cases = [c for c in result.cases if getattr(c, "flags", None)]
    if flag_cases:
        lines += ["", "## 行为红线命中", ""]
        for c in flag_cases[:15]:
            lines.append(f"- `{c.query_id}`: {', '.join(c.flags)}")

    lines.append("")
    return "\n".join(lines)


def save_report(result: MetricResult, reports_dir: Path, title: str = "") -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / result.run_file.replace(".jsonl", "_report.md")
    path.write_text(render_markdown(result, title), encoding="utf-8")
    return path
