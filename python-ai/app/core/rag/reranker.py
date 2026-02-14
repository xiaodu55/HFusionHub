"""Optional second-stage reranking with explicit, observable fallback.

RRF is a strong first-stage fusion method because it never compares unrelated
score scales. A cross-encoder can then inspect the query and candidate text
together, but it is deliberately opt-in: an unavailable model must not turn a
healthy retrieval request into an outage or silently pretend to have reranked.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Protocol, Tuple


class Reranker(Protocol):
    name: str

    async def rerank(self, query: str, candidates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        ...


@dataclass
class DisabledReranker:
    reason: str = "disabled"
    name: str = "disabled"

    async def rerank(self, query: str, candidates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        return candidates, {"applied": False, "reranker": self.name, "reason": self.reason}


@dataclass
class LexicalReranker:
    """Deterministic local baseline for testing the reranker path.

    It is not presented as a semantic model. It simply rewards query-term
    coverage, which makes it safe for local A/B and gives deployments a useful
    control arm before installing a cross-encoder.
    """

    name: str = "lexical"

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return set(re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", value.lower()))

    async def rerank(self, query: str, candidates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        terms = self._tokens(query)
        ranked: List[Dict[str, Any]] = []
        for candidate in candidates:
            content_terms = self._tokens(str(candidate.get("content", "")))
            coverage = len(terms & content_terms) / len(terms) if terms else 0.0
            item = {**candidate, "metadata": {**(candidate.get("metadata") or {})}}
            item["metadata"].update({
                "reranker": self.name,
                "rerank_score": round(coverage, 6),
                "pre_rerank_score": candidate.get("score", 0.0),
            })
            # Coverage dominates this local baseline; first-stage score breaks ties.
            item["score"] = coverage + float(candidate.get("score", 0.0)) * 0.001
            ranked.append(item)
        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked, {"applied": True, "reranker": self.name, "candidate_count": len(candidates)}


class CrossEncoderReranker:
    name = "cross_encoder"

    def __init__(self, model_name: str):
        from sentence_transformers import CrossEncoder
        self._model_name = model_name
        self._model = CrossEncoder(model_name)

    async def rerank(self, query: str, candidates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        pairs = [(query, str(candidate.get("content", ""))) for candidate in candidates]
        scores = await asyncio.to_thread(self._model.predict, pairs)
        ranked: List[Dict[str, Any]] = []
        for candidate, score in zip(candidates, scores):
            item = {**candidate, "metadata": {**(candidate.get("metadata") or {})}}
            item["metadata"].update({
                "reranker": self.name,
                "rerank_score": round(float(score), 6),
                "pre_rerank_score": candidate.get("score", 0.0),
            })
            item["score"] = float(score)
            ranked.append(item)
        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked, {
            "applied": True,
            "reranker": self.name,
            "model": self._model_name,
            "candidate_count": len(candidates),
        }


def get_reranker() -> Reranker:
    from app.utils.config import config

    mode = config.RAG_RERANKER_MODE.lower().strip()
    if mode in {"", "disabled", "off", "none"}:
        return DisabledReranker()
    if mode == "lexical":
        return LexicalReranker()
    if mode == "cross_encoder":
        try:
            return CrossEncoderReranker(config.RAG_RERANKER_MODEL)
        except (ImportError, OSError, RuntimeError) as error:
            return DisabledReranker(reason=f"cross_encoder_unavailable:{type(error).__name__}")
    return DisabledReranker(reason=f"unsupported_mode:{mode}")
