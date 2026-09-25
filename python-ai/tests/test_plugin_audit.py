"""Tests for plugin audit trail."""

from unittest.mock import patch

import pytest

from app.core.plugin.audit import (
    VALID_ACTIONS,
    AuditEntry,
    clear_buffer,
    flush_to_backend,
    get_audit_log,
    get_sync_status,
    record_audit,
    record_disable,
    record_enable,
    record_install,
    record_uninstall,
)


@pytest.fixture(autouse=True)
def clean_audit_buffer():
    """Ensure clean audit buffer for each test."""
    clear_buffer()
    yield
    clear_buffer()


# ── Basic recording ──────────────────────────────────────────────────

class TestAuditRecording:
    def test_record_audit_returns_entry(self):
        entry = record_audit(
            plugin_id="pid-1",
            plugin_name="test_plugin",
            action="install",
            operator_id=1,
        )
        assert isinstance(entry, AuditEntry)
        assert entry.plugin_id == "pid-1"
        assert entry.action == "install"
        assert entry.operator_id == 1

    def test_record_audit_with_all_fields(self):
        entry = record_audit(
            plugin_id="pid-1",
            plugin_name="test_plugin",
            action="disable",
            operator_id=2,
            old_value='{"enabled": true}',
            new_value='{"enabled": false}',
            reason="security concern",
        )
        assert entry.old_value == '{"enabled": true}'
        assert entry.new_value == '{"enabled": false}'
        assert entry.reason == "security concern"

    def test_record_audit_invalid_action_raises(self):
        with pytest.raises(ValueError, match="无效的审计操作"):
            record_audit(
                plugin_id="pid-1",
                plugin_name="test_plugin",
                action="invalid_action",
            )

    def test_record_audit_adds_to_log(self):
        record_audit(plugin_id="pid-1", plugin_name="p", action="install")
        record_audit(plugin_id="pid-1", plugin_name="p", action="enable")
        entries = get_audit_log(plugin_id="pid-1")
        assert len(entries) == 2

    def test_to_dict(self):
        entry = record_audit(
            plugin_id="pid-1", plugin_name="p", action="install", operator_id=1
        )
        d = entry.to_dict()
        assert d["plugin_id"] == "pid-1"
        assert d["action"] == "install"
        assert d["operator_id"] == 1
        assert "timestamp" in d


# ── Convenience functions ────────────────────────────────────────────

class TestAuditConvenience:
    def test_record_install(self):
        entry = record_install("pid-1", "test", "abc123", operator_id=1)
        assert entry.action == "install"
        assert "abc123" in entry.new_value

    def test_record_enable(self):
        entry = record_enable("pid-1", "test", operator_id=1)
        assert entry.action == "enable"
        assert '"enabled": true' in entry.new_value

    def test_record_disable(self):
        entry = record_disable("pid-1", "test", reason="security", operator_id=1)
        assert entry.action == "disable"
        assert entry.reason == "security"

    def test_record_uninstall(self):
        entry = record_uninstall("pid-1", "test", reason="obsolete", operator_id=1)
        assert entry.action == "uninstall"
        assert "deleted" in entry.new_value


# ── Log retrieval ────────────────────────────────────────────────────

class TestAuditRetrieval:
    def test_get_audit_log_empty(self):
        entries = get_audit_log()
        assert entries == []

    def test_get_audit_log_filters_by_plugin_id(self):
        record_audit(plugin_id="pid-1", plugin_name="a", action="install")
        record_audit(plugin_id="pid-2", plugin_name="b", action="install")
        entries = get_audit_log(plugin_id="pid-1")
        assert len(entries) == 1
        assert entries[0].plugin_id == "pid-1"

    def test_get_audit_log_respects_limit(self):
        for i in range(10):
            record_audit(plugin_id="pid-1", plugin_name="p", action="install")
        entries = get_audit_log(limit=5)
        assert len(entries) == 5

    def test_clear_buffer(self):
        record_audit(plugin_id="pid-1", plugin_name="p", action="install")
        count = clear_buffer()
        assert count == 1
        assert get_audit_log() == []


# ── Flush ────────────────────────────────────────────────────────────

