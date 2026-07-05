"""LLM-as-judge 生成质量评审（三指标，单次调用输出 JSON）。

- faithfulness: 回答是否忠实于检索上下文（无编造）；
- answer_correctness: 回答与参考答案的语义正确性（有 ground_truth 才评）；
- answer_relevancy: 回答与问题的相关性。

走 ModelGateway 单轨（get_llm）+ judge_gate（私有部署可强制内网评审模型）。
N 次评审取均值抑制判分方差；评审异常/不可评审样本记录 skip_reason 而非失败。
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Dict, List, Optional

from ...llm import ChatMessage, get_llm
from ...llm.judge_gate import resolve_judge_model
from ..schemas import CaseMetric, EvalRecord

_JUDGE_PROMPT = """你是严格的 RAG 系统评审员。根据以下材料打分（每项 0.0~1.0，两位小数）：

[用户问题]
{query}

[检索上下文]
{contexts}

[系统回答]
{answer}
{ground_truth_block}
请只输出 JSON：{{"faithfulness": 0.0, "answer_correctness": 0.0, "answer_relevancy": 0.0}}
- faithfulness：回答是否完全由上下文支撑、无编造信息
- answer_correctness：回答与参考答案的语义一致性{gt_note}
- answer_relevancy：回答与用户问题的相关程度
{no_gt_note}"""


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _parse_scores(text: str) -> Optional[Dict[str, float]]:
    """从评审模型输出中稳健提取三项分数（容忍代码块/前后缀文本）。"""
    match = re.search(r"\{[^{}]*\"faithfulness\"[^{}]*\}", text, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    scores = {}
    for key in ("faithfulness", "answer_correctness", "answer_relevancy"):
        raw = data.get(key)
        if raw is None:
            return None
        scores[key] = _clamp(float(raw))
    return scores


_CACHE_PATH = Path("data/eval_harness/judge_cache.json")
_cache_lock = threading.Lock()


def _cache_key(record: EvalRecord, model: Optional[str]) -> str:
    raw = f"{model or 'default'}|{record.query}|{record.answer}|{record.ground_truth or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> Optional[Dict[str, float]]:
    try:
        with _cache_lock:
            if _CACHE_PATH.exists():
                data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
                scores = data.get(key)
                return {k: float(v) for k, v in scores.items()} if scores else None
    except Exception:
        pass
    return None


def _cache_put(key: str, scores: Dict[str, float]) -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _cache_lock:
            data = {}
            if _CACHE_PATH.exists():
                data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
            data[key] = scores
            _CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass  # 缓存写入失败不影响评分主流程


async def judge_sample(record: EvalRecord, judge_model: Optional[str] = None,
                       runs: int = 1, temperature: float = 0.2) -> CaseMetric:
    """对单条记录执行 LLM 评审。异常/不可评审返回 skip_reason 而非抛错。"""
    contexts_text = "\n\n".join(f"[{i}] {c}" for i, c in enumerate(record.contexts, 1)) or "（无检索上下文）"
    has_gt = bool((record.ground_truth or "").strip())
    gt_block = f"\n[参考答案]\n{record.ground_truth}" if has_gt else ""
    gt_note = "（有参考答案时以此为准）" if has_gt else ""
    prompt = _JUDGE_PROMPT.format(
        query=record.query, contexts=contexts_text, answer=record.answer,
        ground_truth_block=gt_block, gt_note=gt_note,
        no_gt_note="" if has_gt else "\n- 无参考答案时 answer_correctness 请依据上下文合理性给分，并在分数上保守",
    )
    resolved = resolve_judge_model(judge_model)

    cache_key = _cache_key(record, resolved)
    cached = _cache_get(cache_key)
    if cached is not None:
        return CaseMetric(query_id=record.query_id, metrics=cached)

    all_scores: List[Dict[str, float]] = []
    skip_reason: Optional[str] = None
    for _ in range(max(1, runs)):
        try:
            llm = get_llm(model=resolved)
            response = await llm.chat(
                messages=[ChatMessage(role="user", content=prompt)],
                temperature=temperature,
            )
            scores = _parse_scores(response.content)
            if scores is None:
                skip_reason = skip_reason or "judge output unparseable"
                continue
            all_scores.append(scores)
        except Exception as exc:  # 评审失败不阻断整体评分
            skip_reason = skip_reason or f"judge error: {type(exc).__name__}: {exc}"[:200]

    if not all_scores:
        return CaseMetric(query_id=record.query_id, metrics={}, skip_reason=skip_reason or "judge unavailable")

    averaged = {
        key: round(sum(s[key] for s in all_scores) / len(all_scores), 4)
        for key in ("faithfulness", "answer_correctness", "answer_relevancy")
    }
    _cache_put(cache_key, averaged)
    return CaseMetric(query_id=record.query_id, metrics=averaged)


def aggregate(cases: List[CaseMetric]) -> Dict[str, float]:
    judged = [c for c in cases if c.metrics and not c.skip_reason]
    if not judged:
        return {}
    keys = ("faithfulness", "answer_correctness", "answer_relevancy")
    return {
        f"{key}_mean": round(sum(c.metrics[key] for c in judged) / len(judged), 4)
        for key in keys
        if all(key in c.metrics for c in judged)
    }
