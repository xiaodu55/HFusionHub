"""Plugin audit trail — persistent audit with Java backend sync.

Architecture:
  1. In-memory buffer (fast writes)
  2. Local SQLite file (crash recovery)
  3. Background thread flushes to Java backend with exponential backoff retry
  4. ``flush_on_shutdown`` drains it once more on SIGTERM — the queue lives in a
     per-pod directory, so nothing else will ever pick the leftovers up

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
from dataclasses import dataclass, field
from typing import Any

from app.utils.config import config

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

# Java backend endpoint（Java 的 server.servlet.context-path 是 /api，路径必须自带）
_JAVA_AUDIT_ENDPOINT = "/api/internal/plugin/audit-logs"

# Retry config
_MAX_RETRIES = 5
_RETRY_BASE_DELAY = 2.0  # seconds
_FLUSH_INTERVAL = 30.0  # seconds
# 退出排空预算：K8s 默认优雅期 30s，还要留给在途请求，故远小于它。
_SHUTDOWN_FLUSH_BUDGET = 10.0


@dataclass
class AuditEntry:
    """A single audit log entry with full traceability."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    plugin_id: str = ""
    plugin_name: str = ""
    plugin_version: str = ""
    action: str = ""
    operator_id: int | None = None
    old_value: str | None = None
    new_value: str | None = None
    reason: str | None = None
    manifest_hash: str | None = None
    archive_hash: str | None = None
    trace_id: str | None = None
    resource_usage: dict[str, Any] | None = None
    timestamp: float = field(default_factory=time.time)
    synced: bool = False
    retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
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

    def to_wire(self) -> dict[str, Any]:
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
_db_conn: sqlite3.Connection | None = None


def _get_db() -> sqlite3.Connection:
    """懒建并复用连接。**调用方必须已经持有 `_db_lock`**。

    连接是 `check_same_thread=False` 的共享对象，`_reset_db` 会在锁内关掉它；
    在锁外取引用等于握着一个随时可能被别人关闭的原生句柄，sqlite3 对它的
    `execute` 不是抛 Python 异常，而是解释器级 access violation。
    """
    global _db_conn
    if _db_conn is None:
        _db_conn = _init_db()
    return _db_conn


def _reset_db(new_dir: str | None = None) -> None:
    """Reset the SQLite connection and optionally redirect to a new directory.

    Used by tests to isolate the audit database in a temp directory.
    Pass a directory path to redirect; pass None to restore the default.

    关连接与换绑整段持 `_db_lock`：不持锁时它可以在任何一条在途语句中间把连接关掉。
    """
    global _db_conn, _DB_DIR, _DB_PATH
    with _db_lock:
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
        with _db_lock:
            db = _get_db()
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
        with _db_lock:
            db = _get_db()
            db.execute("UPDATE audit_queue SET synced = 1 WHERE id = ?", (entry_id,))
            db.commit()
    except Exception as e:
        logger.error("SQLite 标记同步失败: %s", e)


def _get_unsynced_entries(limit: int = 100) -> list[AuditEntry]:
    try:
        with _db_lock:
            db = _get_db()
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


def _register_failed_attempt(entry_id: str) -> bool:
    """记一次失败的出站，返回这一行是否被**本次调用**标成 dead-letter。

    读当前 retry_count、自增、落 dead-letter 三步共用同一次持锁。拆成"先自增、再按
    `_do_flush` 那份快照判超限、最后落标记"就留了一道窗口：快照取回到回写之间，运维的
    `retry_dead_letters()` 可以把行回灌（`dead_letter=0, retry_count=0`），而那条拿着过期
    retry_count 的判定会把它翻回 dead-letter——回灌等于没生效（第一百零七批的对象）。
    比的是"自增之前"读到的计数，与旧判定同形，只是把它从快照抬到了当前行。
    """
    try:
        with _db_lock:
            db = _get_db()
            row = db.execute("SELECT retry_count FROM audit_queue WHERE id = ?", (entry_id,)).fetchone()
            db.execute(
                "UPDATE audit_queue SET retry_count = retry_count + 1, last_attempt_at = ? WHERE id = ?",
                (time.time(), entry_id),
            )
            exhausted = row is not None and row[0] >= _MAX_RETRIES
            if exhausted:
                db.execute(
                    "UPDATE audit_queue SET dead_letter = 1, synced = 0 WHERE id = ?",
                    (entry_id,),
                )
            db.commit()
        return exhausted
    except Exception as e:
        logger.error("SQLite 记录失败重试次数出错: %s", e)
        return False


