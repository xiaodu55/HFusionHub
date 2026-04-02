"""Tests for plugin audit trail."""

import pytest
from unittest.mock import patch
from app.core.plugin.audit import (
    record_audit,
    get_audit_log,
    clear_buffer,
    flush_to_backend,
    get_sync_status,
    record_install,
    record_enable,
    record_disable,
    record_uninstall,
    AuditEntry,
    VALID_ACTIONS,
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
