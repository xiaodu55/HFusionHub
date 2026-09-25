"""
Feature Flag 单元测试 — 覆盖评估逻辑、降级策略、五层优先级、黑白名单与百分比。

运行: pytest tests/test_feature_flag.py -v
"""

import json
import logging
import os
import time
from unittest.mock import patch

import httpx

# Ensure transparent degradation for all tests (no Java backend)
os.environ.setdefault("FEATURE_FLAG_DEGRADATION", "transparent")

from app.utils.feature_flag import (
    AVAILABILITY_FLAGS,
    DENY_CAPABILITY_FLAGS,
    MUST_ENFORCE_FLAGS,
    SECURITY_FLAGS,
    FeatureFlagClient,
)

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
        """无缓存降级：每个安全旗标落到自己的安全方向（拒绝能力 / 保持强制）。"""
        client = FeatureFlagClient(cache_ttl=999)
        # No cache → deny-capability flags are refused
        for flag in DENY_CAPABILITY_FLAGS:
            assert client.is_enabled(flag) is False
        # No cache → must-enforce flags stay enforced
        for flag in MUST_ENFORCE_FLAGS:
            assert client.is_enabled(flag) is True
        # Union covers both sets
        assert SECURITY_FLAGS == DENY_CAPABILITY_FLAGS | MUST_ENFORCE_FLAGS

    @patch("app.utils.feature_flag.DEGRADATION_MODE", "fail_closed")
    def test_fail_closed_availability_flag(self):
        """无缓存降级：有 env 映射的旗标回退 env 派生值，其余放行（第十五轮 P0-9）。"""
        from app.utils.config import config as _config
        client = FeatureFlagClient(cache_ttl=999)
        env_expectations = {
            "rag.hybrid.enabled": _config.RAG_HYBRID_ENABLED,
            "rag.reranker.enabled": _config.RAG_RERANKER_MODE != "disabled",
            "agent.multi_agent.enabled": _config.RAG_MULTI_AGENT_ENABLED,
            "agent.enabled": _config.AGENT_ENABLED,
            "memory.long_term.enabled": _config.MEMORY_LONG_TERM_ENABLED,
            "agent.native_tool_calls.enabled": _config.AGENT_NATIVE_TOOL_CALLS_ENABLED,
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


# ── 快照拉取的信封判定（_fetch_all）─────────────────────────────────────────
#
# Java 的 /api/internal/feature-flags/snapshot 鉴权失败走 R.fail(403, …)，
# 那是 HTTP 200 + 信封 code:403 + data:null。raise_for_status() 看不见它，
# 于是"令牌坏了"会被写成"平台一个旗标都没配置"——整份在用缓存被清空。
# 这里的 fake 必须带 code：本模块此前没有任何测试覆盖 _fetch_all，
# 而没有信封形状的 fake 就看不见这个缺陷。

_SNAPSHOT_URL = "http://java:8080/api/internal/feature-flags/snapshot"
_REJECT_MSG = "Forbidden: invalid or missing X-Internal-Token"


class _FakeSnapshotResponse:
    def __init__(self, data=None, *, code=200, message="success", status_code=200):
        self.status_code = status_code
        self._payload = {"code": code, "message": message, "data": data}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", _SNAPSHOT_URL)
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=request,
                response=httpx.Response(self.status_code, request=request),
            )


class _UnparseableSnapshotResponse(_FakeSnapshotResponse):
    """HTTP 200 但正文不是 JSON（网关改写 / 空体）。"""

    def json(self):
        raise ValueError("Expecting value: line 1 column 1 (char 0)")


def _client_with_flags(*keys):
    client = FeatureFlagClient(cache_ttl=30)
    client._fetch_url = _SNAPSHOT_URL
    client._cache = {key: _make_flag(key, enabled=True) for key in keys}
    client._last_fetch = 0.0
    return client


def _warning_records(caplog):
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]