def _cleanup_synced() -> int:
    """Remove synced entries older than 7 days."""
    try:
        cutoff = time.time() - 7 * 86400
        with _db_lock:
            db = _get_db()
            cursor = db.execute(
                "DELETE FROM audit_queue WHERE synced = 1 AND created_at < ?", (cutoff,)
            )
            db.commit()
            return cursor.rowcount
    except Exception:
        return 0


# ── Background flusher ──────────────────────────────────────────────

_flush_thread: threading.Thread | None = None
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
    """Flush unsynced entries to Java backend with retry.

    R15-18：单次批量 POST（Java 端点本身接受 List），替代旧实现的逐条
    POST——50 条积压时从 50 次 HTTP 往返降为 1 次。整批失败时逐条重试
    计数（保留既有 dead-letter 语义）。
    """
    entries = _get_unsynced_entries(limit=50)
    if not entries:
        return 0

    if _post_to_java_backend_batch(entries):
        for entry in entries:
            _mark_synced(entry.id)
        logger.info("审计日志已同步到 Java 后端: %d 条", len(entries))
        _cleanup_synced()
        return len(entries)

    # 批量失败：回退逐条（旧路径），便于定位坏条目并保留 dead-letter 语义
    flushed = 0
    for entry in entries:
        success = _post_to_java_backend(entry)
        if success:
            _mark_synced(entry.id)
            flushed += 1
        else:
            # 超限与否取回写的返回值，不取 entries 那份出站前读的快照
            if _register_failed_attempt(entry.id):
                logger.warning(
                    "审计条目超过最大重试次数，标记为 dead-letter（保留用于审计，不再自动重试）: %s",
                    entry.id,
                )

    if flushed:
        logger.info("审计日志已同步到 Java 后端: %d 条", flushed)

    _cleanup_synced()
    return flushed


def _is_sync_accepted(resp) -> bool:
    """Judge whether Java actually stored the batch.

    ``POST /internal/plugin/audit-logs`` answers a rejected token with
    ``R.fail(403)`` — HTTP 200 plus an envelope code — so the status line alone
    cannot prove the entries landed. Anything other than a 200 envelope is
    treated as unsynced so retry and dead-lettering still apply.
    """
    if resp.status_code != 200:
        logger.warning("Java 审计后端返回 %d: %s", resp.status_code, resp.text[:200])
        return False
    try:
        envelope = resp.json()
    except Exception as e:
        logger.warning("Java 审计响应无法解析，按未同步处理: %s", e)
        return False
    code = envelope.get("code")
    if code != 200:
        logger.warning(
            "Java 审计后端拒绝同步: code=%s message=%s", code, envelope.get("message")
        )
        return False
    return True


def _post_to_java_backend_batch(entries: list) -> bool:
    """POST all entries in one request. Returns True iff the whole batch synced."""
    try:
        import httpx
        java_url = config.JAVA_BACKEND_URL
        internal_token = config.INTERNAL_API_TOKEN

        if not internal_token:
            logger.warning("INTERNAL_API_TOKEN 未设置，跳过审计同步")
            return False

        resp = httpx.post(
            f"{java_url}{_JAVA_AUDIT_ENDPOINT}",
            json=[entry.to_wire() for entry in entries],
            headers={"X-Internal-Token": internal_token},
            timeout=30.0,
        )
        return _is_sync_accepted(resp)
    except Exception as e:
        logger.warning("审计批量同步到 Java 后端失败: %s", e)
        return False


