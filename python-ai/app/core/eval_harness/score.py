"""score 阶段：重放已记录的运行并聚合全部指标（不重打目标系统 API）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .metrics import behavior, llm_judge, retrieval, ttft
from .runner import load_run_file
from .schemas import EvalRecord, MetricResult


async def score_run(run_file: str, runs_dir: Optional[Path] = None,
                    enable_judge: bool = False, judge_model: Optional[str] = None,
                    judge_runs: int = 1, retrieval_k: int = 5,
                    judge_sample_limit: Optional[int] = None) -> MetricResult:
    """重放一个 run 文件：检索/行为/TTFT 指标总是计算；LLM 评审按开关执行。

    judge_sample_limit 限制评审条数（评审调用有真实 token 成本）。
    """
    records: List[EvalRecord] = load_run_file(run_file, runs_dir)
    if not records:
        return MetricResult(run_file=run_file, overall={}, meta={"error": "run file is empty"})

    retrieval_cases = [retrieval.evaluate_case(r, retrieval_k) for r in records
                       if r.requires_rag]
    behavior_cases = [behavior.evaluate_case(r) for r in records]
    ttft_metrics = ttft.aggregate(records)

    judge_cases = []
    if enable_judge:
        targets = [r for r in records if r.final_status == "completed"]
        if judge_sample_limit is not None:
            targets = targets[:judge_sample_limit]
        for record in targets:
            judge_cases.append(await llm_judge.judge_sample(record, judge_model=judge_model,
                                                            runs=judge_runs))

    overall: dict = {}
    overall.update({f"retrieval_{k}": v for k, v in retrieval.aggregate(records, retrieval_k).items()})
    overall.update(behavior.aggregate(records))
    overall.update(ttft_metrics)
    overall.update({f"judge_{k}": v for k, v in llm_judge.aggregate(judge_cases).items()})

    # 切片汇总：按任意标签维度拆检索指标（如 intent_l1 / difficulty / trap_type）
    by_tag: dict = {}
    tag_keys = sorted({k for r in records for k in (r.tags or {})})
    for tag_key in tag_keys:
        groups: dict = {}
        for r in records:
            value = (r.tags or {}).get(tag_key)
            if value:
                groups.setdefault(value, []).append(r)
        if len(groups) < 2:
            continue  # 单一取值的维度无对比价值
        by_tag[tag_key] = {
            value: retrieval.aggregate(group, retrieval_k)
            for value, group in sorted(groups.items())
        }

    meta = {
        "record_count": len(records),
        "requires_rag_count": sum(1 for r in records if r.requires_rag),
        "retrieval_k": retrieval_k,
        "judge_enabled": enable_judge,
        "judge_cases": len(judge_cases),
        "judge_skipped": sum(1 for c in judge_cases if c.skip_reason),
    }
    if by_tag:
        meta["by_tag"] = by_tag
    for r in records:
        if r.error:
            meta.setdefault("record_errors", []).append({"query_id": r.query_id, "error": r.error})

    all_cases = retrieval_cases + [c for c in judge_cases]
    behavior_by_id = {c.query_id: c for c in behavior_cases}
    merged_cases = []
    for c in all_cases:
        merged = c
        extra = behavior_by_id.get(c.query_id)
        if extra and extra.flags:
            merged = type(c)(query_id=c.query_id, metrics=dict(c.metrics),
                             skip_reason=c.skip_reason, flags=extra.flags)
        merged_cases.append(merged)
    # 行为 flag 也应出现在无检索指标的用例上（requires_rag=false 样本无 retrieval case）
    existing_ids = {c.query_id for c in merged_cases}
    for qc in behavior_cases:
        if qc.query_id not in existing_ids and qc.flags:
            merged_cases.append(qc)

    return MetricResult(run_file=run_file, overall=overall, cases=merged_cases, meta=meta)


def save_scores(result: MetricResult, reports_dir: Path) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / result.run_file.replace(".jsonl", "_scores.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
    return path


def load_scores(reports_dir: Path, run_file: str) -> dict:
    path = reports_dir / run_file.replace(".jsonl", "_scores.json")
    if not path.exists():
        raise FileNotFoundError(f"scores not found for {run_file}; run score first")
    return json.loads(path.read_text(encoding="utf-8"))
