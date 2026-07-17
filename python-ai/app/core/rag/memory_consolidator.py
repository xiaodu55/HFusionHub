"""
Memory Consolidator — automatic extraction and consolidation of conversation memory.

Provides:
- ``MemoryConsolidator`` — extract structured memories from conversations
- ``MemoryEntry`` dataclass — a single extracted memory fact
- Consolidation trigger: periodic or on conversation close
- Memory scoring: importance, recency, relevance

Usage::

    from app.core.rag.memory_consolidator import get_memory_consolidator

    consolidator = get_memory_consolidator()
    entries = await consolidator.extract_memories(
        conversation_id=123,
        messages=history,
        user_id=456,
    )
    # entries is List[MemoryEntry] — ready for storage
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC
from typing import Any

from app.core.llm.base import BaseLLM
from app.core.llm.structured_output import generate_structured

logger = logging.getLogger(__name__)

MEMORY_EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "memories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fact": {"type": "string", "description": "A single, atomic fact about the user or conversation"},
                    "category": {"type": "string", "enum": ["preference", "fact", "goal", "context", "decision"]},
                    "importance": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": ["fact", "category", "importance"],
            },
            "maxItems": 10,
        },
    },
    "required": ["memories"],
}

MEMORY_EXTRACTION_PROMPT = """Analyze the conversation below and extract important facts about the user that should be remembered for future interactions.

Rules:
1. Extract ONLY atomic, standalone facts (one piece of information per memory)
2. Categorize each as:
   - preference: what the user likes/dislikes/wants
   - fact: objective information about the user or their context
   - goal: a stated objective or task the user is working toward
   - context: situational information (current project, role, etc.)
   - decision: a conclusion or choice the user made
3. Assign importance (0.0-1.0):
   - 1.0: Critical (identity, core preferences, ongoing goals)
   - 0.7: Important (project details, recurring preferences)
   - 0.5: Useful (context that may help future conversations)
   - 0.3: Nice-to-know (transient information)
   - 0.0: Not worth remembering (do not extract)
4. Assign confidence (0.0-1.0): how certain you are about this fact
5. Extract at most 10 memories
6. If nothing significant to remember, return an empty array

Conversation:
{conversation}

