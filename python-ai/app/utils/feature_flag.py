"""
Feature Flag client for Python AI service.

Calls Java backend internal snapshot endpoint and caches locally with a short TTL.
Evaluates flags using the same 5-layer override logic as Java.

Usage:
    from app.utils.feature_flag import feature_flags

    if feature_flags.is_enabled("rag.graph.enabled", user_id=1, kb_id=101):
        ...  # graph retrieval on
"""

import json
import hashlib
import os
import time
import threading
from typing import Optional
from loguru import logger

from app.utils.config import config

SCOPE_PRIORITY = {"environment": 5, "kb": 4, "user": 3, "tenant": 2, "global": 1}

# ── Flag classification for degraded-mode behavior ──────────────────────────
# SECURITY flags: must be OFF when backend is unreachable (fail-closed).
# AVAILABILITY flags: preserve env-var config when backend is unreachable.
SECURITY_FLAGS = frozenset({
    "agent.write_tools.enabled",
    "agent.web_search.enabled",
    "approval.required_for_write",
    # Content safety guardrails — must be OFF (disabled) when the backend is
    # unreachable: a guardrail that silently disappears is worse than none.
    "guardrails.enabled",
    "guardrails.prompt_injection.enabled",
    "guardrails.content_moderation.enabled",
    "guardrails.pii_masking.enabled",
})

AVAILABILITY_FLAGS = frozenset({
    "rag.hybrid.enabled",
    "rag.graph.enabled",
    "rag.reranker.enabled",
    "agent.multi_agent.enabled",
    "agent.enabled",
})

# Degradation modes (controlled by FEATURE_FLAG_DEGRADATION env var):
#   "fail_closed" — security flags → False, availability → True (production default)
#   "transparent" — all flags → True, preserve env-var config (tests / dev)
#   "fail_open"   — all flags → True (not recommended for production)
DEGRADATION_MODE = os.getenv("FEATURE_FLAG_DEGRADATION", "fail_closed").lower()


