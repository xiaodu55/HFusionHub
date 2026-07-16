"""
Feature-flag degradation semantics (production fail_closed mode).

conftest forces FEATURE_FLAG_DEGRADATION=transparent for the general suite,
which leaves the production no-cache degradation paths untested. These tests
patch the module-level DEGRADATION_MODE to "fail_closed" and exercise exactly
the "backend unreachable, no cache" branch:

- deny-capability flags (write tools / web search) degrade to False → refused;
- must-enforce flags (guardrails / write approval) degrade to True → the
  control stays enforced instead of being silently waived;
- availability flags fall back to their env-derived value.
"""

import pytest
from unittest.mock import patch

from app.utils.feature_flag import FeatureFlagClient
from app.utils.config import config


@pytest.fixture
def client():
    """A client whose cache is always empty (simulates backend unreachable
    since boot) — every is_enabled() call takes the degradation branch."""
    return FeatureFlagClient(cache_ttl=999)


class TestFailClosedNoCache:
    @pytest.mark.parametrize("flag", [
        "guardrails.enabled",
        "guardrails.prompt_injection.enabled",
        "guardrails.content_moderation.enabled",
        "guardrails.pii_masking.enabled",
        "approval.required_for_write",
    ])
    @patch("app.utils.feature_flag.DEGRADATION_MODE", "fail_closed")
    def test_must_enforce_flags_stay_enforced(self, client, flag):
        """后端不可达时护栏与写审批必须保持强制，而不是被静默豁免。"""
        assert client.is_enabled(flag) is True

    @pytest.mark.parametrize("flag", [
        "agent.write_tools.enabled",
        "agent.web_search.enabled",
    ])
    @patch("app.utils.feature_flag.DEGRADATION_MODE", "fail_closed")
    def test_deny_capability_flags_are_refused(self, client, flag):
        assert client.is_enabled(flag) is False

    @patch("app.utils.feature_flag.DEGRADATION_MODE", "fail_closed")
    def test_unknown_flag_fails_closed(self, client):
        assert client.is_enabled("totally.unknown.flag") is False

    @patch("app.utils.feature_flag.DEGRADATION_MODE", "fail_closed")
    def test_agent_enabled_follows_env_fallback(self, client, monkeypatch):
        monkeypatch.setattr(config, "AGENT_ENABLED", False)
        assert client.is_enabled("agent.enabled") is False
        monkeypatch.setattr(config, "AGENT_ENABLED", True)
        assert client.is_enabled("agent.enabled") is True


class TestApprovalContract:
    """The safety contract the rest of the system relies on: when Java is
    unreachable, writes must NOT silently bypass approval."""

    @patch("app.utils.feature_flag.DEGRADATION_MODE", "fail_closed")
    def test_write_approval_required_when_backend_unreachable(self, client):
        assert client.is_enabled("approval.required_for_write", user_id=1, knowledge_base_id=1) is True

    @patch("app.utils.feature_flag.DEGRADATION_MODE", "fail_closed")
    def test_guardrail_master_switch_on_when_backend_unreachable(self, client):
        assert client.is_enabled("guardrails.enabled", user_id=1) is True