class TestAuditFlush:
    @patch("app.core.plugin.audit._post_to_java_backend", return_value=True)
    def test_flush_returns_count(self, mock_post):
        record_audit(plugin_id="pid-1", plugin_name="p", action="install")
        record_audit(plugin_id="pid-1", plugin_name="p", action="enable")
        count = flush_to_backend()
        assert count == 2

    @patch("app.core.plugin.audit._post_to_java_backend", return_value=True)
    def test_flush_clears_buffer(self, mock_post):
        record_audit(plugin_id="pid-1", plugin_name="p", action="install")
        flush_to_backend()
        # After flush, unsynced count should be 0
        status = get_sync_status()
        assert status["unsynced"] == 0

    def test_flush_empty_returns_zero(self):
        count = flush_to_backend()
        assert count == 0


# ── Backend sync token ───────────────────────────────────────────────

class TestBackendSyncToken:
    """出站同步只认服务权威 token（第六十四批修复）。

    历史缺陷：两处出站读取从未部署过的 HFUSIONHUB_INTERNAL_TOKEN，导致插件
    审计静默不同步；现在与入站守卫共用 config.INTERNAL_API_TOKEN。
    """

    @patch("httpx.post")
    @patch("app.core.plugin.audit.config")
    def test_batch_sync_uses_internal_api_token(self, mock_config, mock_post):
        import os
        from unittest.mock import MagicMock

        from app.core.plugin.audit import _post_to_java_backend_batch

        mock_config.INTERNAL_API_TOKEN = "shared-internal-token"
        mock_config.JAVA_BACKEND_URL = "http://java:8080"
        mock_post.return_value = _accepted_response(MagicMock())
        entry = record_audit(plugin_id="pid-1", plugin_name="p", action="install")

        with patch.dict(os.environ, {"HFUSIONHUB_INTERNAL_TOKEN": "legacy-ignored"}):
            assert _post_to_java_backend_batch([entry]) is True

        url = mock_post.call_args.args[0]
        assert url == "http://java:8080/api/internal/plugin/audit-logs"
        assert mock_post.call_args.kwargs["headers"] == {
            "X-Internal-Token": "shared-internal-token"}
        assert isinstance(mock_post.call_args.kwargs["json"], list)

    @patch("httpx.post")
    @patch("app.core.plugin.audit.config")
    def test_single_sync_uses_internal_api_token(self, mock_config, mock_post):
        from unittest.mock import MagicMock

        from app.core.plugin.audit import _post_to_java_backend

        mock_config.INTERNAL_API_TOKEN = "shared-internal-token"
        mock_config.JAVA_BACKEND_URL = "http://java:8080"
        mock_post.return_value = _accepted_response(MagicMock())
        entry = record_audit(plugin_id="pid-1", plugin_name="p", action="enable")

        assert _post_to_java_backend(entry) is True
        assert mock_post.call_args.args[0] == "http://java:8080/api/internal/plugin/audit-logs"
        assert mock_post.call_args.kwargs["headers"] == {
            "X-Internal-Token": "shared-internal-token"}

    @patch("httpx.post")
    @patch("app.core.plugin.audit.config")
    def test_sync_skips_http_when_token_unconfigured(self, mock_config, mock_post):
        from app.core.plugin.audit import _post_to_java_backend_batch

        mock_config.INTERNAL_API_TOKEN = ""
        entry = record_audit(plugin_id="pid-1", plugin_name="p", action="install")
        assert _post_to_java_backend_batch([entry]) is False
        mock_post.assert_not_called()


# ── Backend sync address ─────────────────────────────────────────────

class TestBackendSyncAddress:
    """出站地址只认部署侧真正配置的键，且必须带 Java 的 `/api` context path。

    历史缺陷：两条链路读 `os.environ["JAVA_BASE_URL"]`（默认
    `http://localhost:8080`），而 `JAVA_BASE_URL` 全仓只在
    `.github/workflows/e2e.yml` 里赋值，docker/helm/`.env` 配的都是
    `JAVA_BACKEND_URL`；端点常量又以 `/internal/...` 开头，而 Java 的
    `server.servlet.context-path` 是 `/api`。主机名与路径双错 → 容器里必然
    404、审计重试 5 次后 dead-letter。
    """

    @staticmethod
    def _url_for(single: bool):
        import os
        from unittest.mock import MagicMock

        from app.core.plugin.audit import _post_to_java_backend, _post_to_java_backend_batch

        with patch("httpx.post") as mock_post, patch("app.core.plugin.audit.config") as mock_config:
            mock_config.INTERNAL_API_TOKEN = "shared-internal-token"
            mock_config.JAVA_BACKEND_URL = "http://java-backend:8080"
            mock_post.return_value = _accepted_response(MagicMock())
            entry = record_audit(plugin_id="pid-1", plugin_name="p", action="install")
            # 诱饵：旧代码读的键。修复后不得出现在 URL 里
            with patch.dict(os.environ, {"JAVA_BASE_URL": "http://decoy:9999"}):
                (
                    _post_to_java_backend(entry)
                    if single else _post_to_java_backend_batch([entry])
                )
            return mock_post.call_args.args[0]

    def test_batch_sync_ignores_java_base_url_and_uses_configured_backend(self):
        url = self._url_for(single=False)
        assert url == "http://java-backend:8080/api/internal/plugin/audit-logs"
        assert "decoy" not in url

    def test_single_sync_ignores_java_base_url_and_uses_configured_backend(self):
        url = self._url_for(single=True)
        assert url == "http://java-backend:8080/api/internal/plugin/audit-logs"
        assert "decoy" not in url

    def test_no_java_base_url_reference_remains_in_the_audit_module(self):
        """`JAVA_BASE_URL` 这个键在审计出站里应彻底消失（防回潮）。"""
        import inspect

        from app.core.plugin import audit

        assert "JAVA_BASE_URL" not in inspect.getsource(audit)


# ── Backend sync envelope judgement ──────────────────────────────────

def _rejected_response(resp):
    """Java 内部面的拒绝形状：HTTP 200 + 信封 code 403（raise_for_status 看不见）。"""
    resp.status_code = 200
    resp.text = '{"code":403,"message":"Forbidden: invalid or missing X-Internal-Token"}'
    resp.json.return_value = {"code": 403, "message": "Forbidden: invalid or missing X-Internal-Token",
                              "data": None}
    return resp


def _accepted_response(resp, inserted=1, skipped=0):
    resp.status_code = 200
    resp.text = ""
    resp.json.return_value = {
        "code": 200, "message": "success",
        "data": {"inserted": inserted, "skipped": skipped, "total": inserted + skipped},
    }
    return resp


class TestBackendSyncEnvelopeJudgement:
    """同步判定必须读信封码。

    旧实现只判 `status_code == 200`，而 `POST /internal/plugin/audit-logs`
    （InternalPluginController.receiveAuditLogs）令牌失败时回的是
    `R.fail(403)` = HTTP 200 + 信封码：被拒的批次会被标记 synced 并从本地队列
    永久摘除，不重试、不报警。
    """

    @patch("httpx.post")
    @patch("app.core.plugin.audit.config")
    def test_batch_sync_rejects_envelope_403_despite_http_200(self, mock_config, mock_post):
        from unittest.mock import MagicMock

        from app.core.plugin.audit import _post_to_java_backend_batch

        mock_config.INTERNAL_API_TOKEN = "shared-internal-token"
        mock_post.return_value = _rejected_response(MagicMock())
        entry = record_audit(plugin_id="pid-1", plugin_name="p", action="install")

        assert _post_to_java_backend_batch([entry]) is False

    @patch("httpx.post")
    @patch("app.core.plugin.audit.config")
    def test_single_sync_rejects_envelope_403_despite_http_200(self, mock_config, mock_post):
        from unittest.mock import MagicMock

        from app.core.plugin.audit import _post_to_java_backend

        mock_config.INTERNAL_API_TOKEN = "shared-internal-token"
        mock_post.return_value = _rejected_response(MagicMock())
        entry = record_audit(plugin_id="pid-1", plugin_name="p", action="enable")

        assert _post_to_java_backend(entry) is False

    @patch("httpx.post")
    @patch("app.core.plugin.audit.config")
    def test_rejected_batch_leaves_entries_unsynced(self, mock_config, mock_post):
        from unittest.mock import MagicMock

        mock_config.INTERNAL_API_TOKEN = "shared-internal-token"
        mock_post.return_value = _rejected_response(MagicMock())
        record_audit(plugin_id="pid-1", plugin_name="p", action="install")

        assert flush_to_backend() == 0
        assert get_sync_status()["unsynced"] == 1

    @patch("httpx.post")
    @patch("app.core.plugin.audit.config")
    def test_http_error_status_is_still_not_synced(self, mock_config, mock_post):
        from unittest.mock import MagicMock

        from app.core.plugin.audit import _post_to_java_backend_batch

        mock_config.INTERNAL_API_TOKEN = "shared-internal-token"
        resp = MagicMock()
        resp.status_code = 503
        resp.text = "gateway down"
        resp.json.side_effect = ValueError("no body")
        mock_post.return_value = resp
        entry = record_audit(plugin_id="pid-1", plugin_name="p", action="install")

        assert _post_to_java_backend_batch([entry]) is False

    @patch("httpx.post")
    @patch("app.core.plugin.audit.config")
    def test_unparseable_success_body_is_not_synced(self, mock_config, mock_post):
        from unittest.mock import MagicMock

        from app.core.plugin.audit import _post_to_java_backend_batch

        mock_config.INTERNAL_API_TOKEN = "shared-internal-token"
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "<html>proxy said ok</html>"
        resp.json.side_effect = ValueError("Expecting value")
        mock_post.return_value = resp
        entry = record_audit(plugin_id="pid-1", plugin_name="p", action="install")

        assert _post_to_java_backend_batch([entry]) is False


# ── Valid actions ────────────────────────────────────────────────────

class TestValidActions:
    def test_all_actions_valid(self):
        assert "install" in VALID_ACTIONS
        assert "enable" in VALID_ACTIONS
        assert "disable" in VALID_ACTIONS
        assert "update" in VALID_ACTIONS
        assert "uninstall" in VALID_ACTIONS
        assert "rollback" in VALID_ACTIONS


# ── Dead-letter queue ────────────────────────────────────────────────

class TestAuditDeadLetter:
    @patch("app.core.plugin.audit._post_to_java_backend", return_value=False)
    @patch("app.core.plugin.audit._MAX_RETRIES", 2)
    def test_dead_letter_after_max_retries(self, mock_post):
        """Entry exceeding max retries should be marked dead_letter, NOT synced."""
        from app.core.plugin import audit as audit_mod
        record_audit(plugin_id="pid-1", plugin_name="p", action="install")

        # Flush multiple times to exhaust retries
        audit_mod._do_flush()
        audit_mod._do_flush()
        audit_mod._do_flush()

        status = get_sync_status()
        assert status["unsynced"] == 0  # not retryable
        assert status["dead_letter"] == 1  # but preserved

    @patch("app.core.plugin.audit._post_to_java_backend", return_value=False)
    @patch("app.core.plugin.audit._MAX_RETRIES", 2)
    def test_dead_letter_not_retried(self, mock_post):
        """Dead-letter entries should not be picked up by subsequent flushes."""
        from app.core.plugin import audit as audit_mod
        record_audit(plugin_id="pid-1", plugin_name="p", action="install")

        audit_mod._do_flush()
        audit_mod._do_flush()
        audit_mod._do_flush()

        # Reset mock to track new calls
        mock_post.reset_mock()
        audit_mod._do_flush()

        # Should not attempt to post dead-letter entries
        assert mock_post.call_count == 0

    def test_get_sync_status_includes_dead_letter(self):
        status = get_sync_status()
        assert "dead_letter" in status
        assert "unsynced" in status
        assert "total" in status


# ── dead-letter 回灌 ────────────────────────────────────────────────────


def _drain_to_dead_letter(audit_mod, plugin_id="pid-1"):
    """造一条已耗尽重试的 dead-letter 行（第七十七批修地址之前的常见终态）。"""
    record_audit(plugin_id=plugin_id, plugin_name="p", action="install")
    with (
        patch.object(audit_mod, "_post_to_java_backend_batch", return_value=False),
        patch.object(audit_mod, "_post_to_java_backend", return_value=False),
        patch.object(audit_mod, "_MAX_RETRIES", 2),
    ):
        for _ in range(3):
            audit_mod._do_flush()
    status = get_sync_status()
    assert status["dead_letter"] == 1 and status["unsynced"] == 0
    return status


def _queue_rows(audit_mod):
    with audit_mod._db_lock:
        return audit_mod._get_db().execute(
            "SELECT id, synced, dead_letter, retry_count FROM audit_queue"
        ).fetchall()


class TestRetryDeadLetters:
    def test_retry_returns_count_and_clears_dead_letter(self):
        from app.core.plugin import audit as audit_mod

        _drain_to_dead_letter(audit_mod)
        assert audit_mod.retry_dead_letters() == 1
        status = get_sync_status()
        assert status["dead_letter"] == 0
        assert status["unsynced"] == 1

    def test_retry_count_is_reset_so_the_row_gets_a_full_budget(self):
        from app.core.plugin import audit as audit_mod

        _drain_to_dead_letter(audit_mod)
        audit_mod.retry_dead_letters()
        rows = _queue_rows(audit_mod)
        assert [(r[1], r[2], r[3]) for r in rows] == [(0, 0, 0)]

    def test_requeued_row_is_actually_posted_by_the_next_flush(self):
        """回灌的意义：地址已修（第七十七批）后，这一行必须真的再上一次出站。"""
        from app.core.plugin import audit as audit_mod

        _drain_to_dead_letter(audit_mod)
        audit_mod.retry_dead_letters()
        with patch.object(audit_mod, "_post_to_java_backend_batch", return_value=True) as batch:
            assert audit_mod._do_flush() == 1
        assert batch.call_count == 1
        status = get_sync_status()
        assert status["unsynced"] == 0 and status["dead_letter"] == 0

    def test_second_retry_is_idempotent(self):
        from app.core.plugin import audit as audit_mod

        _drain_to_dead_letter(audit_mod)
        audit_mod.retry_dead_letters()
        assert audit_mod.retry_dead_letters() == 0
        assert get_sync_status()["dead_letter"] == 0

    def test_no_dead_letters_is_a_no_op(self):
        from app.core.plugin import audit as audit_mod

        record_audit(plugin_id="pid-ok", plugin_name="p", action="install")
        assert audit_mod.retry_dead_letters() == 0
        status = get_sync_status()
        assert status["unsynced"] == 1 and status["dead_letter"] == 0

    def test_synced_rows_are_untouched(self):
        from app.core.plugin import audit as audit_mod

        record_audit(plugin_id="pid-sync", plugin_name="p", action="install")
        with patch.object(audit_mod, "_post_to_java_backend_batch", return_value=True):
            audit_mod._do_flush()
        assert get_sync_status()["unsynced"] == 0

        with (
            patch.object(audit_mod, "_post_to_java_backend_batch", return_value=False),
            patch.object(audit_mod, "_post_to_java_backend", return_value=False),
            patch.object(audit_mod, "_MAX_RETRIES", 0),
        ):
            record_audit(plugin_id="pid-dead", plugin_name="p", action="disable")
            audit_mod._do_flush()
        assert get_sync_status()["dead_letter"] == 1

        assert audit_mod.retry_dead_letters() == 1
        requeued = audit_mod._get_unsynced_entries(limit=10)
        assert [e.plugin_id for e in requeued] == ["pid-dead"]
        with audit_mod._db_lock:
            still_synced = audit_mod._get_db().execute(
                "SELECT COUNT(*) FROM audit_queue WHERE synced = 1"
            ).fetchone()[0]
        assert still_synced == 1

    def test_db_failure_returns_zero_and_logs_error(self, caplog):
        import logging

        from app.core.plugin import audit as audit_mod

        _drain_to_dead_letter(audit_mod)
        with (
            patch.object(audit_mod, "_get_db", side_effect=RuntimeError("database is locked")),
            caplog.at_level(logging.ERROR, logger="app.core.plugin.audit"),
        ):
            assert audit_mod.retry_dead_letters() == 0
        assert get_sync_status()["dead_letter"] == 1  # 失败不得把行清掉
        assert [r for r in caplog.records if r.levelno >= logging.ERROR]


# ── 退出前把队列排空 ──────────────────────────────────────────────────


