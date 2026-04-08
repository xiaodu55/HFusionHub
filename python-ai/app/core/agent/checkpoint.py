"""
Agent Checkpoint — persistent state for agent task pause and precise resume.

Provides:
- ``CheckpointManager`` — SQLite-backed save/restore for agent execution state
- ``Checkpoint`` — immutable snapshot of agent state at a specific step
- Auto-checkpoint hooks for ReactAgent and approval flows

Usage::

    from app.core.agent.checkpoint import get_checkpoint_manager

    mgr = get_checkpoint_manager()
    cp = Checkpoint(run_id="abc", step_index=2, conversation_history=[...], ...)
    mgr.save(cp)

    # Later, on resume:
    restored = mgr.load("abc")
    if restored:
        agent.resume_from(restored)
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.utils.config import config

logger = logging.getLogger(__name__)

_CHECKPOINT_DB_DEFAULT = "data/checkpoints.db"


@dataclass
class Checkpoint:
    """Immutable snapshot of agent execution state at a specific step."""

    run_id: str
    step_index: int
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    retrieved_context: str = ""
    pending_tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    agent_state: Dict[str, Any] = field(default_factory=dict)
    sources: List[Dict[str, Any]] = field(default_factory=list)
    style: str = "detailed"
    max_tool_steps: int = 5
    created_at: str = field(default_factory=lambda: _now_iso())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Checkpoint":
        return cls(
            run_id=row["run_id"],
            step_index=row["step_index"],
            conversation_history=json.loads(row["conversation_history"] or "[]"),
            retrieved_context=row["retrieved_context"] or "",
            pending_tool_calls=json.loads(row["pending_tool_calls"] or "[]"),
            agent_state=json.loads(row["agent_state"] or "{}"),
            sources=json.loads(row["sources"] or "[]"),
            style=row["style"] or "detailed",
            max_tool_steps=row["max_tool_steps"] or 5,
            created_at=row["created_at"],
        )


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


class CheckpointManager:
    """SQLite-backed checkpoint store for agent execution state.

    Thread-safe — uses a reentrant lock.  Designed for single-node deployments;
    multi-node setups should replace the backend with a shared store (MySQL/Redis).
    """

    def __init__(self, database_path: Optional[str] = None):
        self._path = Path(database_path or getattr(config, "CHECKPOINT_DB_PATH", None) or _CHECKPOINT_DB_DEFAULT)
        self._lock = threading.Lock()
        if str(self._path) != ":memory:":
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_checkpoints (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id      TEXT    NOT NULL,
                    step_index  INTEGER NOT NULL DEFAULT 0,
                    conversation_history TEXT DEFAULT '[]',
                    retrieved_context    TEXT DEFAULT '',
                    pending_tool_calls   TEXT DEFAULT '[]',
                    agent_state          TEXT DEFAULT '{}',
                    sources              TEXT DEFAULT '[]',
                    style                TEXT DEFAULT 'detailed',
                    max_tool_steps       INTEGER DEFAULT 5,
                    created_at  TEXT    NOT NULL,
                    UNIQUE(run_id, step_index)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_checkpoint_run
                ON agent_checkpoints(run_id, step_index DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_checkpoint_created
                ON agent_checkpoints(created_at)
            """)

    # ── Public API ────────────────────────────────────────────────────

    def save(self, checkpoint: Checkpoint) -> int:
        """Persist a checkpoint. Returns the row id."""
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """INSERT OR REPLACE INTO agent_checkpoints
                   (run_id, step_index, conversation_history, retrieved_context,
                    pending_tool_calls, agent_state, sources, style, max_tool_steps, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    checkpoint.run_id,
                    checkpoint.step_index,
                    json.dumps(checkpoint.conversation_history, ensure_ascii=False),
                    checkpoint.retrieved_context,
                    json.dumps(checkpoint.pending_tool_calls, ensure_ascii=False),
                    json.dumps(checkpoint.agent_state, ensure_ascii=False),
                    json.dumps(checkpoint.sources, ensure_ascii=False),
                    checkpoint.style,
                    checkpoint.max_tool_steps,
                    checkpoint.created_at,
                ),
            )
            row_id = cursor.lastrowid or 0
        logger.debug("Checkpoint saved: run=%s step=%d id=%d", checkpoint.run_id, checkpoint.step_index, row_id)
        return row_id

    def load(self, run_id: str) -> Optional[Checkpoint]:
        """Load the latest checkpoint for a run."""
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM agent_checkpoints WHERE run_id = ? ORDER BY step_index DESC LIMIT 1",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return Checkpoint.from_row(row)

    def load_at_step(self, run_id: str, step_index: int) -> Optional[Checkpoint]:
        """Load checkpoint at a specific step."""
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM agent_checkpoints WHERE run_id = ? AND step_index = ?",
                (run_id, step_index),
            ).fetchone()
        if row is None:
            return None
        return Checkpoint.from_row(row)

    def list_for_run(self, run_id: str) -> List[Checkpoint]:
        """All checkpoints for a run, ordered by step."""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_checkpoints WHERE run_id = ? ORDER BY step_index",
                (run_id,),
            ).fetchall()
        return [Checkpoint.from_row(r) for r in rows]

    def delete(self, run_id: str) -> int:
        """Remove all checkpoints for a run. Returns count deleted."""
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM agent_checkpoints WHERE run_id = ?", (run_id,),
            )
        count = cursor.rowcount
        if count:
            logger.info("Deleted %d checkpoints for run=%s", count, run_id)
        return count

    def prune(self, max_age_days: int = 7) -> int:
        """Remove checkpoints older than *max_age_days*. Returns count removed."""
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM agent_checkpoints WHERE created_at < datetime('now', ? || ' days')",
                (f"-{max_age_days}",),
            )
        count = cursor.rowcount
        if count:
            logger.info("Pruned %d checkpoints older than %d days", count, max_age_days)
        return count

    def count(self) -> int:
        """Total number of stored checkpoints."""
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM agent_checkpoints").fetchone()
        return row["cnt"] if row else 0


# ── Auto-checkpoint helpers ────────────────────────────────────────────


def build_checkpoint_from_agent(
    agent: Any,  # ReactAgent (lazy import)
    run_id: str,
    step_index: int,
    *,
    extra_state: Optional[Dict[str, Any]] = None,
) -> Checkpoint:
    """Build a Checkpoint from the current ReactAgent state.

    Call this after each ReAct step or when entering approval wait.
    """
    return Checkpoint(
        run_id=run_id,
        step_index=step_index,
        conversation_history=getattr(agent, "_checkpoint_history", []),
        retrieved_context=getattr(agent, "_checkpoint_context", ""),
        pending_tool_calls=getattr(agent, "_checkpoint_pending_tools", []),
        agent_state=extra_state or {},
        sources=list(getattr(agent, "_last_sources", [])),
        style=getattr(agent, "style", "detailed"),
        max_tool_steps=getattr(agent, "max_steps", 5),
    )


# ── Singleton ──────────────────────────────────────────────────────────

_checkpoint_manager: Optional[CheckpointManager] = None


def get_checkpoint_manager() -> CheckpointManager:
    global _checkpoint_manager
    if _checkpoint_manager is None:
        _checkpoint_manager = CheckpointManager()
    return _checkpoint_manager


__all__ = [
    "Checkpoint",
    "CheckpointManager",
    "build_checkpoint_from_agent",
    "get_checkpoint_manager",
]
