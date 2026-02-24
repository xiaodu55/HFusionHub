"""
Persistent Memory Manager — entity extraction, summarization, and retrieval.

Integrates with the Java backend's MemoryEntry storage via HTTP API.
Memories are user-scoped and can span multiple conversations.

Memory types:
  - entity_fact: a factual claim about a named entity (e.g., "用户喜欢 Python")
  - conversation_summary: compressed summary of a conversation segment
  - user_preference: a stated preference or instruction from the user
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-process memory store (for quick access during a session)
# Longer-term storage goes through the Java backend API.
# ---------------------------------------------------------------------------

class MemoryManager:
    """Manages persistent memories for conversations."""

    def __init__(self):
        self._pending_extractions: List[Dict[str, Any]] = []

    async def extract_entities(
        self,
        user_message: str,
        assistant_response: str,
    ) -> List[Dict[str, Any]]:
        """
        Extract entity facts from a conversation turn.

        Uses lightweight heuristics; can be upgraded to LLM-based extraction.

        Returns a list of {type, content, entities, importance} dicts.
        """
        facts: List[Dict[str, Any]] = []

        # Heuristic 1: User preference detection
        preference_keywords = ["我喜欢", "我更喜欢", "我希望", "请记住", "记住", "偏好", "我习惯"]
        for kw in preference_keywords:
            if kw in user_message:
                facts.append({
                    "type": "user_preference",
                    "content": user_message.strip(),
                    "entities": [],
                    "importance": 0.8,
                })
                break

        # Heuristic 2: Named entity + fact pairs (simple "X 是 Y" pattern)
        if "是" in user_message and len(user_message) < 200:
            facts.append({
                "type": "entity_fact",
                "content": user_message.strip(),
                "entities": [],
                "importance": 0.5,
            })

        # Heuristic 3: Conversation summarization trigger
        if len(assistant_response) > 500:
            summary = assistant_response[:300].rsplit("。", 1)[0] + "。"
            facts.append({
                "type": "conversation_summary",
                "content": summary,
                "entities": [],
                "importance": 0.3,
            })

        return facts

    def format_memories_for_context(
        self,
        memories: List[Dict[str, Any]],
        max_tokens: int = 2000,
    ) -> str:
        """
        Format retrieved memories as a context string for the LLM.

        Args:
            memories: List of memory dicts with type, content, importance
            max_tokens: Rough token budget for memories

        Returns:
            Formatted string for inclusion in the system prompt
        """
        if not memories:
            return ""

        lines = ["## 用户记忆（长期）\n"]
        char_budget = max_tokens * 3  # rough char-to-token ratio

        # Sort by importance (highest first)
        sorted_memories = sorted(memories, key=lambda m: m.get("importance", 0), reverse=True)

        chars_used = len(lines[0])
        for mem in sorted_memories:
            mem_type = mem.get("type", "entity_fact")
            content = mem.get("content", "")
            importance = mem.get("importance", 0.5)

            if mem_type == "user_preference":
                prefix = "🎯 偏好"
            elif mem_type == "conversation_summary":
                prefix = "📝 摘要"
            else:
                prefix = "💡 事实"

            line = f"- {prefix} (重要性: {importance:.1f}): {content}\n"
            if chars_used + len(line) > char_budget:
                break
            lines.append(line)
            chars_used += len(line)

        return "".join(lines)


# Global singleton
_memory_manager: Optional[MemoryManager] = None


def get_memory_manager() -> MemoryManager:
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager
