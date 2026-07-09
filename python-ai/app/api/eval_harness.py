"""评估中枢 API（内部数据面）：驱动运行 / 重放评分 / 报告 / A/B 对比。

与 rag.py 同守卫（X-Internal-Token + X-Tenant-Id）。评估会真实调用生产链路
（SSE 对话 + 检索评估），代价与真实流量相当 —— 请在评测环境使用。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..core.eval_harness import EvalSample, MetricResult
from ..core.eval_harness import diff as diff_mod
from ..core.eval_harness import report as report_mod
from ..core.eval_harness import runner as runner_mod
from ..core.eval_harness import score as score_mod
from ..core.eval_harness import slides as slides_mod
from ..utils.config import config

router = APIRouter(prefix="/api/eval-harness", tags=["eval-harness"])

# 数据集白名单目录：仅允许加载该目录下的 .jsonl（防目录穿越）
logger = logging.getLogger(__name__)
TENANT_ID_HEADER = "1"
DATASET_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "eval_sets"
REPORTS_DIR = Path("data/eval_harness/reports")


class _RunRequest(BaseModel):
    label: str = Field(default="run", max_length=60)
    knowledge_base_id: int = Field(ge=1)
    top_k: int = Field(default=5, ge=1, le=20)
    # 二选一：内联样本，或 dataset_name（scripts/eval_sets/<name>.jsonl 白名单）
    samples: Optional[List[Dict[str, Any]]] = Field(default=None, max_length=500)
    dataset_name: Optional[str] = Field(default=None, max_length=120)
    concurrency: Optional[int] = Field(default=None, ge=1, le=16)
    enable_judge: bool = False
    judge_runs: Optional[int] = Field(default=None, ge=1, le=5)


def _notify_java_record(run_file: str, request: _RunRequest, result: MetricResult) -> None:
    """评估完成后回调 Java 记录聚合摘要（eval_harness_runs 表）。

    失败仅告警不影响评估结果 —— Java 侧可通过 /api/eval-harness/report 按需拉取。
    """
    import httpx

    failed_ids = [c.query_id for c in result.cases
                  if any(isinstance(m, float) and m == 0.0 for m in c.metrics.values())][:200]
    java_base = str(config.JAVA_BACKEND_URL).rstrip("/")
    if java_base.endswith("/api"):
        java_base = java_base[:-4]
    body = {
        "run_file": run_file,
        "label": request.label,
        "knowledge_base_id": request.knowledge_base_id,
        "top_k": request.top_k,
        "record_count": result.meta.get("record_count", 0),
        "requires_rag_count": result.meta.get("requires_rag_count", 0),
        "judge_enabled": bool(result.meta.get("judge_enabled")),
        "judge_cases": result.meta.get("judge_cases", 0),
        "overall": result.overall,
        "failed_case_ids": {"failed": failed_ids},
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                java_base + "/api/internal/eval-harness/record",
                json=body,
                headers={
                    "X-Internal-Token": config.INTERNAL_API_TOKEN,
                    "X-Tenant-Id": TENANT_ID_HEADER,
                },
            )
        if resp.status_code >= 400:
            logger.warning("[eval-harness] Java record callback failed: %s %s",
                           resp.status_code, resp.text[:200])
        else:
            logger.info("[eval-harness] Java record callback ok: %s", run_file)
    except Exception as exc:
        logger.warning("[eval-harness] Java record callback error: %s", exc)


def _load_samples(request: _RunRequest) -> List[EvalSample]:
    if request.samples:
        raw = request.samples
    elif request.dataset_name:
        safe = request.dataset_name
        if "/" in safe or "\\" in safe or ".." in safe or not safe.endswith(".jsonl"):
            raise HTTPException(status_code=422, detail="invalid dataset name")
        path = DATASET_DIR / safe
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"dataset not found: {safe}")
        raw = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        raise HTTPException(status_code=422, detail="samples or dataset_name is required")

    samples: List[EvalSample] = []
    for i, item in enumerate(raw):
        try:
            samples.append(EvalSample(
                query_id=str(item.get("query_id") or f"case-{i + 1}"),
                query=str(item["query"]),
                expected_document_ids=[str(x) for x in (item.get("expected_document_ids")
                                                        or item.get("expected_documents") or [])],
                requires_rag=bool(item.get("requires_rag", True)),
                ground_truth=item.get("ground_truth"),
                tags={k: str(v) for k, v in (item.get("tags") or {}).items()},
                history=[{"role": str(m.get("role")), "content": str(m.get("content"))}
                         for m in (item.get("history") or [])],
                seed_messages=[{"role": str(m.get("role")), "content": str(m.get("content"))}
                               for m in (item.get("seed_messages") or [])],
                user_id=item.get("user_id"),
                conversation_id=item.get("conversation_id"),
            ))
        except KeyError as exc:
            raise HTTPException(status_code=422, detail=f"sample {i} missing field: {exc}") from exc
    if not samples:
        raise HTTPException(status_code=422, detail="no usable samples")
    return samples


@router.post("/run")
async def start_run(request: _RunRequest) -> Dict[str, Any]:
    """驱动一次完整评估（同步执行；样本量大时耗时与并发配置相关）。"""
    samples = _load_samples(request)
    headers = {"X-Internal-Token": config.INTERNAL_API_TOKEN, "X-Tenant-Id": "1"}
    # runner 使用同步 httpx 自调用本服务 —— 必须进线程池执行，
    # 否则会阻塞事件循环造成"自己等自己"的死锁
    import asyncio
    run_file = await asyncio.to_thread(
        runner_mod.run_dataset,
        samples,
        config.EVAL_BASE_URL,
        headers,
        request.knowledge_base_id,
        request.top_k,
        request.concurrency or config.EVAL_CONCURRENCY,
        float(config.EVAL_TIMEOUT_S),
        None,
        request.label,
        None,
    )
    # 运行后立即评分（评审按开关；报告同步生成）
    result = await score_mod.score_run(
        run_file.name, enable_judge=request.enable_judge,
        judge_model=config.EVAL_JUDGE_MODEL or None,
        judge_runs=request.judge_runs or config.EVAL_JUDGE_RUNS,
        retrieval_k=request.top_k,
    )
    report_mod.save_report(result, REPORTS_DIR, title=request.label)
    _notify_java_record(run_file.name, request, result)
    return {"run_file": run_file.name, "summary": result.overall, "meta": result.meta}


class _ScoreRequest(BaseModel):
    run_file: str = Field(max_length=160)
    enable_judge: bool = False
    judge_model: Optional[str] = Field(default=None, max_length=120)
    judge_runs: int = Field(default=1, ge=1, le=5)
    retrieval_k: int = Field(default=5, ge=1, le=20)


@router.post("/score")
async def score(request: _ScoreRequest) -> Dict[str, Any]:
    try:
        result = await score_mod.score_run(
            request.run_file, enable_judge=request.enable_judge,
            judge_model=request.judge_model or config.EVAL_JUDGE_MODEL or None,
            judge_runs=request.judge_runs, retrieval_k=request.retrieval_k,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    path = score_mod.save_scores(result, REPORTS_DIR)
    slides_mod.save_slides(result, REPORTS_DIR, title=request.label)
    return {"scores_file": path.name, "slides_file": path.name.replace("_scores.json", "_slides.html"), "result": result.to_dict()}


@router.get("/runs")
async def list_runs() -> Dict[str, Any]:
    return {"runs": runner_mod.list_run_files()}


@router.get("/slides")
async def get_slides(run_file: str) -> Dict[str, Any]:
    if "/" in run_file or "\\" in run_file or ".." in run_file:
        raise HTTPException(status_code=422, detail="invalid run file name")
    slides_path = REPORTS_DIR / run_file.replace(".jsonl", "_slides.html")
    if not slides_path.exists():
        raise HTTPException(status_code=404, detail="slides not found; run score first")
    return {"run_file": run_file, "html": slides_path.read_text(encoding="utf-8")}


@router.get("/report")
async def get_report(run_file: str) -> Dict[str, Any]:
    if "/" in run_file or "\\" in run_file or ".." in run_file:
        raise HTTPException(status_code=422, detail="invalid run file name")
    report_path = REPORTS_DIR / run_file.replace(".jsonl", "_report.md")
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="report not found; run score first")
    return {"run_file": run_file, "report": report_path.read_text(encoding="utf-8")}


class _DiffRequest(BaseModel):
    base_run: str = Field(max_length=160)
    candidate_run: str = Field(max_length=160)


@router.post("/diff")
async def diff(request: _DiffRequest) -> Dict[str, Any]:
    try:
        base = score_mod.load_scores(REPORTS_DIR, request.base_run)
        candidate = score_mod.load_scores(REPORTS_DIR, request.candidate_run)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    rows = diff_mod.diff_metrics(base.get("overall", {}), candidate.get("overall", {}))
    return {
        "base_run": request.base_run,
        "candidate_run": request.candidate_run,
        "rows": rows,
        "has_regression": diff_mod.has_regression(rows),
    }


@router.get("/datasets")
async def list_datasets() -> Dict[str, Any]:
    if not DATASET_DIR.exists():
        return {"datasets": []}
    return {"datasets": sorted(p.name for p in DATASET_DIR.glob("*.jsonl"))}
