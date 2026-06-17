"""
Feature Flag 单元测试 — 覆盖评估逻辑、降级策略、五层优先级、黑白名单与百分比。

运行: pytest tests/test_feature_flag.py -v
"""

import os
import time
import threading
from unittest.mock import patch, MagicMock

import pytest

# Ensure transparent degradation for all tests (no Java backend)
os.environ.setdefault("FEATURE_FLAG_DEGRADATION", "transparent")

from app.utils.feature_flag import FeatureFlagClient, SECURITY_FLAGS, AVAILABILITY_FLAGS, DEGRADATION_MODE


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_flag(key, enabled=False, percentage=None, whitelist=None, blacklist=None,
               start_time=None, end_time=None, rules=None):
    return {
        "flagKey": key,
        "enabled": enabled,
        "flagType": "boolean",
        "percentage": percentage,
        "whitelist": whitelist,
        "blacklist": blacklist,
        "startTime": start_time,
        "endTime": end_time,
        "rules": rules or [],
        "fetched_at": time.time(),
    }


def _make_rule(scope, scope_value=None, enabled=None, percentage=None,
               whitelist=None, blacklist=None):
    return {
        "scope": scope,
        "scopeValue": scope_value,
        "enabled": enabled,
        "percentage": percentage,
        "whitelist": whitelist,
        "blacklist": blacklist,
    }


# ── Time window tests ───────────────────────────────────────────────────────

class TestTimeWindow:
    def test_flag_not_yet_active(self):
        future = "2099-01-01T00:00:00"
        client = FeatureFlagClient(cache_ttl=999)
        client._cache = {"t": _make_flag("t", enabled=True, start_time=future)}
        assert client.is_enabled("t") is False

    def test_flag_expired(self):
        past = "2000-01-01T00:00:00"
        client = FeatureFlagClient(cache_ttl=999)
        client._cache = {"t": _make_flag("t", enabled=True, end_time=past)}
        assert client.is_enabled("t") is False

    def test_flag_within_window(self):
        client = FeatureFlagClient(cache_ttl=999)
        client._cache = {"t": _make_flag("t", enabled=True)}
        assert client.is_enabled("t") is True


# ── Five-layer priority tests ───────────────────────────────────────────────

class TestFiveLayerPriority:
    def test_global_default(self):
        client = FeatureFlagClient(cache_ttl=999)
        client._cache = {"f": _make_flag("f", enabled=True)}
        assert client.is_enabled("f") is True

    def test_tenant_overrides_global(self):
        rule = _make_rule("tenant", "42", enabled=False)
        client = FeatureFlagClient(cache_ttl=999)
        client._cache = {"f": _make_flag("f", enabled=True, rules=[rule])}
        # Different tenant → falls back to global
        assert client.is_enabled("f", tenant_id=99) is True
        # Matching tenant → rule applies
        assert client.is_enabled("f", tenant_id=42) is False

    def test_user_overrides_tenant(self):
        global_rule = _make_rule("global", enabled=True)
        tenant_rule = _make_rule("tenant", "1", enabled=False)
        user_rule = _make_rule("user", "100", enabled=True)
        client = FeatureFlagClient(cache_ttl=999)
        client._cache = {"f": _make_flag("f", enabled=False, rules=[global_rule, tenant_rule, user_rule])}
        # User 100 in tenant 1: user rule wins (enabled=True)
        assert client.is_enabled("f", user_id=100, tenant_id=1) is True
        # User 999 in tenant 1: tenant rule wins (enabled=False)
        assert client.is_enabled("f", user_id=999, tenant_id=1) is False

    def test_kb_overrides_user(self):
        user_rule = _make_rule("user", "100", enabled=False)
        kb_rule = _make_rule("kb", "77", enabled=True)
        client = FeatureFlagClient(cache_ttl=999)
        client._cache = {"f": _make_flag("f", enabled=False, rules=[user_rule, kb_rule])}
        # User 100, KB 77: kb rule wins
        assert client.is_enabled("f", user_id=100, knowledge_base_id=77) is True

    def test_environment_overrides_kb(self):
        kb_rule = _make_rule("kb", "77", enabled=True)
        env_rule = _make_rule("environment", "production", enabled=False)
        client = FeatureFlagClient(cache_ttl=999)
        client._cache = {"f": _make_flag("f", enabled=True, rules=[kb_rule, env_rule])}
        # KB 77, env production: env rule wins
        assert client.is_enabled("f", knowledge_base_id=77, environment="production") is False
        # KB 77, env staging: kb rule wins
        assert client.is_enabled("f", knowledge_base_id=77, environment="staging") is True


