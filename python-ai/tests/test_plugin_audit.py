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
