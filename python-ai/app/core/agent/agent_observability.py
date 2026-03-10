"""Agent-level observability — durable SQLite trace store for agent runs.

Complements ``app.core.rag.observability`` (retrieval traces) by persisting
operational metadata for each agent run: latency, token usage, tool call
counts, approval duration, and aggregate statistics.  Deliberately omits
prompts, thoughts, and retrieved content — those belong to the retrieval
trace layer, not this operational journal.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Deque, Dict, List, Optional
from uuid import uuid4


# ── Data models ────────────────────────────────────────────────────────

@dataclass
class AgentTrace:
    """One agent run record — operational metadata only, no user content."""

    run_uuid: str
    knowledge_base_id: Optional[int]
    status: str  # completed | insufficient_evidence | tool_error | timeout | failed
    model: str = ""
    duration_ms: float = 0.0
    token_usage: Optional[Dict[str, int]] = None  # {prompt_tokens, completion_tokens, total_tokens}
    tool_calls_count: int = 0
    sources_count: int = 0
    step_count: int = 0
    approval_count: int = 0
    total_approval_duration_ms: float = 0.0
    error_code: Optional[str] = None
    error_detail: Optional[str] = None
    failed_tool: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return data


# ── Persistent store ───────────────────────────────────────────────────

class AgentTraceStore:
    """SQLite-backed append-only journal of agent run metadata.

    Designed after ``EvaluationRunStore`` — same SQLite + row_factory +
    lock pattern.  Deployments that need a shared database can replace the
    class behind the same public API.
    """

    def __init__(self, database_path: str):
        self._path = Path(database_path)
        self._lock = Lock()
        self._memory_connection: Optional[sqlite3.Connection] = None
        if database_path == ":memory:":
            self._memory_connection = sqlite3.connect(database_path, check_same_thread=False)
            self._memory_connection.row_factory = sqlite3.Row
        else:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        if self._memory_connection is not None:
            return self._memory_connection
        connection = sqlite3.connect(self._path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_traces (
                    run_uuid              TEXT PRIMARY KEY,
                    knowledge_base_id     INTEGER,
                    status                TEXT NOT NULL,
                    model                 TEXT DEFAULT '',
                    duration_ms           REAL DEFAULT 0.0,
                    token_usage           TEXT DEFAULT '{}',
                    tool_calls_count      INTEGER DEFAULT 0,
                    sources_count         INTEGER DEFAULT 0,
                    step_count            INTEGER DEFAULT 0,
                    approval_count        INTEGER DEFAULT 0,
                    total_approval_duration_ms REAL DEFAULT 0.0,
                    error_code            TEXT,
                    error_detail          TEXT,
                    failed_tool           TEXT,
                    created_at            TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_agent_traces_created
                ON agent_traces(created_at DESC)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_agent_traces_kb
                ON agent_traces(knowledge_base_id, created_at DESC)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_agent_traces_status
                ON agent_traces(status, created_at DESC)
                """
            )

    # ── CRUD ─────────────────────────────────────────────────────────

    def record(self, trace: AgentTrace) -> AgentTrace:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO agent_traces (
                    run_uuid, knowledge_base_id, status, model, duration_ms,
                    token_usage, tool_calls_count, sources_count, step_count,
                    approval_count, total_approval_duration_ms,
                    error_code, error_detail, failed_tool, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace.run_uuid,
                    trace.knowledge_base_id,
                    trace.status,
                    trace.model,
                    trace.duration_ms,
                    json.dumps(trace.token_usage or {}, ensure_ascii=False),
                    trace.tool_calls_count,
                    trace.sources_count,
                    trace.step_count,
                    trace.approval_count,
                    trace.total_approval_duration_ms,
                    trace.error_code,
                    trace.error_detail,
                    trace.failed_tool,
                    trace.created_at,
                ),
            )
        return trace

    def get(self, run_uuid: str) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM agent_traces WHERE run_uuid = ?", (run_uuid,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        knowledge_base_id: Optional[int] = None,
        status: Optional[str] = None,
        error_only: bool = False,
    ) -> List[Dict[str, Any]]:
        limit = max(1, min(limit, 200))
        offset = max(0, min(offset, 1000))
        clauses = ["1=1"]
        params: List[Any] = []
        if knowledge_base_id is not None:
            clauses.append("knowledge_base_id = ?")
            params.append(knowledge_base_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if error_only:
            clauses.append("error_code IS NOT NULL")
        where = " AND ".join(clauses)
        query = f"SELECT * FROM agent_traces WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self._lock, self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def count(
        self,
        *,
        knowledge_base_id: Optional[int] = None,
        status: Optional[str] = None,
        error_only: bool = False,
    ) -> int:
        clauses = ["1=1"]
        params: List[Any] = []
        if knowledge_base_id is not None:
            clauses.append("knowledge_base_id = ?")
            params.append(knowledge_base_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if error_only:
            clauses.append("error_code IS NOT NULL")
        where = " AND ".join(clauses)
        with self._lock, self._connect() as connection:
            row = connection.execute(
                f"SELECT COUNT(*) AS cnt FROM agent_traces WHERE {where}", params
            ).fetchone()
        return row["cnt"] if row else 0

    # ── Statistics ───────────────────────────────────────────────────

    def stats(
        self,
        *,
        window_days: int = 7,
        knowledge_base_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        window_days = max(1, min(window_days, 30))
        clauses = ["created_at >= datetime('now', ? || ' days')"]
        params: List[Any] = [f"-{window_days}"]
        if knowledge_base_id is not None:
            clauses.append("knowledge_base_id = ?")
            params.append(knowledge_base_id)
        where = " AND ".join(clauses)

        with self._lock, self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT
                    COUNT(*) AS total_runs,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
                    SUM(CASE WHEN status = 'insufficient_evidence' THEN 1 ELSE 0 END) AS insufficient,
                    SUM(CASE WHEN status = 'tool_error' THEN 1 ELSE 0 END) AS tool_errors,
                    SUM(CASE WHEN status = 'timeout' THEN 1 ELSE 0 END) AS timeouts,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                    AVG(duration_ms) AS avg_duration_ms,
                    AVG(tool_calls_count) AS avg_tool_calls,
                    AVG(sources_count) AS avg_sources,
                    SUM(tool_calls_count) AS total_tool_calls
                FROM agent_traces WHERE {where}
                """, params
            ).fetchone()

            # Daily breakdown
            daily_rows = connection.execute(
                f"""
                SELECT
                    DATE(created_at) AS day,
                    COUNT(*) AS count,
                    AVG(duration_ms) AS avg_duration_ms,
                    SUM(CASE WHEN error_code IS NOT NULL THEN 1 ELSE 0 END) AS errors
                FROM agent_traces WHERE {where}
                GROUP BY DATE(created_at)
                ORDER BY day
                """, params
            ).fetchall()

            # Error distribution
            error_rows = connection.execute(
                f"""
                SELECT error_code, COUNT(*) AS cnt
                FROM agent_traces WHERE {where} AND error_code IS NOT NULL
                GROUP BY error_code ORDER BY cnt DESC
                """, params
            ).fetchall()

        if row is None:
            return {"total_runs": 0, "knowledge_base_id": knowledge_base_id}

        total = row["total_runs"] or 0
        err_total = (row["tool_errors"] or 0) + (row["timeouts"] or 0) + (row["failed"] or 0)

        return {
            "knowledge_base_id": knowledge_base_id,
            "window_days": window_days,
            "total_runs": total,
            "completed": row["completed"] or 0,
            "insufficient_evidence": row["insufficient"] or 0,
            "tool_errors": row["tool_errors"] or 0,
            "timeouts": row["timeouts"] or 0,
            "failed": row["failed"] or 0,
            "failure_rate": round(err_total / total, 4) if total else 0.0,
            "avg_duration_ms": round(row["avg_duration_ms"] or 0, 2),
            "avg_tool_calls": round(row["avg_tool_calls"] or 0, 2),
            "avg_sources": round(row["avg_sources"] or 0, 2),
            "total_tool_calls": row["total_tool_calls"] or 0,
            "daily_metrics": [
                {
                    "date": r["day"],
                    "count": r["count"],
                    "avg_duration_ms": round(r["avg_duration_ms"] or 0, 2),
                    "errors": r["errors"],
                }
                for r in daily_rows
            ],
            "error_distribution": {r["error_code"]: r["cnt"] for r in error_rows},
        }

    def stale_runs(
        self,
        *,
        max_running_seconds: float = 120.0,
        knowledge_base_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Find runs that are still 'running' beyond the threshold."""
        clauses = [
            "status = 'running'",
            "created_at <= datetime('now', ? || ' seconds')",
        ]
        params: List[Any] = [f"-{max_running_seconds}"]
        if knowledge_base_id is not None:
            clauses.append("knowledge_base_id = ?")
            params.append(knowledge_base_id)
        where = " AND ".join(clauses)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM agent_traces WHERE {where} ORDER BY created_at DESC LIMIT 50",
                params,
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def clear(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM agent_traces")

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        # Parse JSON fields
        if isinstance(data.get("token_usage"), str):
            try:
                data["token_usage"] = json.loads(data["token_usage"])
            except (json.JSONDecodeError, TypeError):
                data["token_usage"] = {}
        return data


# ── Global singleton ───────────────────────────────────────────────────

_trace_store: Optional[AgentTraceStore] = None


def get_agent_trace_store(database_path: Optional[str] = None) -> AgentTraceStore:
    global _trace_store
    if _trace_store is None:
        if database_path is None:
            from app.utils.config import config
            database_path = getattr(config, 'AGENT_TRACE_DB_PATH',
                                    str(Path(config.MILVUS_LITE_PATH).parent / "agent_traces.db"))
        _trace_store = AgentTraceStore(database_path)
    return _trace_store


def reset_agent_trace_store() -> None:
    global _trace_store
    _trace_store = None