def _post_to_java_backend(entry: AuditEntry) -> bool:
    """POST a single audit entry to the Java backend.

    Uses httpx for the actual HTTP call.  The entry is wrapped in a list
    because the Java endpoint expects ``List<Map<...>>``.
    Returns True on success.
    """
    try:
        import httpx
        java_url = config.JAVA_BACKEND_URL
        internal_token = config.INTERNAL_API_TOKEN

        if not internal_token:
            logger.warning("INTERNAL_API_TOKEN 未设置，跳过审计同步")
            return False

        wire_data = entry.to_wire()
        resp = httpx.post(
            f"{java_url}{_JAVA_AUDIT_ENDPOINT}",
            json=[wire_data],  # wrap in list — Java expects List<Map>
            headers={"X-Internal-Token": internal_token},
            timeout=10.0,
        )
        return _is_sync_accepted(resp)
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
    operator_id: int | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
    reason: str | None = None,
    plugin_version: str | None = None,
    manifest_hash: str | None = None,
    archive_hash: str | None = None,
    trace_id: str | None = None,
    resource_usage: dict[str, Any] | None = None,
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


def get_audit_log(plugin_id: str | None = None, limit: int = 50) -> list[AuditEntry]:
    """Get recent audit entries from SQLite (includes unsynced)."""
    try:
        with _db_lock:
            db = _get_db()
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
        with _db_lock:
            db = _get_db()
            cursor = db.execute("DELETE FROM audit_queue")
            db.commit()
            return cursor.rowcount
    except Exception:
        return 0


def _queue_counts() -> dict[str, int]:
    """Read the queue counters. Raises if the database is unreadable."""
    with _db_lock:
        db = _get_db()
        total = db.execute("SELECT COUNT(*) FROM audit_queue").fetchone()[0]
        unsynced = db.execute(
            "SELECT COUNT(*) FROM audit_queue WHERE synced = 0 AND dead_letter = 0"
        ).fetchone()[0]
        dead_letter = db.execute(
            "SELECT COUNT(*) FROM audit_queue WHERE dead_letter = 1"
        ).fetchone()[0]
    return {"total": total, "unsynced": unsynced, "dead_letter": dead_letter}


def get_sync_status() -> dict[str, Any]:
    """Get audit sync status for monitoring."""
    try:
        return _queue_counts()
    except Exception:
        return {"total": 0, "unsynced": 0, "dead_letter": 0}


def retry_dead_letters() -> int:
    """把 dead-letter 行重新放回重试队列，返回回灌条数（运维显式触发）。

    修好出站地址并不会让历史 dead-letter 行自我恢复：`_get_unsynced_entries`
    只取 `dead_letter = 0`。`retry_count` 一并清零，每行重新拿到完整的
    `_MAX_RETRIES` 预算；已 synced 的行不受影响。
    """
    try:
        with _db_lock:
            db = _get_db()
            cursor = db.execute(
                "UPDATE audit_queue SET dead_letter = 0, retry_count = 0 "
                "WHERE dead_letter = 1"
            )
            db.commit()
            retried = cursor.rowcount
        if retried:
            logger.warning("dead-letter 审计行已重新入队: %d 条", retried)
        return retried
    except Exception as e:
        logger.error("dead-letter 回灌失败: %s", e)
        return 0