class TestFlushOnShutdown:
    """SIGTERM 只做三件事：停后台线程、在预算内再同步一次、把没排空的量说清楚。

    第八十批把队列放上了卷，但 helm 的落点是 `$(POD_NAME)` 子目录——Pod 换成新名字后
    没有任何进程会去读旧目录，所以"在卷上"只有配上"退出前排空"才成立。
    """

    def test_drains_the_queue_and_reports_zero_remaining(self):
        from app.core.plugin import audit as audit_mod

        record_audit(plugin_id="pid-1", plugin_name="p", action="install")
        record_audit(plugin_id="pid-1", plugin_name="p", action="enable")
        with (
            patch.object(audit_mod, "_post_to_java_backend_batch", return_value=True) as batch,
            patch.object(audit_mod, "_post_to_java_backend", return_value=True),
        ):
            result = audit_mod.flush_on_shutdown()
        assert batch.call_count == 1
        assert result["flushed"] == 2
        assert result["remaining"] == 0
        # 排空的判据是"没有待发项"，不是"表空了"——synced 行按 7 天保留（_cleanup_synced:267-278）
        assert get_sync_status() == {"total": 2, "unsynced": 0, "dead_letter": 0}

    def test_empty_queue_reports_zero_without_touching_java(self):
        from app.core.plugin import audit as audit_mod

        def boom(*_a, **_k):
            raise AssertionError("空队列不该发起出站")

        with patch.object(audit_mod, "_post_to_java_backend_batch", side_effect=boom):
            result = audit_mod.flush_on_shutdown()
        assert result == {**result, "flushed": 0, "remaining": 0, "timed_out": False,
                          "error": None}

    def test_rows_survive_when_java_refuses_and_the_location_is_logged(self, caplog):
        """被拒时不得把行清掉，也不得报告已排空——落点目录要出现在日志里，否则运维不知道该查哪个 Pod 目录。"""
        import logging

        from app.core.plugin import audit as audit_mod

        record_audit(plugin_id="pid-1", plugin_name="p", action="install")
        with (
            patch.object(audit_mod, "_post_to_java_backend_batch", return_value=False),
            patch.object(audit_mod, "_post_to_java_backend", return_value=False),
            caplog.at_level(logging.WARNING, logger="app.core.plugin.audit"),
        ):
            result = audit_mod.flush_on_shutdown(budget_seconds=5)
        assert result["flushed"] == 0
        assert result["remaining"] == 1
        assert _queue_rows(audit_mod)[0][1] == 0  # synced 仍为 0
        messages = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
        assert any(str(audit_mod._DB_DIR) in m for m in messages), messages

    def test_stops_the_background_thread(self):
        from app.core.plugin import audit as audit_mod

        audit_mod._ensure_flush_thread()
        assert audit_mod._flush_thread.is_alive()
        try:
            with (
                patch.object(audit_mod, "_post_to_java_backend_batch", return_value=True),
                patch.object(audit_mod, "_post_to_java_backend", return_value=True),
            ):
                audit_mod.flush_on_shutdown()
            assert audit_mod._flush_stop.is_set()
            assert not audit_mod._flush_thread.is_alive()
        finally:
            audit_mod._flush_stop.clear()

    def test_returns_within_budget_when_java_hangs(self):
        """出站卡住时退出流程必须按时返回——优雅期一到就是 SIGKILL，拖延不会换来同步成功。"""
        import threading
        import time

        from app.core.plugin import audit as audit_mod

        record_audit(plugin_id="pid-1", plugin_name="p", action="install")
        release = threading.Event()

        def hang(_entries):
            release.wait(timeout=10)
            return False

        started = time.monotonic()
        try:
            with patch.object(audit_mod, "_post_to_java_backend_batch", side_effect=hang):
                result = audit_mod.flush_on_shutdown(budget_seconds=1.0)
        finally:
            release.set()
        elapsed = time.monotonic() - started
        assert result["timed_out"] is True
        assert result["flushed"] == 0
        assert elapsed < 3.0, f"退出被出站拖住 {elapsed:.1f}s"
        assert get_sync_status()["unsynced"] == 1  # 超时不等于失败确认，行必须还在

    def test_db_failure_is_reported_as_unknown_not_as_drained(self):
        """读不到队列时 remaining 是 None：把"不可确认"写成 0 就是第七十七批那族失明。"""
        from app.core.plugin import audit as audit_mod

        with patch.object(audit_mod, "_get_db", side_effect=RuntimeError("db locked")):
            result = audit_mod.flush_on_shutdown()
        assert result["remaining"] is None
        assert result["error"] and "db locked" in result["error"]

    def test_get_sync_status_still_degrades_to_zeros(self):
        """端点侧的降级口径不变：读不到就回三个 0，不能让 /audit/sync-status 500。"""
        from app.core.plugin import audit as audit_mod

        with patch.object(audit_mod, "_queue_counts", side_effect=RuntimeError("gone")):
            assert audit_mod.get_sync_status() == {"total": 0, "unsynced": 0, "dead_letter": 0}


