"""Reranker A/B benchmark — lexical vs cross_encoder vs first-stage order.

P6 治理要求 cross_encoder 上线前先获得离线基准证明。本脚本在合成语料上
跑同一个一阶段检索（SyntheticRouter，召回 RAG_RERANK_CANDIDATE_COUNT 条），
分别用三种方式重排后计算 recall@k / nDCG@k / MRR 与单条耗时：

- ``none``           —— 一阶段 RRF 融合顺序（对照臂）
- ``lexical``        —— 当前默认（确定性词覆盖基线）
- ``cross_encoder``  —— sentence-transformers CrossEncoder（可选依赖）

用法：
    .venv/Scripts/python.exe scripts/eval_reranker.py            # 全部臂
    .venv/Scripts/python.exe scripts/eval_reranker.py --arms lexical,cross_encoder

报告写入 ``evaluation/reports/reranker_ab.json``（--report 覆盖路径）。
跨臂对比只看相对值：合成语料偏词法，cross_encoder 的真实收益需结合
真实知识库抽检；本基准的门槛是「不得显著劣于一阶段顺序」。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from eval_baseline import load_cases  # noqa: E402

DEFAULT_TOP_K = 10
DEFAULT_CANDIDATES = 20


def _recall_at_k(ranked_chunk_ids: list[str], expected: list[str], k: int) -> float:
    if not expected:
        return 0.0
    hits = sum(1 for chunk_id in ranked_chunk_ids[:k] if chunk_id in expected)
    return hits / len(expected)


def _ndcg_at_k(ranked_chunk_ids: list[str], expected: list[str], k: int) -> float:
    if not expected:
        return 0.0
    dcg = sum(
        1.0 / math.log2(position + 2)
        for position, chunk_id in enumerate(ranked_chunk_ids[:k])
        if chunk_id in expected
    )
    ideal = sum(1.0 / math.log2(position + 2) for position in range(min(len(expected), k)))
    return dcg / ideal if ideal else 0.0


def _mrr(ranked_chunk_ids: list[str], expected: list[str]) -> float:
    for position, chunk_id in enumerate(ranked_chunk_ids):
        if chunk_id in expected:
            return 1.0 / (position + 1)
    return 0.0


async def _arm_outcomes(arm: str, reranker, router, cases, candidates_k: int, top_k: int) -> dict:
    recalls, ndcgs, mrrs, latencies = [], [], [], []
    for case in cases:
        merged = await router.search(case.query, case.kb_id, candidates_k)
        candidates = [
            {
                "content": result.content,
                "score": result.score,
                "metadata": result.metadata or {},
            }
            for result in merged.results
        ]
        started = time.perf_counter()
        if reranker is not None:
            ranked, _debug = await reranker.rerank(case.query, candidates)
        else:
            ranked = candidates
        elapsed_ms = (time.perf_counter() - started) * 1000

        seen: list[str] = []
        for item in ranked:
            chunk_id = (item.get("metadata") or {}).get("chunk_id")
            if chunk_id is not None and str(chunk_id) not in seen:
                seen.append(str(chunk_id))

        recalls.append(_recall_at_k(seen, case.expected_chunk_ids, top_k))
        ndcgs.append(_ndcg_at_k(seen, case.expected_chunk_ids, top_k))
        mrrs.append(_mrr(seen, case.expected_chunk_ids))
        latencies.append(elapsed_ms)

    count = max(1, len(cases))
    return {
        "arm": arm,
        "recall_at_5": round(sum(recalls) / count, 4),
        "ndcg_at_10": round(sum(ndcgs) / count, 4),
        "mrr": round(sum(mrrs) / count, 4),
        "avg_rerank_ms": round(sum(latencies) / count, 2),
        "cases": len(cases),
    }


async def run(args: argparse.Namespace) -> list[dict]:
    from app.core.rag.reranker import CrossEncoderReranker, LexicalReranker
    from app.core.rag.synthetic_index import SyntheticIndex, SyntheticRouter

    kb_manifest = PROJECT_ROOT / "evaluation" / "kb" / "kb_manifest.json"
    cases = load_cases(PROJECT_ROOT / "evaluation" / "suite" / "cases.jsonl")
    router = SyntheticRouter(index=SyntheticIndex(manifest_path=kb_manifest))

    arms: list[tuple[str, object]] = [("none", None), ("lexical", LexicalReranker())]
    if "cross_encoder" in args.arms:
        try:
            model_name = args.model
            cross_encoder = CrossEncoderReranker(model_name)
            arms.append(("cross_encoder", cross_encoder))
        except Exception as error:
            print(f"[SKIP] cross_encoder unavailable ({type(error).__name__}: {error})", file=sys.stderr)

    arms = [arm for arm in arms if arm[0] in args.arms]
    outcomes = []
    for name, reranker in arms:
        outcome = await _arm_outcomes(name, reranker, router, cases, args.candidates, args.top_k)
        outcomes.append(outcome)
        print(f"[{name:>14}] recall@{args.top_k}={outcome['recall_at_5']:.3f} "
              f"ndcg@{args.top_k}={outcome['ndcg_at_10']:.3f} mrr={outcome['mrr']:.3f} "
              f"avg_ms={outcome['avg_rerank_ms']:.1f}")
    return outcomes


def main() -> int:
    parser = argparse.ArgumentParser(description="Reranker A/B benchmark on the synthetic corpus")
    parser.add_argument("--arms", default="none,lexical,cross_encoder",
                        help="逗号分隔的对比臂：none,lexical,cross_encoder")
    parser.add_argument("--model", default="BAAI/bge-reranker-base",
                        help="cross_encoder 模型名（默认 BAAI/bge-reranker-base）")
    parser.add_argument("--candidates", type=int, default=DEFAULT_CANDIDATES,
                        help="一阶段召回候选数（与 RAG_RERANK_CANDIDATE_COUNT 对齐）")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--report", default=str(PROJECT_ROOT / "evaluation" / "reports" / "reranker_ab.json"))
    args = parser.parse_args()

    import asyncio

    outcomes = asyncio.run(run(args))
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps({"arms": outcomes, "candidates": args.candidates, "top_k": args.top_k},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"report → {report_path}")

    # 门槛：cross_encoder 臂的 nDCG 不得劣于 none 臂（劣于即判定不推荐）
    by_name = {item["arm"]: item for item in outcomes}
    if "cross_encoder" in by_name and "none" in by_name:
        delta = by_name["cross_encoder"]["ndcg_at_10"] - by_name["none"]["ndcg_at_10"]
        verdict = "PASS" if delta >= -0.01 else "FAIL"
        print(f"cross_encoder vs none: ndcg@10 delta = {delta:+.4f} → {verdict}")
        return 0 if verdict == "PASS" else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
