"""Durable, privacy-conscious history for retrieval evaluation runs.

The offline evaluator deliberately keeps the benchmark in source control.  This
store keeps the *outcome* of every execution across process restarts so the
console can show regressions over time without copying evaluation queries or
document content into operational telemetry.
"""

from __future__ import annotations

import builtins
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class EvaluationRun:
    run_id: str
    created_at: str
    knowledge_base_id: int | None
    label: str | None
    top_k: int
    case_count: int
    precision_at_k: float
    recall_at_k: float
    mean_reciprocal_rank: float
    failed_case_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "knowledge_base_id": self.knowledge_base_id,
            "label": self.label,
            "top_k": self.top_k,
            "case_count": self.case_count,
            "precision_at_k": self.precision_at_k,
            "recall_at_k": self.recall_at_k,
            "mean_reciprocal_rank": self.mean_reciprocal_rank,
            "failed_case_ids": self.failed_case_ids,
        }


class EvaluationRunStore:
    """Small SQLite repository for evaluation summaries.

    SQLite is intentional here: this service already owns the evaluation
    execution and the data is an append-only operational journal.  Deployments
    with a shared database can replace this class behind the same API without
    changing the FastAPI or frontend contracts.
    """

    def __init__(self, database_path: str):
        self._path = Path(database_path)
        self._lock = Lock()
        self._memory_connection: sqlite3.Connection | None = None
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
                CREATE TABLE IF NOT EXISTS rag_evaluation_runs (
                    run_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    knowledge_base_id INTEGER,
                    label TEXT,
                    top_k INTEGER NOT NULL,
                    case_count INTEGER NOT NULL,
                    precision_at_k REAL NOT NULL,
                    recall_at_k REAL NOT NULL,
                    mean_reciprocal_rank REAL NOT NULL,
                    failed_case_ids TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_rag_evaluation_runs_created_at
                ON rag_evaluation_runs(created_at DESC)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_rag_evaluation_runs_knowledge_base
                ON rag_evaluation_runs(knowledge_base_id, created_at DESC)
                """
            )

    def record(
        self,
        report: dict[str, Any],
        *,
        knowledge_base_id: int | None,
        label: str | None = None,
    ) -> EvaluationRun:
        summary = report["summary"]
        failed_case_ids = [
            str(case.get("case_id") or "unnamed-case")
            for case in report.get("cases", [])
            if case.get("recall_at_k", 0.0) < 1.0
        ]
        run = EvaluationRun(
            run_id=str(uuid4()),
            created_at=datetime.now(UTC).isoformat(),
            knowledge_base_id=knowledge_base_id,
            label=(label or "").strip() or None,
            top_k=int(summary["top_k"]),
            case_count=int(summary["case_count"]),
            precision_at_k=float(summary["precision_at_k"]),
            recall_at_k=float(summary["recall_at_k"]),
            mean_reciprocal_rank=float(summary["mean_reciprocal_rank"]),
            failed_case_ids=failed_case_ids,
        )
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO rag_evaluation_runs (
                    run_id, created_at, knowledge_base_id, label, top_k, case_count,
                    precision_at_k, recall_at_k, mean_reciprocal_rank, failed_case_ids
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id, run.created_at, run.knowledge_base_id, run.label,
                    run.top_k, run.case_count, run.precision_at_k,
                    run.recall_at_k, run.mean_reciprocal_rank,
                    json.dumps(run.failed_case_ids, ensure_ascii=False),
                ),
            )
        return run

    def list(
        self,
        *,
        limit: int = 50,
        knowledge_base_id: int | None = None,
    ) -> builtins.list[dict[str, Any]]:
        limit = max(1, min(limit, 200))
        query = "SELECT * FROM rag_evaluation_runs"
        parameters: list[Any] = []
        if knowledge_base_id is not None:
            query += " WHERE knowledge_base_id = ?"
            parameters.append(knowledge_base_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        parameters.append(limit)
        with self._lock, self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._row_to_run(row).to_dict() for row in rows]

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> EvaluationRun:
        return EvaluationRun(
            run_id=row["run_id"],
            created_at=row["created_at"],
            knowledge_base_id=row["knowledge_base_id"],
            label=row["label"],
            top_k=row["top_k"],
            case_count=row["case_count"],
            precision_at_k=row["precision_at_k"],
            recall_at_k=row["recall_at_k"],
            mean_reciprocal_rank=row["mean_reciprocal_rank"],
            failed_case_ids=json.loads(row["failed_case_ids"]),
        )


_run_store: EvaluationRunStore | None = None


def get_evaluation_run_store(database_path: str | None = None) -> EvaluationRunStore:
    global _run_store
    if _run_store is None:
        if database_path is None:
            from app.utils.config import config
            database_path = config.RAG_EVALUATION_DB_PATH
        _run_store = EvaluationRunStore(database_path)
    return _run_store


def reset_evaluation_run_store() -> None:
    global _run_store
    _run_store = None