# ── 审计队列的持久化落点（防回潮）─────────────────────────────────────


class TestAuditQueuePersistenceConfigured:
    """队列只落在运行用户的家目录里，而三套拓扑的卷挂在 /data 与 /app/uploads。

    第七十七批之前：地址错 → 每条审计重试 5 次进 dead-letter；
    第七十七批之后：能同步，但同步前的积压（以及任何 dead-letter 行）
    在容器重建时随镜像层一起消失——_persist_to_sqlite 的"crash recovery"
    注释在 shipped 拓扑里本就不成立。故按变量名钉住部署侧已显式配好落点。
    """

    def test_compose_files_set_the_audit_db_path(self):
        from pathlib import Path

        import yaml

        root = Path(__file__).resolve().parents[2]
        for rel in ("docker/docker-compose.yml", "deploy/docker-compose.prod.yml"):
            doc = yaml.safe_load((root / rel).read_text(encoding="utf-8"))
            env = doc["services"]["python-ai"]["environment"]
            assert "HFUSIONHUB_AUDIT_DB_PATH" in env, f"{rel} 未配置审计队列落点"
            assert env["HFUSIONHUB_AUDIT_DB_PATH"].startswith("/data/"), (
                f"{rel} 的审计落点不在已挂载的 /data 下"
            )

    def test_helm_python_sets_a_per_pod_audit_db_path(self):
        """helm 的 python 是 2 副本，家目录里的队列随 Pod 重建消失，必须显式配落点。

        `$(POD_NAME)` 只有在 env 列表里先定义 POD_NAME 才会展开（K8s 只用此前已定义的
        变量做替换）；按每 Pod 分目录是因为多副本共享同一个 SQLite 文件会互相踩锁。
        """
        text = self._helm_text("templates/python.yaml")
        env = self._helm_env(text)
        assert "HFUSIONHUB_AUDIT_DB_PATH" in env, "helm 未配置审计队列落点"
        assert env["HFUSIONHUB_AUDIT_DB_PATH"] == "/app/audit-queue/$(POD_NAME)"
        assert "fieldRef" in text and "metadata.name" in text, "POD_NAME 未从 downward API 取"
        assert text.index("- name: POD_NAME") < text.index("- name: HFUSIONHUB_AUDIT_DB_PATH"), (
            "POD_NAME 必须排在 HFUSIONHUB_AUDIT_DB_PATH 之前，否则 $() 不展开"
        )
        assert "/app/audit-queue" in text, "审计路径没有落在挂载点上"

    def test_helm_provides_an_rwx_audit_pvc(self):
        """审计卷必须是 RWX：RWO 卷在 replicas=2 时会让第二个 Pod 卡在 Pending。"""
        text = self._helm_text("templates/python.yaml")
        claims = [blk for blk in text.split("---")
                  if "kind: PersistentVolumeClaim" in blk and "audit-pvc" in blk]
        assert len(claims) == 1, "审计 PVC 应恰好一个"
        assert "ReadWriteMany" in claims[0], "审计卷不是 RWX，2 副本会卡 Pending"
        values = self._helm_text("values.yaml")
        assert "auditQueueSize" in values, "审计卷容量未进 values.yaml"

    @staticmethod
    def _helm_text(rel: str) -> str:
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        return (root / "deploy/helm/hfusionhub" / rel).read_text(encoding="utf-8")

    @staticmethod
    def _helm_env(text: str) -> dict[str, str]:
        """从 python.yaml 里按顺序抽出 `- name: X / value: Y` 环境变量对。"""
        import re

        return {name: value.strip('"') for name, value in re.findall(
            r"^ *- name: (\S+)\n +value: (\S+)$", text, re.MULTILINE)}

    def test_the_module_still_honours_the_env_var(self, monkeypatch, tmp_path):
        """落点由环境变量决定，家目录只是本地开发兜底。"""
        from app.core.plugin import audit as audit_mod

        monkeypatch.setenv("HFUSIONHUB_AUDIT_DB_PATH", str(tmp_path / "audit"))
        audit_mod._reset_db(None)
        try:
            assert audit_mod._DB_PATH == str(tmp_path / "audit" / "plugin_audit.db")
        finally:
            audit_mod._reset_db(str(tmp_path))