Return a JSON object with a "memories" array."""


@dataclass
class MemoryEntry:
    """A single extracted memory fact."""
    fact: str
    category: str  # preference | fact | goal | context | decision
    importance: float  # 0.0–1.0
    confidence: float = 0.8  # 0.0–1.0
    source_message_ids: list[str] = field(default_factory=list)
    conversation_id: int | None = None
    user_id: int | None = None
    extracted_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact": self.fact,
            "category": self.category,
            "importance": self.importance,
            "confidence": self.confidence,
            "source_message_ids": self.source_message_ids,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "extracted_at": self.extracted_at or _now_iso(),
        }


@dataclass
class ConsolidationResult:
    entries: list[MemoryEntry]
    total_tokens: int = 0
    extraction_time_ms: float = 0.0
    conversation_too_short: bool = False

    @property
    def high_value_entries(self) -> list[MemoryEntry]:
        return [e for e in self.entries if e.importance >= 0.7]

    @property
    def summary(self) -> str:
        if not self.entries:
            return "No significant memories extracted"
        categories: dict[str, int] = {}
        for e in self.entries:
            categories[e.category] = categories.get(e.category, 0) + 1
        parts = [f"{v} {k}" for k, v in sorted(categories.items())]
        return f"{len(self.entries)} memories: {', '.join(parts)}"


def _now_iso() -> str:
    from datetime import datetime
    return datetime.now(UTC).isoformat()


class MemoryConsolidator:
    """Extract structured memories from conversations using LLM analysis.

    Features:
    - Importance-based memory scoring
    - Category classification (preference, fact, goal, context, decision)
    - Confidence estimation
    - Conversation length aware (skips very short conversations)
    - Duplicate detection via semantic similarity (simple keyword overlap)
    """

    def __init__(self, min_messages: int = 4, importance_threshold: float = 0.4):
        self.min_messages = min_messages
        self.importance_threshold = importance_threshold
        self._known_facts: set = set()  # simple dedup

    async def extract_memories(
        self,
        conversation_id: int,
        messages: list[dict[str, str]],
        user_id: int | None = None,
        llm: BaseLLM | None = None,
    ) -> ConsolidationResult:
        """Extract memories from a conversation.

        Skips conversations with fewer than ``min_messages`` user+assistant turns.
        """
        started = time.monotonic()

        # Skip short conversations
        substantive = [m for m in messages if m.get("role") in ("user", "assistant")]
        if len(substantive) < self.min_messages:
            return ConsolidationResult(entries=[], conversation_too_short=True)

        # Build conversation text
        convo_text = self._format_conversation(messages)

        # Resolve LLM
        if llm is None:
            from app.core.llm import get_llm
            llm = get_llm()

        # Extract memories via structured output
        try:
            result = await generate_structured(
                llm=llm,
                prompt=MEMORY_EXTRACTION_PROMPT.format(conversation=convo_text),
                output_schema=MEMORY_EXTRACTION_SCHEMA,
                temperature=0.2,
                max_tokens=2048,
                max_retries=1,
            )
        except Exception as e:
            logger.warning("Memory extraction failed for conversation %d: %s", conversation_id, e)
            return ConsolidationResult(entries=[])

        raw_memories = result.get("memories", [])
        entries: list[MemoryEntry] = []
        for raw in raw_memories:
            fact = (raw.get("fact") or "").strip()
            if not fact or len(fact) < 5:
                continue

            importance = float(raw.get("importance", 0.5))
            if importance < self.importance_threshold:
                continue

            # Simple dedup
            dedup_key = fact.lower()[:60]
            if dedup_key in self._known_facts:
                continue
            self._known_facts.add(dedup_key)

            entries.append(MemoryEntry(
                fact=fact,
                category=raw.get("category", "fact"),
                importance=importance,
                confidence=float(raw.get("confidence", 0.8)),
                conversation_id=conversation_id,
                user_id=user_id,
                extracted_at=_now_iso(),
            ))

        elapsed = (time.monotonic() - started) * 1000
        logger.info(
            "Memory extraction for conversation %d: %d entries in %.0fms",
            conversation_id, len(entries), elapsed,
        )
        return ConsolidationResult(entries=entries, extraction_time_ms=elapsed)

    async def merge_memories(
        self,
        existing: list[MemoryEntry],
        new_entries: list[MemoryEntry],
    ) -> list[MemoryEntry]:
        """Merge new memories with existing ones, updating or replacing as needed."""
        merged: dict[str, MemoryEntry] = {}

        for e in existing:
            merged[e.fact.lower()[:80]] = e

        for e in new_entries:
            key = e.fact.lower()[:80]
            if key in merged:
                old = merged[key]
                # Boost importance if reconfirmed
                old.importance = min(1.0, max(old.importance, e.importance) + 0.05)
                old.confidence = min(1.0, (old.confidence + e.confidence) / 2 + 0.1)
            else:
                merged[key] = e

        # Sort by importance descending, keep top 200
        sorted_entries = sorted(merged.values(), key=lambda e: e.importance, reverse=True)
        return sorted_entries[:200]

    @staticmethod
    def _format_conversation(messages: list[dict[str, str]]) -> str:
        """Format conversation for the extraction prompt."""
        lines: list[str] = []
        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if role == "system":
                continue
            label = "用户" if role == "user" else "助手"
            # Truncate long messages
            if len(content) > 500:
                content = content[:497] + "..."
            lines.append(f"[{label}]: {content}")
        return "\n".join(lines)

    def reset_dedup(self) -> None:
        """Clear the deduplication cache (e.g., between test runs)."""
        self._known_facts.clear()


# ── Singleton ──────────────────────────────────────────────────────────

_memory_consolidator: MemoryConsolidator | None = None


def get_memory_consolidator() -> MemoryConsolidator:
    global _memory_consolidator
    if _memory_consolidator is None:
        _memory_consolidator = MemoryConsolidator()
    return _memory_consolidator


__all__ = [
    "MemoryEntry",
    "ConsolidationResult",
    "MemoryConsolidator",
    "get_memory_consolidator",
]
