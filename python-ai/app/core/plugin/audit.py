"""Plugin audit trail — persistent audit with Java backend sync.

Architecture:
  1. In-memory buffer (fast writes)
  2. Local SQLite file (crash recovery)
  3. Background thread flushes to Java backend with exponential backoff retry

Every plugin mutation is recorded with:
  - trace_id for correlation
  - version and manifest_hash for integrity
  - resource_usage snapshot when available
  - Structured JSON for machine readability
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ACTION_INSTALL = "install"
ACTION_ENABLE = "enable"
ACTION_DISABLE = "disable"
ACTION_UPDATE = "update"
ACTION_UNINSTALL = "uninstall"
ACTION_ROLLBACK = "rollback"
ACTION_TOOL_EXECUTED = "tool_executed"
ACTION_TOOL_FAILED = "tool_failed"
ACTION_SANDBOX_VIOLATION = "sandbox_violation"

VALID_ACTIONS = {
    ACTION_INSTALL, ACTION_ENABLE, ACTION_DISABLE,
    ACTION_UPDATE, ACTION_UNINSTALL, ACTION_ROLLBACK,
    ACTION_TOOL_EXECUTED, ACTION_TOOL_FAILED, ACTION_SANDBOX_VIOLATION,
}

# SQLite persistence path — configurable via HFUSIONHUB_AUDIT_DB_PATH
_DB_DIR = os.environ.get(
    "HFUSIONHUB_AUDIT_DB_PATH",
    os.path.join(os.path.expanduser("~"), ".hfusionhub", "audit"),
)
_DB_PATH = os.path.join(_DB_DIR, "plugin_audit.db")

# Java backend endpoint
_JAVA_AUDIT_ENDPOINT = "/internal/plugin/audit-logs"

# Retry config
_MAX_RETRIES = 5
_RETRY_BASE_DELAY = 2.0  # seconds
_FLUSH_INTERVAL = 30.0  # seconds


@dataclass
class AuditEntry:
    """A single audit log entry with full traceability."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    plugin_id: str = ""
    plugin_name: str = ""
    plugin_version: str = ""
    action: str = ""
    operator_id: Optional[int] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    reason: Optional[str] = None
    manifest_hash: Optional[str] = None
    archive_hash: Optional[str] = None
    trace_id: Optional[str] = None
    resource_usage: Optional[Dict[str, Any]] = None
    timestamp: float = field(default_factory=time.time)
    synced: bool = False
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "plugin_id": self.plugin_id,
            "plugin_name": self.plugin_name,
            "plugin_version": self.plugin_version,
            "action": self.action,
            "operator_id": self.operator_id,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "reason": self.reason,
            "manifest_hash": self.manifest_hash,
            "archive_hash": self.archive_hash,
            "trace_id": self.trace_id,
            "resource_usage": self.resource_usage,
            "timestamp": self.timestamp,
        }

    def to_wire(self) -> Dict[str, Any]:
        """Format for Java backend POST."""
        return {
            "eventId": self.id,
            "pluginId": self.plugin_id,
            "pluginName": self.plugin_name,
            "pluginVersion": self.plugin_version,
            "action": self.action,
            "operatorId": self.operator_id,
            "oldValue": self.old_value,
            "newValue": self.new_value,
            "reason": self.reason,
            "manifestHash": self.manifest_hash,
            "archiveHash": self.archive_hash,
            "traceId": self.trace_id,
            "resourceUsage": json.dumps(self.resource_usage) if self.resource_usage else None,
        }


# ── SQLite persistence ──────────────────────────────────────────────