def flush_on_shutdown(budget_seconds: float = _SHUTDOWN_FLUSH_BUDGET) -> dict[str, Any]:
    """进程退出前停掉后台线程并把队列最后排空一次，返回处置结果。

    调用方（lifespan shutdown）与 K8s 优雅终止共用一个事实：预算一到就是
    SIGKILL，所以拖延换不来同步成功。`remaining=None` 表示队列读不到、
    无法确认是否排空——这与把它写成 0 是两回事。
    """
    result: dict[str, Any] = {
        "flushed": 0,
        "remaining": 0,
        "timed_out": False,
        "error": None,
        "db_dir": _DB_DIR,
    }
    _flush_stop.set()
    worker = _flush_thread
    if worker is not None and worker.is_alive():
        worker.join(timeout=budget_seconds / 3)  # 等在途的那次出站跑完再补一次

    outcome: dict[str, Any] = {}

    def _run() -> None:
        try:
            outcome["flushed"] = _do_flush()
        except Exception as e:
            outcome["error"] = str(e)

    final = threading.Thread(target=_run, daemon=True, name="audit-shutdown-flush")
    final.start()
    final.join(timeout=budget_seconds)
    result["timed_out"] = final.is_alive()
    result["flushed"] = outcome.get("flushed", 0)
    result["error"] = outcome.get("error")

    if result["error"] is None:
        try:
            counts = _queue_counts()
            result["remaining"] = counts["unsynced"] + counts["dead_letter"]
        except Exception as e:
            result["remaining"] = None
            result["error"] = str(e)

    if result["remaining"]:
        logger.warning(
            "退出时审计队列未排空: remaining=%s timed_out=%s 落点=%s",
            result["remaining"], result["timed_out"], result["db_dir"],
        )
    elif result["remaining"] is None or result["error"]:
        logger.error(
            "退出时无法确认审计队列状态: %s 落点=%s", result["error"], result["db_dir"]
        )
    else:
        logger.info("审计队列已在退出前排空: flushed=%d", result["flushed"])
    return result


# ── Convenience functions ──────────────────────────────────────────

def record_install(plugin_id: str, plugin_name: str, manifest_hash: str,
                   operator_id: int | None = None,
                   plugin_version: str | None = None,
                   archive_hash: str | None = None) -> AuditEntry:
    return record_audit(
        plugin_id=plugin_id, plugin_name=plugin_name,
        action=ACTION_INSTALL, operator_id=operator_id,
        plugin_version=plugin_version, manifest_hash=manifest_hash,
        archive_hash=archive_hash,
        new_value=json.dumps({"manifest_hash": manifest_hash}),
    )


def record_enable(plugin_id: str, plugin_name: str,
                  operator_id: int | None = None,
                  plugin_version: str | None = None) -> AuditEntry:
    return record_audit(
        plugin_id=plugin_id, plugin_name=plugin_name,
        action=ACTION_ENABLE, operator_id=operator_id,
        plugin_version=plugin_version,
        old_value=json.dumps({"enabled": False}),
        new_value=json.dumps({"enabled": True}),
    )


def record_disable(plugin_id: str, plugin_name: str, reason: str | None = None,
                   operator_id: int | None = None,
                   plugin_version: str | None = None) -> AuditEntry:
    return record_audit(
        plugin_id=plugin_id, plugin_name=plugin_name,
        action=ACTION_DISABLE, operator_id=operator_id,
        plugin_version=plugin_version,
        old_value=json.dumps({"enabled": True}),
        new_value=json.dumps({"enabled": False}),
        reason=reason,
    )


def record_uninstall(plugin_id: str, plugin_name: str, reason: str | None = None,
                     operator_id: int | None = None,
                     plugin_version: str | None = None) -> AuditEntry:
    return record_audit(
        plugin_id=plugin_id, plugin_name=plugin_name,
        action=ACTION_UNINSTALL, operator_id=operator_id,
        plugin_version=plugin_version,
        new_value=json.dumps({"status": "deleted"}),
        reason=reason,
    )


def record_tool_execution(plugin_id: str, plugin_name: str, tool_name: str,
                          success: bool, duration_ms: float,
                          plugin_version: str | None = None,
                          trace_id: str | None = None,
                          resource_usage: dict[str, Any] | None = None,
                          error: str | None = None) -> AuditEntry:
    action = ACTION_TOOL_EXECUTED if success else ACTION_TOOL_FAILED
    return record_audit(
        plugin_id=plugin_id, plugin_name=plugin_name,
        action=action, plugin_version=plugin_version,
        trace_id=trace_id, resource_usage=resource_usage,
        new_value=json.dumps({"tool": tool_name, "duration_ms": duration_ms}),
        reason=error,
    )
