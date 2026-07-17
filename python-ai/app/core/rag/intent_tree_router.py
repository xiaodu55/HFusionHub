"""Runtime routing for the Java-managed intent tree."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

_SEPARATORS = re.compile(r"[\s\-_/\\,，。！？!?、:：;；()（）\[\]{}]+")
_GREETING_TERMS = {
    "你好", "您好", "嗨", "hello", "hi", "hey", "早上好", "中午好", "晚上好",
    "谢谢", "感谢", "再见", "拜拜", "在吗", "你是谁", "你叫什么",
}


def _normalize(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip().lower()


def _terms(value: Any) -> list[str]:
    normalized = _normalize(value)
    if not normalized:
        return []
    terms = [item for item in _SEPARATORS.split(normalized) if item]
    if len(normalized) >= 2:
        terms.extend(normalized[index:index + 2] for index in range(len(normalized) - 1))
    return list(dict.fromkeys(terms))


def is_greeting(query: str) -> bool:
    normalized = _normalize(query)
    return normalized in _GREETING_TERMS or any(
        normalized.startswith(term) and len(normalized) <= len(term) + 4
        for term in _GREETING_TERMS
    )


def _score(query: str, candidate: dict[str, Any]) -> float:
    normalized_query = _normalize(query)
    name = _normalize(candidate.get("name"))
    code = _normalize(candidate.get("intent_code"))
    description = _normalize(candidate.get("description"))
    path = _normalize(candidate.get("path"))
    if not normalized_query or not (name or code or description):
        return 0.0
    if name and name in normalized_query:
        return 1.0
    if code and code in normalized_query:
        return 0.95
    query_terms = set(_terms(normalized_query))
    weighted_terms = _terms(name) + _terms(code) + _terms(path) + _terms(description)[:16]
    overlap = len(query_terms.intersection(weighted_terms))
    overlap_score = min(0.78, overlap / max(1, min(8, len(set(weighted_terms)))) * 1.4)
    phrase_score = max(
        (len(term) / max(1, len(normalized_query)) for term in (name, code) if term and term in normalized_query),
        default=0.0,
    )
    similarity = max(
        SequenceMatcher(None, normalized_query, value).ratio()
        for value in (name, code, description[:120], path)
        if value
    )
    return min(0.94, max(overlap_score, phrase_score * 1.8, similarity * 0.62))


def resolve_intent_route(
    query: str,
    candidates: list[dict[str, Any]] | None,
    explicit_knowledge_base_id: int | None = None,
) -> dict[str, Any]:
    """Score authorized candidates and return a route decision."""
    if explicit_knowledge_base_id:
        return {"status": "explicit", "knowledge_base_id": explicit_knowledge_base_id, "top_k": None, "confidence": 1.0, "candidates": []}
    if is_greeting(query):
        return {"status": "chitchat", "knowledge_base_id": None, "top_k": None, "confidence": 1.0, "candidates": []}
    ranked = sorted(
        ((round(_score(query, candidate), 4), candidate) for candidate in (candidates or [])),
        key=lambda item: item[0], reverse=True,
    )
    ranked = [(score, candidate) for score, candidate in ranked if score >= 0.34]
    if not ranked:
        return {"status": "unmatched", "knowledge_base_id": None, "top_k": None, "confidence": 0.0, "candidates": []}
    top_score, top = ranked[0]
    second = ranked[1] if len(ranked) > 1 else None
    if second and second[0] >= 0.46 and top_score - second[0] < 0.12:
        top_kb, second_kb = top.get("knowledge_base_id"), second[1].get("knowledge_base_id")
        if top_kb and second_kb and top_kb != second_kb:
            options = [
                {"intent_code": item.get("intent_code"), "name": item.get("name"), "knowledge_base_id": item.get("knowledge_base_id")}
                for _, item in ranked[:3]
            ]
            return {
                "status": "ambiguous", "knowledge_base_id": None, "top_k": None,
                "confidence": top_score, "candidates": options,
                "message": "这个问题可能属于多个知识库，请选择回答范围：" + "、".join(item["name"] for item in options),
            }
    kb_id = top.get("knowledge_base_id")
    if not kb_id or str(top.get("kind", "KB")).upper() != "KB":
        return {"status": "matched_non_kb", "knowledge_base_id": None, "top_k": None, "confidence": top_score, "candidates": [top]}
    return {
        "status": "matched", "knowledge_base_id": int(kb_id),
        "top_k": max(1, min(int(top.get("top_k") or 5), 20)), "confidence": top_score,
        "intent_code": top.get("intent_code"), "intent_name": top.get("name"),
        "candidates": [{"intent_code": top.get("intent_code"), "name": top.get("name"), "knowledge_base_id": kb_id}],
    }