class TestSnapshotRejectionKeepsStaleCache:
    def test_rejected_snapshot_does_not_wipe_cache(self):
        client = _client_with_flags("agent.write_tools.enabled")
        with patch(
            "httpx.get",
            return_value=_FakeSnapshotResponse(code=403, message=_REJECT_MSG),
        ):
            client._fetch_all(force=True)
        assert "agent.write_tools.enabled" in client._cache

    @patch("app.utils.feature_flag.DEGRADATION_MODE", "fail_closed")
    def test_rejected_snapshot_keeps_flag_at_cached_value(self):
        """被拒绝后读到的必须还是旧快照的值，而不是无缓存降级方向。"""
        client = _client_with_flags("agent.write_tools.enabled")
        with patch(
            "httpx.get",
            return_value=_FakeSnapshotResponse(code=403, message=_REJECT_MSG),
        ):
            client._fetch_all(force=True)
        assert client.is_enabled("agent.write_tools.enabled") is True

    def test_rejected_snapshot_does_not_advance_last_fetch(self):
        client = _client_with_flags("guardrails.enabled")
        with patch(
            "httpx.get",
            return_value=_FakeSnapshotResponse(code=403, message=_REJECT_MSG),
        ):
            client._fetch_all(force=True)
        assert client._last_fetch == 0.0

    def test_rejection_is_logged_at_warning(self, caplog):
        client = _client_with_flags("agent.enabled")
        with caplog.at_level(logging.DEBUG, logger="hfusionhub.feature_flag"):
            with patch(
                "httpx.get",
                return_value=_FakeSnapshotResponse(code=403, message=_REJECT_MSG),
            ):
                client._fetch_all(force=True)
        warnings = _warning_records(caplog)
        assert warnings, "被 Java 拒绝却只记 debug，线上等同于静默"
        assert "403" in " ".join(warnings)

    def test_rejected_snapshot_is_retried_on_next_call(self):
        calls = []

        def _get(url, **kwargs):
            calls.append(url)
            return _FakeSnapshotResponse(code=403, message=_REJECT_MSG)

        client = _client_with_flags("agent.enabled")
        with patch("httpx.get", side_effect=_get):
            client._fetch_all()
            client._fetch_all()
        assert len(calls) == 2, "拒绝却推进 _last_fetch，会把重试推迟一个 TTL 周期"

    def test_envelope_without_code_is_treated_as_rejection(self):
        """不是 R 信封的 200 正文按拒绝处理，不能当"零旗标"覆盖缓存。"""
        client = _client_with_flags("guardrails.enabled")
        resp = _FakeSnapshotResponse(data=[{"flagKey": "guardrails.enabled", "enabled": True}])
        resp._payload.pop("code")
        with patch("httpx.get", return_value=resp):
            client._fetch_all(force=True)
        assert client._last_fetch == 0.0

    # ── 以下四例钉住"不是本缺陷"的路径，防止修复过度 ──

    def test_legitimate_empty_snapshot_still_clears_cache(self):
        client = _client_with_flags("agent.enabled")
        with patch("httpx.get", return_value=_FakeSnapshotResponse(data=[])):
            client._fetch_all(force=True)
        assert client._cache == {}
        assert client._last_fetch > 0.0

    def test_success_snapshot_populates_cache(self):
        client = _client_with_flags()
        flag = {"flagKey": "rag.hybrid.enabled", "enabled": True, "flagType": "boolean", "rules": []}
        with patch("httpx.get", return_value=_FakeSnapshotResponse(data=[flag])):
            client._fetch_all(force=True)
        assert client.is_enabled("rag.hybrid.enabled") is True

    def test_real_http_error_keeps_cache_and_warns(self, caplog):
        client = _client_with_flags("approval.required_for_write")
        with caplog.at_level(logging.DEBUG, logger="hfusionhub.feature_flag"):
            with patch("httpx.get", return_value=_FakeSnapshotResponse(status_code=500)):
                client._fetch_all(force=True)
        assert "approval.required_for_write" in client._cache
        assert _warning_records(caplog)

    def test_unparseable_200_body_keeps_cache_and_warns(self, caplog):
        client = _client_with_flags("guardrails.enabled")
        with caplog.at_level(logging.DEBUG, logger="hfusionhub.feature_flag"):
            with patch("httpx.get", return_value=_UnparseableSnapshotResponse()):
                client._fetch_all(force=True)
        assert "guardrails.enabled" in client._cache
        assert _warning_records(caplog)