# ── Blacklist / whitelist / percentage tests ────────────────────────────────

class TestBlacklistWhitelistPercentage:
    def test_blacklist_always_denies(self):
        bl = _make_rule("global", enabled=True, blacklist='["100","200"]')
        client = FeatureFlagClient(cache_ttl=999)
        client._cache = {"f": _make_flag("f", enabled=True, rules=[bl])}
        assert client.is_enabled("f", user_id=100) is False
        assert client.is_enabled("f", user_id=300) is True

    def test_whitelist_allows_only_listed(self):
        wl = _make_rule("global", enabled=True, whitelist='["100","200"]')
        client = FeatureFlagClient(cache_ttl=999)
        client._cache = {"f": _make_flag("f", enabled=True, rules=[wl])}
        assert client.is_enabled("f", user_id=100) is True
        assert client.is_enabled("f", user_id=300) is False

    def test_blacklist_overrides_whitelist(self):
        """User in both blacklist and whitelist → blacklisted (deny wins)."""
        rule = _make_rule("global", enabled=True, whitelist='["100"]', blacklist='["100"]')
        client = FeatureFlagClient(cache_ttl=999)
        client._cache = {"f": _make_flag("f", enabled=True, rules=[rule])}
        assert client.is_enabled("f", user_id=100) is False

    def test_percentage_rollout(self):
        rule = _make_rule("global", enabled=True, percentage=50)
        client = FeatureFlagClient(cache_ttl=999)
        client._cache = {"f": _make_flag("f", enabled=True, rules=[rule])}
        # Deterministic: same user always gets same result
        results = [client.is_enabled("f", user_id=i) for i in range(1000)]
        pct_true = sum(results)
        # Should be roughly 50% (allow wide margin for hash distribution)
        assert 400 < pct_true < 600, f"Expected ~500, got {pct_true}"

    def test_percentage_with_blacklist(self):
        """Blacklist takes priority over percentage."""
        rule = _make_rule("global", enabled=True, percentage=100, blacklist='["42"]')
        client = FeatureFlagClient(cache_ttl=999)
        client._cache = {"f": _make_flag("f", enabled=True, rules=[rule])}
        # User 42 is blacklisted → always False
        assert client.is_enabled("f", user_id=42) is False
        # Other users → 100% rollout → True
        assert client.is_enabled("f", user_id=999) is True

    def test_flag_level_blacklist(self):
        """Blacklist on the flag (not rule) also works."""
        client = FeatureFlagClient(cache_ttl=999)
        client._cache = {"f": _make_flag("f", enabled=True, blacklist='["55"]')}
        assert client.is_enabled("f", user_id=55) is False
        assert client.is_enabled("f", user_id=56) is True

    def test_percentage_on_flag_level(self):
        """Percentage on the flag (not rule) applies when no rule matches."""
        client = FeatureFlagClient(cache_ttl=999)
        client._cache = {"f": _make_flag("f", enabled=True, percentage=0)}
        assert client.is_enabled("f", user_id=1) is False


# ── Cache and degradation tests ─────────────────────────────────────────────