def _init_db() -> sqlite3.Connection:
    os.makedirs(_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)

    # Migration: add dead_letter column if DB existed before this feature
    try:
        conn.execute("ALTER TABLE audit_queue ADD COLUMN dead_letter INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists

    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_queue (
            id TEXT PRIMARY KEY,
            entry_json TEXT NOT NULL,
            synced INTEGER NOT NULL DEFAULT 0,
            dead_letter INTEGER NOT NULL DEFAULT 0,
            retry_count INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            last_attempt_at REAL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_aq_synced ON audit_queue (synced)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_aq_dead_letter ON audit_queue (dead_letter)")
    conn.commit()
    return conn


_db_lock = threading.Lock()
_db_conn: Optional[sqlite3.Connection] = None


def _get_db() -> sqlite3.Connection:
    global _db_conn
    if _db_conn is None:
        _db_conn = _init_db()
    return _db_conn


def _reset_db(new_dir: Optional[str] = None) -> None:
    """Reset the SQLite connection and optionally redirect to a new directory.

    Used by tests to isolate the audit database in a temp directory.
    Pass a directory path to redirect; pass None to restore the default.
    """
    global _db_conn, _DB_DIR, _DB_PATH
    # Close existing connection
    if _db_conn is not None:
        try:
            _db_conn.close()
        except Exception:
            pass
        _db_conn = None
    # Reconfigure path
    if new_dir is not None:
        _DB_DIR = new_dir
        _DB_PATH = os.path.join(_DB_DIR, "plugin_audit.db")
    else:
        _DB_DIR = os.environ.get(
            "HFUSIONHUB_AUDIT_DB_PATH",
            os.path.join(os.path.expanduser("~"), ".hfusionhub", "audit"),
        )
        _DB_PATH = os.path.join(_DB_DIR, "plugin_audit.db")


def _persist_to_sqlite(entry: AuditEntry) -> None:
    """Write audit entry to SQLite for crash recovery."""
    try:
        db = _get_db()
        with _db_lock:
            db.execute(
                "INSERT OR REPLACE INTO audit_queue (id, entry_json, synced, retry_count, created_at) "
                "VALUES (?, ?, 0, 0, ?)",
                (entry.id, json.dumps(entry.to_dict()), entry.timestamp),
            )
            db.commit()
    except Exception as e:
        logger.error("SQLite 审计持久化失败: %s", e)


def _mark_synced(entry_id: str) -> None:
    try:
        db = _get_db()
        with _db_lock:
            db.execute("UPDATE audit_queue SET synced = 1 WHERE id = ?", (entry_id,))
            db.commit()
    except Exception as e:
        logger.error("SQLite 标记同步失败: %s", e)


def _mark_dead_letter(entry_id: str) -> None:
    """Mark an entry as dead-letter (exceeded max retries, never auto-cleaned)."""
    try:
        db = _get_db()
        with _db_lock:
            db.execute(
                "UPDATE audit_queue SET dead_letter = 1, synced = 0 WHERE id = ?",
                (entry_id,),
            )
            db.commit()
    except Exception as e:
        logger.error("SQLite 标记 dead-letter 失败: %s", e)


def _get_unsynced_entries(limit: int = 100) -> List[AuditEntry]:
    try:
        db = _get_db()
        with _db_lock:
            cursor = db.execute(
                "SELECT entry_json, retry_count FROM audit_queue "
                "WHERE synced = 0 AND dead_letter = 0 "
                "ORDER BY created_at ASC LIMIT ?",
                (limit,),
            )
            rows = cursor.fetchall()
        entries = []
        for (raw, db_retry_count) in rows:
            data = json.loads(raw)
            entry = AuditEntry(**{k: v for k, v in data.items() if k in AuditEntry.__dataclass_fields__})
            # Use the actual retry count from SQLite, not the stale JSON value
            entry.retry_count = db_retry_count
            entries.append(entry)
        return entries
    except Exception as e:
        logger.error("SQLite 读取未同步条目失败: %s", e)
        return []


def _increment_retry(entry_id: str) -> None:
    try:
        db = _get_db()
        with _db_lock:
            db.execute(
                "UPDATE audit_queue SET retry_count = retry_count + 1, last_attempt_at = ? WHERE id = ?",
                (time.time(), entry_id),
            )
            db.commit()
    except Exception:
        pass


def _cleanup_synced() -> int:
    """Remove synced entries older than 7 days."""
    try:
        cutoff = time.time() - 7 * 86400
        db = _get_db()
        with _db_lock:
            cursor = db.execute(
                "DELETE FROM audit_queue WHERE synced = 1 AND created_at < ?", (cutoff,)
            )
            db.commit()
            return cursor.rowcount
    except Exception:
        return 0


# ── Background flusher ──────────────────────────────────────────────

_flush_thread: Optional[threading.Thread] = None
_flush_stop = threading.Event()


def _flush_worker() -> None:
    """Background thread that flushes audit entries to Java backend."""
    while not _flush_stop.is_set():
        _flush_stop.wait(timeout=_FLUSH_INTERVAL)
        if _flush_stop.is_set():
            break
        try:
            _do_flush()
        except Exception as e:
            logger.error("审计刷新线程异常: %s", e)


def _do_flush() -> int:
    """Flush unsynced entries to Java backend with retry."""
    entries = _get_unsynced_entries(limit=50)
    if not entries:
        return 0

    flushed = 0
    for entry in entries:
        success = _post_to_java_backend(entry)
        if success:
            _mark_synced(entry.id)
            flushed += 1
        else:
            _increment_retry(entry.id)
            if entry.retry_count >= _MAX_RETRIES:
                logger.warning(
                    "审计条目超过最大重试次数，标记为 dead-letter（保留用于审计，不再自动重试）: %s",
                    entry.id,
                )
                _mark_dead_letter(entry.id)

    if flushed:
        logger.info("审计日志已同步到 Java 后端: %d 条", flushed)

    _cleanup_synced()
    return flushed


def _post_to_java_backend(entry: AuditEntry) -> bool:
    """POST a single audit entry to the Java backend.

    Uses httpx for the actual HTTP call.  The entry is wrapped in a list
    because the Java endpoint expects ``List<Map<...>>``.
    Returns True on success.
    """
    try:
        import httpx
        java_url = os.environ.get("JAVA_BASE_URL", "http://localhost:8080")
        internal_token = os.environ.get("HFUSIONHUB_INTERNAL_TOKEN", "")

        if not internal_token:
            logger.warning("HFUSIONHUB_INTERNAL_TOKEN 未设置，跳过审计同步")
            return False

        wire_data = entry.to_wire()
        resp = httpx.post(
            f"{java_url}{_JAVA_AUDIT_ENDPOINT}",
            json=[wire_data],  # wrap in list — Java expects List<Map>
            headers={"X-Internal-Token": internal_token},
            timeout=10.0,
        )
        if resp.status_code == 200:
            return True
        else:
            logger.warning("Java 审计后端返回 %d: %s", resp.status_code, resp.text[:200])
            return False
    except ImportError:
        logger.warning("httpx 不可用，审计无法同步到 Java 后端")
        return False
    except Exception as e:
        logger.warning("审计同步到 Java 后端失败: %s", e)
        return False


def _ensure_flush_thread() -> None:
    global _flush_thread
    if _flush_thread is None or not _flush_thread.is_alive():
        _flush_stop.clear()
        _flush_thread = threading.Thread(target=_flush_worker, daemon=True, name="audit-flusher")
        _flush_thread.start()


# ── Public API ──────────────────────────────────────────────────────

def record_audit(
    plugin_id: str,
    plugin_name: str,
    action: str,
    operator_id: Optional[int] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    reason: Optional[str] = None,
    plugin_version: Optional[str] = None,
    manifest_hash: Optional[str] = None,
    archive_hash: Optional[str] = None,
    trace_id: Optional[str] = None,
    resource_usage: Optional[Dict[str, Any]] = None,
) -> AuditEntry:
    """Record an audit event with full traceability.

    Writes to: in-memory buffer + SQLite (crash recovery) + Java backend (async).
    """
    if action not in VALID_ACTIONS:
        raise ValueError(f"无效的审计操作: {action}，允许值: {VALID_ACTIONS}")

    entry = AuditEntry(
        plugin_id=plugin_id,
        plugin_name=plugin_name,
        plugin_version=plugin_version or "",
        action=action,
        operator_id=operator_id,
        old_value=old_value,
        new_value=new_value,
        reason=reason,
        manifest_hash=manifest_hash,
        archive_hash=archive_hash,
        trace_id=trace_id or str(uuid.uuid4())[:8],
        resource_usage=resource_usage,
    )

    # Persist to SQLite immediately (crash recovery)
    _persist_to_sqlite(entry)

    # Ensure background flusher is running
    _ensure_flush_thread()

    logger.info(
        "插件审计: %s %s %s@%s by user=%s trace=%s",
        plugin_name, action, plugin_id,
        plugin_version or "?", operator_id, entry.trace_id,
    )

    return entry


def get_audit_log(plugin_id: Optional[str] = None, limit: int = 50) -> List[AuditEntry]:
    """Get recent audit entries from SQLite (includes unsynced)."""
    try:
        db = _get_db()
        with _db_lock:
            if plugin_id:
                cursor = db.execute(
                    "SELECT entry_json FROM audit_queue WHERE json_extract(entry_json, '$.plugin_id') = ? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (plugin_id, limit),
                )
            else:
                cursor = db.execute(
                    "SELECT entry_json FROM audit_queue ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
            rows = cursor.fetchall()
        entries = []
        for (raw,) in rows:
            data = json.loads(raw)
            entry = AuditEntry(**{k: v for k, v in data.items() if k in AuditEntry.__dataclass_fields__})
            entries.append(entry)
        return entries
    except Exception as e:
        logger.error("读取审计日志失败: %s", e)
        return []


def flush_to_backend() -> int:
    """Manually trigger a flush to Java backend.  Returns count flushed."""
    return _do_flush()


def clear_buffer() -> int:
    """Clear all audit data (SQLite + in-memory).  Returns count cleared."""
    try:
        db = _get_db()
        with _db_lock:
            cursor = db.execute("DELETE FROM audit_queue")
            db.commit()
            return cursor.rowcount
    except Exception:
        return 0


def get_sync_status() -> Dict[str, Any]:
    """Get audit sync status for monitoring."""
    try:
        db = _get_db()
        with _db_lock:
            total = db.execute("SELECT COUNT(*) FROM audit_queue").fetchone()[0]
            unsynced = db.execute("SELECT COUNT(*) FROM audit_queue WHERE synced = 0 AND dead_letter = 0").fetchone()[0]
            dead_letter = db.execute("SELECT COUNT(*) FROM audit_queue WHERE dead_letter = 1").fetchone()[0]
        return {"total": total, "unsynced": unsynced, "dead_letter": dead_letter}
    except Exception:
        return {"total": 0, "unsynced": 0, "dead_letter": 0}


# ── Convenience functions ──────────────────────────────────────────

def record_install(plugin_id: str, plugin_name: str, manifest_hash: str,
                   operator_id: Optional[int] = None,
                   plugin_version: Optional[str] = None,
                   archive_hash: Optional[str] = None) -> AuditEntry:
    return record_audit(
        plugin_id=plugin_id, plugin_name=plugin_name,
        action=ACTION_INSTALL, operator_id=operator_id,
        plugin_version=plugin_version, manifest_hash=manifest_hash,
        archive_hash=archive_hash,
        new_value=json.dumps({"manifest_hash": manifest_hash}),
    )


def record_enable(plugin_id: str, plugin_name: str,
                  operator_id: Optional[int] = None,
                  plugin_version: Optional[str] = None) -> AuditEntry:
    return record_audit(
        plugin_id=plugin_id, plugin_name=plugin_name,
        action=ACTION_ENABLE, operator_id=operator_id,
        plugin_version=plugin_version,
        old_value=json.dumps({"enabled": False}),
        new_value=json.dumps({"enabled": True}),
    )


def record_disable(plugin_id: str, plugin_name: str, reason: Optional[str] = None,
                   operator_id: Optional[int] = None,
                   plugin_version: Optional[str] = None) -> AuditEntry:
    return record_audit(
        plugin_id=plugin_id, plugin_name=plugin_name,
        action=ACTION_DISABLE, operator_id=operator_id,
        plugin_version=plugin_version,
        old_value=json.dumps({"enabled": True}),
        new_value=json.dumps({"enabled": False}),
        reason=reason,
    )


def record_uninstall(plugin_id: str, plugin_name: str, reason: Optional[str] = None,
                     operator_id: Optional[int] = None,
                     plugin_version: Optional[str] = None) -> AuditEntry:
    return record_audit(
        plugin_id=plugin_id, plugin_name=plugin_name,
        action=ACTION_UNINSTALL, operator_id=operator_id,
        plugin_version=plugin_version,
        new_value=json.dumps({"status": "deleted"}),
        reason=reason,
    )


def record_tool_execution(plugin_id: str, plugin_name: str, tool_name: str,
                          success: bool, duration_ms: float,
                          plugin_version: Optional[str] = None,
                          trace_id: Optional[str] = None,
                          resource_usage: Optional[Dict[str, Any]] = None,
                          error: Optional[str] = None) -> AuditEntry:
    action = ACTION_TOOL_EXECUTED if success else ACTION_TOOL_FAILED
    return record_audit(
        plugin_id=plugin_id, plugin_name=plugin_name,
        action=action, plugin_version=plugin_version,
        trace_id=trace_id, resource_usage=resource_usage,
        new_value=json.dumps({"tool": tool_name, "duration_ms": duration_ms}),
        reason=error,
    )