class FeatureFlagClient:
    """Thread-safe, TTL-cached feature flag evaluator.

    Degradation policy:
    - Cache fresh → use cached value (normal path).
    - Cache expired but stale data exists → use stale data, schedule background refresh.
    - No cache at all (first boot, backend unreachable):
      * SECURITY flags → False (fail-closed).
      * AVAILABILITY flags → True (preserve env-var config).
      * Unknown flags → False (fail-closed).
    """

    def __init__(self, cache_ttl: int = 30):
        self._cache_ttl = cache_ttl
        self._cache: dict = {}          # flag_key → {enabled, rules, fetched_at}
        self._lock = threading.Lock()
        self._last_fetch: float = 0
        self._fetch_url = f"{config.JAVA_BACKEND_URL}/api/internal/feature-flags/snapshot"
        self._internal_token = getattr(config, "INTERNAL_API_TOKEN", "")

    # ── public API ──────────────────────────────────────────

    def is_enabled(
        self,
        flag_key: str,
        user_id: Optional[int] = None,
        knowledge_base_id: Optional[int] = None,
        tenant_id: Optional[int] = None,
        environment: Optional[str] = None,
    ) -> bool:
        """Return whether flag_key is enabled for the given context.

        Degradation (when Java backend unreachable and no cache):
        - "fail_closed" mode: security flags → False, availability → True
        - "transparent" mode: all flags → True (preserve env-var config)
        - "fail_open" mode: all flags → True
        """
        entry, is_stale = self._get_entry(flag_key)

        if entry is None:
            # No cache at all — apply degradation policy
            if DEGRADATION_MODE == "transparent":
                return True  # preserve env-var config
            if DEGRADATION_MODE == "fail_open":
                return True
            # fail_closed (default): security flags → False, availability → True
            if flag_key in SECURITY_FLAGS:
                logger.warning(f"Feature flag '{flag_key}' degraded to FAIL-CLOSED (no cache)")
                return False
            if flag_key in AVAILABILITY_FLAGS:
                logger.info(f"Feature flag '{flag_key}' degraded to permissive (preserve env config)")
                return True
            logger.warning(f"Feature flag '{flag_key}' degraded to FAIL-CLOSED (unknown flag, no cache)")
            return False

        if is_stale:
            logger.debug(f"Feature flag '{flag_key}' using stale cache (backend unreachable)")

        return self._evaluate(entry, user_id, knowledge_base_id, tenant_id, environment)

    def force_refresh(self):
        """Force an immediate cache refresh (best-effort)."""
        self._fetch_all(force=True)

    # ── cache management ────────────────────────────────────

    def _get_entry(self, flag_key: str) -> tuple[Optional[dict], bool]:
        """Return (entry, is_stale). entry=None means no cache at all."""
        with self._lock:
            entry = self._cache.get(flag_key)
            if entry:
                age = time.time() - entry["fetched_at"]
                if age < self._cache_ttl:
                    return entry, False
                # Expired but still present → use as stale, trigger background refresh
                self._trigger_background_refresh()
                return entry, True
        # No cache entry → 不在请求路径上做同步网络调用（避免阻塞事件循环）：
        # 触发后台刷新，立即返回 None 由调用方按降级策略处理（保留环境变量配置）。
        self._trigger_background_refresh()
        return None, False

    def _trigger_background_refresh(self):
        """Fire-and-forget background refresh if not already running."""
        if not self._refresh_thread or not self._refresh_thread.is_alive():
            self._refresh_thread = threading.Thread(target=self._fetch_all, daemon=True)
            self._refresh_thread.start()

    @property
    def _refresh_thread(self):
        return getattr(self, "_bg_thread", None)

    @_refresh_thread.setter
    def _refresh_thread(self, t):
        self._bg_thread = t

    def _fetch_all(self, force: bool = False):
        now = time.time()
        if not force and (now - self._last_fetch) < self._cache_ttl:
            return
        try:
            import httpx
            headers = {}
            if self._internal_token:
                headers["X-Internal-Token"] = self._internal_token
            resp = httpx.get(self._fetch_url, headers=headers, timeout=5.0)
            resp.raise_for_status()
            data = resp.json()
            flags = data.get("data") or []
            new_cache = {}
            for f in flags:
                key = f.get("flagKey")
                if key:
                    new_cache[key] = {
                        "enabled": f.get("enabled", False),
                        "flagType": f.get("flagType", "boolean"),
                        "percentage": f.get("percentage"),
                        "whitelist": f.get("whitelist"),
                        "blacklist": f.get("blacklist"),
                        "startTime": f.get("startTime"),
                        "endTime": f.get("endTime"),
                        "rules": f.get("rules", []),
                        "fetched_at": now,
                    }
            with self._lock:
                self._cache = new_cache
                self._last_fetch = now
            logger.debug(f"Feature flags refreshed: {len(new_cache)} flags")
        except Exception as e:
            logger.warning(f"Feature flag fetch failed (using stale cache): {e}")

    # ── evaluation ──────────────────────────────────────────

    def _evaluate(
        self,
        entry: dict,
        user_id: Optional[int],
        knowledge_base_id: Optional[int],
        tenant_id: Optional[int],
        environment: Optional[str],
    ) -> bool:
        """Evaluate flag with deterministic order:
        time_window → blacklist → whitelist → percentage → default enabled.
        """
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%S")

        # 1. Time window
        start = entry.get("startTime")
        end = entry.get("endTime")
        if start and now_iso < start:
            return False
        if end and now_iso > end:
            return False

        # 2. Sort rules by priority descending (environment > kb > user > tenant > global)
        rules = sorted(
            entry.get("rules", []),
            key=lambda r: SCOPE_PRIORITY.get(r.get("scope"), 0),
            reverse=True,
        )

        # 3. Find first matching rule
        for rule in rules:
            if self._scope_matches(rule, user_id, knowledge_base_id, tenant_id, environment):
                return self._resolve_with_order(entry, rule, user_id)

        # 4. No rule matched → apply flag-level lists/percentage/default
        return self._resolve_flag_level(entry, user_id)

    def _scope_matches(
        self, rule: dict,
        user_id, kb_id, tenant_id, environment
    ) -> bool:
        scope = rule.get("scope")
        sv = rule.get("scopeValue")
        if scope == "global":
            return True
        if scope == "tenant" and tenant_id is not None:
            return str(tenant_id) == str(sv)
        if scope == "user" and user_id is not None:
            return str(user_id) == str(sv)
        if scope == "kb" and kb_id is not None:
            return str(kb_id) == str(sv)
        if scope == "environment" and environment is not None:
            return environment.lower() == str(sv).lower()
        return False

    def _resolve_with_order(self, entry: dict, rule: dict, user_id) -> bool:
        """Resolve enabled with fixed order: blacklist → whitelist → percentage → default.

        The rule's ``enabled`` field provides the base value.  Lists and
        percentages are overlays that can flip the result:
          - blacklist match  → always False
          - whitelist match  → base value
          - percentage match → base AND in-percentage
          - otherwise        → base
        """
        base = rule.get("enabled") if rule.get("enabled") is not None else entry.get("enabled", False)

        # Resolve effective lists (rule overrides flag)
        bl = rule.get("blacklist") if rule.get("blacklist") is not None else entry.get("blacklist")
        wl = rule.get("whitelist") if rule.get("whitelist") is not None else entry.get("whitelist")
        pct = rule.get("percentage") if rule.get("percentage") is not None else entry.get("percentage")

        # Blacklist (highest priority — always deny)
        if bl and user_id is not None and self._json_contains(bl, str(user_id)):
            return False

        # Whitelist (if present, user must be in it)
        if wl and user_id is not None:
            return base and self._json_contains(wl, str(user_id))

        # Percentage rollout
        if pct is not None and user_id is not None:
            h = self._deterministic_hash(f"{entry.get('flagKey', '')}:{user_id}")
            in_pct = (abs(h) % 100) < pct
            return base and in_pct

        return base

    def _resolve_flag_level(self, entry: dict, user_id) -> bool:
        """Apply flag-level blacklist/whitelist/percentage when no rule matches."""
        base = entry.get("enabled", False)

        bl = entry.get("blacklist")
        wl = entry.get("whitelist")
        pct = entry.get("percentage")

        # Blacklist (highest priority — always deny)
        if bl and user_id is not None and self._json_contains(bl, str(user_id)):
            return False

        # Whitelist (if present, user must be in it)
        if wl and user_id is not None:
            return base and self._json_contains(wl, str(user_id))

        # Percentage rollout
        if pct is not None and user_id is not None:
            h = self._deterministic_hash(f"{entry.get('flagKey', '')}:{user_id}")
            in_pct = (abs(h) % 100) < pct
            return base and in_pct

        return base

    @staticmethod
    def _json_contains(json_str: str, value: str) -> bool:
        try:
            items = json.loads(json_str) if isinstance(json_str, str) else json_str
            return str(value) in [str(i) for i in items]
        except Exception:
            return False

    @staticmethod
    def _deterministic_hash(input_str: str) -> int:
        digest = hashlib.sha256(input_str.encode("utf-8")).digest()
        h = 0
        for b in digest[:8]:
            h = (h << 8) | b
        return h


# Module-level singleton
feature_flags = FeatureFlagClient(cache_ttl=30)