class TestCacheAndDegradation:
    def test_cache_hit_returns_fresh(self):
        client = FeatureFlagClient(cache_ttl=999)
        client._cache = {"f": _make_flag("f", enabled=True)}
        client._last_fetch = time.time()
        assert client.is_enabled("f") is True

    def test_stale_cache_used(self):
        client = FeatureFlagClient(cache_ttl=0)  # everything stale
        client._cache = {"f": _make_flag("f", enabled=True)}
        client._last_fetch = time.time() - 999
        # Should still use stale cache (returns True)
        assert client.is_enabled("f") is True

    @patch("app.utils.feature_flag.DEGRADATION_MODE", "fail_closed")
    def test_fail_closed_security_flag(self):
        client = FeatureFlagClient(cache_ttl=999)
        # No cache → fail-closed for security flags
        for flag in SECURITY_FLAGS:
            assert client.is_enabled(flag) is False

    @patch("app.utils.feature_flag.DEGRADATION_MODE", "fail_closed")
    def test_fail_closed_availability_flag(self):
        """无缓存降级：有 env 映射的旗标回退 env 派生值，其余放行（第十五轮 P0-9）。"""
        from app.utils.config import config as _config
        client = FeatureFlagClient(cache_ttl=999)
        env_expectations = {
            "rag.hybrid.enabled": _config.RAG_HYBRID_ENABLED,
            "rag.reranker.enabled": _config.RAG_RERANKER_MODE != "disabled",
            "agent.multi_agent.enabled": _config.RAG_MULTI_AGENT_ENABLED,
        }
        for flag in AVAILABILITY_FLAGS:
            expected = env_expectations.get(flag, True)
            assert client.is_enabled(flag) is expected

    @patch("app.utils.feature_flag.DEGRADATION_MODE", "fail_closed")
    def test_availability_degradation_honours_env_false(self, monkeypatch):
        """env 显式关闭的旗标在后端不可达时不得被静默打开。"""
        import app.utils.feature_flag as ff
        monkeypatch.setattr(ff._env_fallback_value, "__defaults__", (), raising=False)
        client = FeatureFlagClient(cache_ttl=999)
        with patch.object(ff, "_env_fallback_value", lambda key: False if key == "agent.multi_agent.enabled" else None):
            assert client.is_enabled("agent.multi_agent.enabled") is False
            # 无映射旗标保持原放行默认
            assert client.is_enabled("agent.enabled") is True

    @patch("app.utils.feature_flag.DEGRADATION_MODE", "transparent")
    def test_transparent_all_true(self):
        client = FeatureFlagClient(cache_ttl=999)
        assert client.is_enabled("agent.write_tools.enabled") is True
        assert client.is_enabled("agent.enabled") is True
        assert client.is_enabled("unknown.flag") is True

    @patch("app.utils.feature_flag.DEGRADATION_MODE", "fail_open")
    def test_fail_open_all_true(self):
        client = FeatureFlagClient(cache_ttl=999)
        assert client.is_enabled("agent.write_tools.enabled") is True
        assert client.is_enabled("unknown.flag") is True


# ── Deterministic hash tests ────────────────────────────────────────────────

class TestDeterministicHash:
    def test_same_input_same_hash(self):
        h1 = FeatureFlagClient._deterministic_hash("test:123")
        h2 = FeatureFlagClient._deterministic_hash("test:123")
        assert h1 == h2

    def test_different_input_different_hash(self):
        h1 = FeatureFlagClient._deterministic_hash("test:123")
        h2 = FeatureFlagClient._deterministic_hash("test:456")
        assert h1 != h2


# ── Scope matching tests ────────────────────────────────────────────────────

class TestScopeMatching:
    def test_global_always_matches(self):
        client = FeatureFlagClient(cache_ttl=999)
        rule = _make_rule("global", enabled=True)
        assert client._scope_matches(rule, 1, 2, 3, "prod") is True

    def test_tenant_matches(self):
        client = FeatureFlagClient(cache_ttl=999)
        rule = _make_rule("tenant", "42", enabled=True)
        assert client._scope_matches(rule, None, None, 42, None) is True
        assert client._scope_matches(rule, None, None, 99, None) is False

    def test_user_matches(self):
        client = FeatureFlagClient(cache_ttl=999)
        rule = _make_rule("user", "100", enabled=True)
        assert client._scope_matches(rule, 100, None, None, None) is True
        assert client._scope_matches(rule, 999, None, None, None) is False

    def test_kb_matches(self):
        client = FeatureFlagClient(cache_ttl=999)
        rule = _make_rule("kb", "77", enabled=True)
        assert client._scope_matches(rule, None, 77, None, None) is True
        assert client._scope_matches(rule, None, 99, None, None) is False

    def test_environment_matches_case_insensitive(self):
        client = FeatureFlagClient(cache_ttl=999)
        rule = _make_rule("environment", "Production", enabled=True)
        assert client._scope_matches(rule, None, None, None, "production") is True
        assert client._scope_matches(rule, None, None, None, "staging") is False


# ── JSON helper tests ───────────────────────────────────────────────────────

class TestJsonContains:
    def test_valid_json_array(self):
        assert FeatureFlagClient._json_contains('["1","2","3"]', "2") is True
        assert FeatureFlagClient._json_contains('["1","2","3"]', "4") is False

    def test_invalid_json(self):
        assert FeatureFlagClient._json_contains("not-json", "1") is False

    def test_empty_string(self):
        assert FeatureFlagClient._json_contains("", "1") is False
