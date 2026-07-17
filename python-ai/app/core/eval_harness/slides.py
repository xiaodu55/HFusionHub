"""自包含 16:9 HTML 幻灯片生成（评分后自动产出，供发布汇报使用）。

单文件、无外部依赖：封面 → KPI 卡 → 指标表 → 行为红线命中 → 结论，键盘 ←/→ 翻页。
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from .schemas import MetricResult

_LABELS: dict[str, str] = {
    "retrieval_hit@5": "检索 Hit@5",
    "retrieval_recall@5": "检索 Recall@5",
    "retrieval_mrr@5": "检索 MRR@5",
    "refusal_when_required_rate": "该答未答率",
    "fallback_when_required_rate": "回退话术率",
    "over_retrieval_rate": "过度检索率",
    "ttft_p50_ms": "首字延迟 P50",
    "ttft_mean_ms": "首字延迟均值",
    "latency_mean_ms": "总延迟均值",
    "judge_faithfulness_mean": "忠实度 (LLM)",
    "judge_answer_correctness_mean": "答案正确性 (LLM)",
    "judge_answer_relevancy_mean": "答案相关性 (LLM)",
}

_TEMPLATE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>HFusionHub 评估报告 — {title}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #0b0f0e; color: #e7f0ec; font-family: "PingFang SC", "Microsoft YaHei", sans-serif; overflow: hidden; }}
  .slide {{ display: none; width: 100vw; height: 100vh; padding: 7vh 8vw; flex-direction: column; justify-content: center; }}
  .slide.active {{ display: flex; }}
  .kicker {{ letter-spacing: .35em; font-size: 14px; color: #34d399; text-transform: uppercase; }}
  h1 {{ font-size: 56px; margin: 18px 0 10px; }}
  h2 {{ font-size: 40px; margin-bottom: 28px; border-left: 6px solid #34d399; padding-left: 18px; }}
  .sub {{ color: #9db8ae; font-size: 20px; }}
  .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 20px; margin-top: 30px; }}
  .kpi {{ background: rgba(52, 211, 153, .08); border: 1px solid rgba(52, 211, 153, .25); border-radius: 14px; padding: 22px; }}
  .kpi .v {{ font-size: 42px; font-weight: 700; color: #6ee7b7; }}
  .kpi .k {{ margin-top: 6px; color: #9db8ae; font-size: 15px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 20px; }}
  th, td {{ padding: 12px 16px; border-bottom: 1px solid rgba(255,255,255,.08); text-align: left; }}
  th {{ color: #9db8ae; font-weight: 500; }}
  td.num {{ font-variant-numeric: tabular-nums; }}
  .fail {{ background: rgba(251, 113, 133, .08); border-left: 4px solid #fb7185; padding: 14px 18px; margin-bottom: 12px; border-radius: 8px; font-size: 18px; }}
  .hint {{ position: fixed; bottom: 20px; right: 28px; color: #5c7268; font-size: 13px; }}
</style>
</head>
<body>
{slides}
<div class="hint">← / → 翻页 · 共 {total} 页</div>
<script>
  const slides = document.querySelectorAll('.slide');
  let i = 0;
  const show = (n) => {{ slides.forEach((s, idx) => s.classList.toggle('active', idx === n)); }};
  document.addEventListener('keydown', (e) => {{
    if (e.key === 'ArrowRight' || e.key === ' ') {{ i = Math.min(i + 1, slides.length - 1); show(i); }}
    if (e.key === 'ArrowLeft') {{ i = Math.max(i - 1, 0); show(i); }}
  }});
  show(0);
</script>
</body>
</html>"""


def _fmt(key: str, value: float) -> str:
    return f"{value:,.1f}" if value > 1.5 else f"{value:.4f}"


def render_slides(result: MetricResult, title: str = "") -> str:
    slides: list[str] = []
    meta = result.meta

    # 封面
    slides.append(f"""
  <section class="slide active">
    <p class="kicker">HFusionHub Evaluation</p>
    <h1>RAG 评估报告</h1>
    <p class="sub">{escape(title or result.run_file)} · 记录 {meta.get('record_count', 0)} 条 · 评审 {meta.get('judge_cases', 0)} 条</p>
  </section>""")

    # KPI 总览
    kpi_cards = "".join(
        f'<div class="kpi"><div class="v">{escape(_fmt(k, float(v)))}</div><div class="k">{escape(_LABELS.get(k, k))}</div></div>'
        for k, v in list(result.overall.items())[:6]
    )
    slides.append(f"""
  <section class="slide">
    <p class="kicker">KPI Overview</p>
    <h2>核心指标</h2>
    <div class="kpis">{kpi_cards}</div>
  </section>""")

    # 全量指标表
    rows = "".join(
        f"<tr><td>{escape(_LABELS.get(k, k))}</td><td class='num'>{escape(_fmt(k, float(v)))}</td></tr>"
        for k, v in result.overall.items()
    )
    slides.append(f"""
  <section class="slide">
    <p class="kicker">Metrics</p>
    <h2>指标明细</h2>
    <table><thead><tr><th>指标</th><th>数值</th></tr></thead><tbody>{rows}</tbody></table>
  </section>""")

    # 行为红线命中
    flag_cases = [c for c in result.cases if getattr(c, "flags", None)]
    if flag_cases:
        cards = "".join(
            f'<div class="fail"><strong>{escape(c.query_id)}</strong> — {escape(", ".join(c.flags))}</div>'
            for c in flag_cases[:8]
        )
        slides.append(f"""
  <section class="slide">
    <p class="kicker">Behavior Red Lines</p>
    <h2>行为红线命中（{len(flag_cases)}）</h2>
    {cards}
  </section>""")

    # 结论页
    regressed_hint = "存在需关注的红线命中，建议排查对应样本。" if flag_cases else "全部行为红线通过。"
    slides.append(f"""
  <section class="slide">
    <p class="kicker">Takeaway</p>
    <h2>结论</h2>
    <p class="sub">{escape(regressed_hint)} 逐样本明细见 per-run 评分文件与 markdown 报告。</p>
  </section>""")

    return _TEMPLATE.format(slides="\n".join(slides), total=len(slides), title=escape(title or result.run_file))


def save_slides(result: MetricResult, reports_dir: Path, title: str = "") -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / result.run_file.replace(".jsonl", "_slides.html")
    path.write_text(render_slides(result, title), encoding="utf-8")
    return path
