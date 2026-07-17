"""Content Safety Guardrails — prompt injection, PII masking, content moderation.

Layered rule-based safety controls for the AI service, applied at two
choke points:

  * :meth:`GuardrailsPipeline.check_input` — user messages and tool
    arguments, before execution.
  * :meth:`GuardrailsPipeline.check_output` — model responses, before they
    are returned to the caller.

Run order for input is: **prompt injection detection → PII masking →
content moderation**.  A *critical* injection short-circuits the pipeline
(fast-path block) so nothing downstream sees the dangerous input.

Feature-flag gating
-------------------
Each component is governed by a Java-managed feature flag (``guardrails.*``)
combined with an env-var kill-switch in :class:`app.utils.config.Config`:

  * ``guardrails.prompt_injection.enabled``   ↔ ``GUARDRAILS_PROMPT_INJECTION_ENABLED``
  * ``guardrails.content_moderation.enabled`` ↔ ``GUARDRAILS_CONTENT_MODERATION_ENABLED``
  * ``guardrails.pii_masking.enabled``        ↔ ``GUARDRAILS_PII_MASKING_ENABLED``
  * ``guardrails.enabled``                    ↔ ``GUARDRAILS_ENABLED`` (master switch)

The flags are registered in :data:`app.utils.feature_flag.MUST_ENFORCE_FLAGS`, so
they **stay enforced** when the Java backend is unreachable (degraded mode →
controls remain on; the env-var kill-switches above are the explicit way to
hard-disable a component).  They activate once registered in Java (or under
``FEATURE_FLAG_DEGRADATION=transparent`` used by tests).

All detection logic is pure over strings (regex / keyword matching) and is
kept separate from I/O; flag resolution is isolated in :func:`_flag_enabled`,
which :class:`GuardrailsPipeline` calls through an injectable resolver so
tests can bypass the network.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Pattern

from app.utils.config import config
from app.utils.feature_flag import feature_flags

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Severity model
# ═══════════════════════════════════════════════════════════════════════════

SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def _worse(a: str, b: str) -> str:
    """Return the more severe of two severity labels."""
    return a if SEVERITY_ORDER.get(a, 0) >= SEVERITY_ORDER.get(b, 0) else b


# ═══════════════════════════════════════════════════════════════════════════
# Prompt injection patterns (module-level compiled constants)
# ═══════════════════════════════════════════════════════════════════════════
# Each entry: (pattern_name, compiled_regex, severity).

INJECTION_PATTERNS: list[tuple[str, Pattern[str], str]] = [
    # ── Role switching ───────────────────────────────────────────────
    ("role_switch_dan",
     re.compile(r"\byou\s+are\s+now\s+(?:a\s+)?(?:DAN|jailbroken|uncensored)\b", re.IGNORECASE),
     "critical"),
    ("role_switch_ignore_instructions",
     re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior|earlier|above)\s+instructions", re.IGNORECASE),
     "high"),
    ("role_switch_disregard",
     re.compile(r"disregard\s+(?:all\s+)?(?:previous|prior|earlier|above)\s+instructions", re.IGNORECASE),
     "high"),
    ("role_switch_override",
     re.compile(r"override\s+(?:your|the|all)\s+(?:system\s+)?(?:instructions|rules|guidelines|prompt)", re.IGNORECASE),
     "high"),
    ("role_switch_no_rules",
     re.compile(r"\byou\s+(?:now\s+)?have\s+no\s+(?:rules|restrictions|limitations|filters)", re.IGNORECASE),
     "high"),
    ("role_switch_forget",
     re.compile(r"forget\s+(?:everything|all\s+(?:your\s+)?(?:previous|prior)\s+(?:instructions|rules))", re.IGNORECASE),
     "medium"),
    ("role_switch_pretend_admin",
     re.compile(r"pretend\s+(?:to\s+be|you\s+are)\s+(?:an?\s+)?(?:system|developer|admin)", re.IGNORECASE),
     "medium"),
    ("role_switch_new_role",
     re.compile(r"\b(?:new\s+)?role\s*(?:is|:|=|to\s+be)\s*(?:system|developer|admin)", re.IGNORECASE),
     "medium"),
    # ── Delimiter injection ──────────────────────────────────────────
    ("delimiter_fence",
     re.compile(r"```\s*(?:system|developer|instructions|prompt)", re.IGNORECASE),
     "high"),
    ("delimiter_tag",
     re.compile(r"</?\s*(?:system|developer|instructions|prompt)\s*>", re.IGNORECASE),
     "medium"),
    # ── Prompt leaking ───────────────────────────────────────────────
    ("leak_reveal",
     re.compile(r"reveal\s+(?:your|the|its)\s+(?:full\s+)?(?:system\s+)?(?:prompt|instructions|rules)", re.IGNORECASE),
     "critical"),
    ("leak_print",
     re.compile(r"\b(?:print|repeat|output|say|state|write\s+out)\s+(?:your|the)\s+(?:initial\s+|full\s+)?(?:system\s+)?(?:prompt|instructions)", re.IGNORECASE),
     "high"),
    ("leak_show",
     re.compile(r"show\s+me\s+(?:your|the)\s+(?:system\s+)?(?:prompt|instructions)", re.IGNORECASE),
     "medium"),
    ("leak_what",
     re.compile(r"\bwhat\s+(?:are|is)\s+(?:your|the)\s+(?:system\s+)?(?:prompt|instructions|rules)", re.IGNORECASE),
     "medium"),
    ("leak_system_prompt_eq",
     re.compile(r"\b(?:system|initial)\s+prompt\s*(?:is|=|:)", re.IGNORECASE),
     "medium"),
    # ── Evasion / encoding tricks ────────────────────────────────────
    ("evasion_encoding",
     re.compile(r"\b(?:base64|rot\s*13|caesar\s+cipher|reverse\s+text)\s+(?:decode|encode|obfuscate|to\s+hide)", re.IGNORECASE),
     "low"),
]

# Two or more high/critical hits escalate to critical (composite jailbreak).
_ESCALATION_HIGH_COUNT = 2


def _aggregate_severity(matched: list[tuple[str, str]]) -> str:
    """Aggregate per-pattern severities; escalate composites to critical."""
    worst = "low"
    for _name, sev in matched:
        if SEVERITY_ORDER.get(sev, 0) > SEVERITY_ORDER.get(worst, 0):
            worst = sev
    if worst == "high":
        high_count = sum(1 for _n, s in matched if SEVERITY_ORDER.get(s, 0) >= SEVERITY_ORDER["high"])
        if high_count >= _ESCALATION_HIGH_COUNT:
            return "critical"
    return worst


def _remove_spans(text: str, spans: list[tuple[int, int]]) -> str:
    """Remove (start, end) spans from *text*, merging overlaps, preserving order."""
    if not spans:
        return text
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    parts: list[str] = []
    cursor = 0
    for start, end in merged:
        parts.append(text[cursor:start])
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)


@dataclass(frozen=True)
class InjectionResult:
    """Outcome of prompt-injection detection."""

    is_injection: bool
    severity: str = "low"
    matched_patterns: list[str] = field(default_factory=list)
    sanitized_input: str = ""


class PromptInjectionDetector:
    """Rule-based prompt-injection detector (pure, no I/O).

    Detection is a pure function over a string; flag gating happens in
    :class:`GuardrailsPipeline`.  The dangerous matches are removed from
    :attr:`InjectionResult.sanitized_input`.
    """

    def detect(self, text: str) -> InjectionResult:
        """Scan *text* for injection patterns; return an :class:`InjectionResult`."""
        if not text:
            return InjectionResult(False, "low", [], "")
        matched: list[tuple[str, str]] = []
        spans: list[tuple[int, int]] = []
        for name, pattern, severity in INJECTION_PATTERNS:
            for m in pattern.finditer(text):
                matched.append((name, severity))
                spans.append((m.start(), m.end()))
        if not matched:
            return InjectionResult(False, "low", [], text)
        severity = _aggregate_severity(matched)
        # Deduplicate pattern names, preserving first-occurrence order.
        names: list[str] = []
        for name, _sev in matched:
            if name not in names:
                names.append(name)
        return InjectionResult(
            is_injection=True,
            severity=severity,
            matched_patterns=names,
            sanitized_input=_remove_spans(text, spans),
        )


# ═══════════════════════════════════════════════════════════════════════════
# PII patterns (module-level compiled constants)
# ═══════════════════════════════════════════════════════════════════════════
# Each entry: (type, compiled_regex, placeholder).  Order matters — earlier
# patterns take priority when spans overlap (e.g. a credit card wins over the
# more generic phone pattern).

PII_PATTERNS: list[tuple[str, Pattern[str], str]] = [
    # ── API keys / tokens (highest priority — longest distinctive runs) ──
    ("api_key", re.compile(r"\bsk(?:-|_)?[A-Za-z0-9]{16,}\b"), "[API_KEY]"),
    ("api_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[API_KEY]"),
    ("api_key", re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "[API_KEY]"),
    ("api_key", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "[API_KEY]"),
    ("api_key", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}\b"), "[API_KEY]"),
    ("api_key", re.compile(r"\b[A-Za-z0-9]{32,}\b"), "[API_KEY]"),
    # ── Credit cards (Luhn-validated, 13–19 digits) ───────────────────
    ("credit_card", re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[CREDIT_CARD]"),
    # ── SSN / national ID numbers ────────────────────────────────────
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    ("ssn", re.compile(r"\b[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b"), "[SSN]"),
    ("ssn", re.compile(r"\b(?:ID\s*[:#]?\s*|身份证\s*[:#号]?\s*)\d{6,18}\b"), "[SSN]"),
    # ── Email addresses ───────────────────────────────────────────────
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    # ── IP addresses (IPv4 + common IPv6 forms) ───────────────────────
    ("ip_addr", re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b"
    ), "[IP_ADDR]"),
    ("ip_addr", re.compile(
        r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b"
    ), "[IP_ADDR]"),
    ("ip_addr", re.compile(
        r"\b(?:[0-9a-fA-F]{1,4}:){1,6}:(?:[0-9a-fA-F]{1,4}(?::[0-9a-fA-F]{1,4}){0,4})?\b"
    ), "[IP_ADDR]"),
    # ── Phone numbers (most generic — processed last) ─────────────────
    ("phone", re.compile(
        r"(?<!\d)(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4}(?!\d)"
    ), "[PHONE]"),
]


def _luhn_valid(digits: str) -> bool:
    """Return True when *digits* (13–19 chars) passes the Luhn checksum.

    Used to reduce false positives on arbitrary long digit runs (order
    numbers, timestamps) while still catching spaced/dashed card numbers.
    """
    if not digits.isdigit() or not (13 <= len(digits) <= 19):
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _scan_pii_types(text: str) -> list[str]:
    """Return ordered, deduplicated PII types present in *text* (pure scan)."""
    found: list[str] = []
    for ptype, pattern, _placeholder in PII_PATTERNS:
        for m in pattern.finditer(text):
            if ptype == "credit_card" and not _luhn_valid(re.sub(r"[^0-9]", "", m.group(0))):
                continue
            if ptype not in found:
                found.append(ptype)
    return found


class PIIMasker:
    """Detect and mask PII with typed placeholders, tracking an audit trail.

    Masked values are stored in an in-memory, capacity-bounded vault keyed by
    placeholder (``[EMAIL]``, ``[EMAIL_2]``, …) so :meth:`unmask` can restore
    them for internal logs/audit reconstruction.  The vault is deliberately
    *not* exposed through the public API — the status endpoint reports counts
    and audit metadata only.
    """

    def __init__(self, vault_capacity: int = 500, audit_capacity: int = 200):
        self._vault_capacity = vault_capacity
        self._vault: dict[str, str] = {}          # placeholder → original value
        self._reverse: dict[str, str] = {}        # original value → placeholder
        self._counts: dict[str, int] = defaultdict(int)  # placeholder_type → count
        self._audit: deque = deque(maxlen=audit_capacity)
        self._lock = threading.RLock()

    def mask(self, text: str) -> tuple[str, list[dict[str, Any]]]:
        """Mask all PII in *text*.

        Returns ``(masked_text, entries)`` where *entries* describes what was
        masked in this call (placeholder, placeholder_type, value) and is
        empty when nothing was masked.
        """
        if not text:
            return text, []
        accepted: list[tuple[int, int, str, str]] = []  # start, end, value, type
        for ptype, pattern, _placeholder in PII_PATTERNS:
            for m in pattern.finditer(text):
                value = m.group(0)
                if ptype == "credit_card" and not _luhn_valid(re.sub(r"[^0-9]", "", value)):
                    continue
                if any(s <= m.start() < e for s, e, _v, _t in accepted):
                    continue  # overlapping span already claimed by higher priority
                accepted.append((m.start(), m.end(), value, ptype))

        accepted.sort(key=lambda item: item[0])
        entries: list[dict[str, Any]] = []
        parts: list[str] = []
        cursor = 0
        for start, end, value, ptype in accepted:
            parts.append(text[cursor:start])
            placeholder = self._register(value, ptype)
            parts.append(placeholder)
            cursor = end
            entries.append({
                "placeholder": placeholder,
                "placeholder_type": ptype,
                "value": value,
            })
        parts.append(text[cursor:])
        return "".join(parts), entries

    def unmask(self, text: str) -> str:
        """Replace known placeholders in *text* back with their stored values."""
        if not text:
            return text
        with self._lock:
            for placeholder, value in self._vault.items():
                text = text.replace(placeholder, value)
        return text

    def audit_trail(self, limit: int = 50, include_values: bool = False) -> list[dict[str, Any]]:
        """Return the most recent masking audit entries (metadata only by default)."""
        with self._lock:
            entries = list(self._audit)[-limit:]
        if include_values:
            return entries
        return [{k: v for k, v in e.items() if k != "value"} for e in entries]

    def summary(self) -> dict[str, int]:
        """Per-type masked-value counters."""
        with self._lock:
            return dict(self._counts)

    def _register(self, value: str, ptype: str) -> str:
        """Store *value* in the vault and return its typed placeholder.

        Placeholders use the canonical uppercase form (``[EMAIL]``); the
        per-type counters stay lowercase internally.
        """
        with self._lock:
            existing = self._reverse.get(value)
            if existing:
                return existing
            n = self._counts[ptype] + 1
            self._counts[ptype] = n
            base = f"[{ptype.upper()}]"
            placeholder = base if n == 1 else f"[{ptype.upper()}_{n}]"
            self._vault[placeholder] = value
            self._reverse[value] = placeholder
            if len(self._vault) > self._vault_capacity:
                oldest_placeholder, oldest_value = next(iter(self._vault.items()))
                del self._vault[oldest_placeholder]
                self._reverse.pop(oldest_value, None)
            self._audit.append({
                "ts": time.time(),
                "placeholder": placeholder,
                "placeholder_type": ptype,
                "value": value,
            })
            return placeholder


# ═══════════════════════════════════════════════════════════════════════════
# Content moderation lexicons (module-level compiled constants)
# ═══════════════════════════════════════════════════════════════════════════

# ASCII profanity / slurs / hate speech — matched with word boundaries so
# "assassin" never triggers on "ass".
_TOXIC_ASCII_KEYWORDS: tuple[str, ...] = (
    "fuck", "fucking", "motherfucker", "shit", "bitch", "bastard",
    "asshole", "dickhead", "wanker", "cunt",
    "nigger", "nigga", "faggot", "fag", "kike", "chink", "spic", "wetback",
    "retard", "kill yourself", "go die", "die in a fire", "kill all",
)
_TOXIC_CJK_KEYWORDS: tuple[str, ...] = (
    "傻逼", "傻b", "妈的", "他妈的", "操你妈", "草泥马", "混蛋",
    "贱人", "王八蛋", "婊子", "去死", "滚蛋", "白痴", "弱智",
)
_TOXIC_ASCII_PATTERNS: tuple[Pattern[str], ...] = tuple(
    re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE) for kw in _TOXIC_ASCII_KEYWORDS
)

# Model-output "confidence without evidence" markers — flagged, not blocked.
HALLUCINATION_MARKERS: tuple[str, ...] = (
    "as an ai language model",
    "according to my training data",
    "based on my training data",
    "i am 100% certain",
    "i am absolutely certain",
    "i know for a fact",
    "i guarantee",
    "i can assure you",
    "this is definitely",
    "this is 100% accurate",
    "i'm 100% sure",
    "without a doubt",
    "i have verified",
    "trust me,",
)


def _find_toxic_keywords(text: str) -> list[str]:
    """Return the toxic keywords present in *text* (pure scan)."""
    lowered = text.lower()
    hits: list[str] = []
    for keyword, pattern in zip(_TOXIC_ASCII_KEYWORDS, _TOXIC_ASCII_PATTERNS):
        if pattern.search(text) and keyword not in hits:
            hits.append(keyword)
    for keyword in _TOXIC_CJK_KEYWORDS:
        if keyword in lowered and keyword not in hits:
            hits.append(keyword)
    return hits


def _find_hallucination_markers(text: str) -> list[str]:
    """Return the hallucination markers present in *text* (pure scan)."""
    lowered = text.lower()
    return [marker for marker in HALLUCINATION_MARKERS if marker in lowered]


@dataclass(frozen=True)
class ModerationResult:
    """Outcome of content moderation.

    ``passed`` is informational for a standalone moderator check: it is
    False on a hard-block finding (critical injection or toxic content).
    The pipeline makes the final allow/block decision from the flags.
    """

    passed: bool
    flags: list[str] = field(default_factory=list)
    severity: str = "low"
    sanitized: str | None = None


class ContentModerator:
    """Rule-based moderation for user input and AI output (pure over strings)."""

    def __init__(
        self,
        detector: PromptInjectionDetector | None = None,
        masker: PIIMasker | None = None,
    ):
        self._detector = detector or PromptInjectionDetector()
        self._masker = masker or PIIMasker()

    def check_input(
        self,
        text: str,
        enable_injection: bool = True,
    ) -> ModerationResult:
        """Moderate a user message: injection, PII, toxic content."""
        if not text:
            return ModerationResult(True, [], "low", None)
        flags: list[str] = []
        severity = "low"
        sanitized: str | None = None

        if enable_injection:
            inj = self._detector.detect(text)
            if inj.is_injection:
                flags.append(f"prompt_injection:{inj.severity}")
                severity = _worse(severity, inj.severity)
                sanitized = inj.sanitized_input

        for ptype in _scan_pii_types(text):
            flags.append(f"pii:{ptype.lower()}")
            severity = _worse(severity, "medium")

        for keyword in _find_toxic_keywords(text):
            flags.append("toxic_content")
            severity = _worse(severity, "high")
            break  # one flag is enough; details are logged by the caller

        external_category = self._external_moderation(text, "input")
        if external_category:
            flags.append(f"external_moderation:{external_category}")
            severity = _worse(severity, "high")

        hard_block = (
            "toxic_content" in flags
            or any(f.startswith("external_moderation:") for f in flags)
            or (enable_injection and inj.is_injection and inj.severity == "critical")
        )
        return ModerationResult(not hard_block, flags, severity, sanitized)

    def check_output(
        self,
        text: str,
        enable_injection: bool = True,
    ) -> ModerationResult:
        """Moderate an AI response: hallucination markers, leaks, toxicity."""
        if not text:
            return ModerationResult(True, [], "low", None)
        flags: list[str] = []
        severity = "low"
        sanitized: str | None = None

        if _find_hallucination_markers(text):
            flags.append("hallucination_marker")
            # Low confidence marker — informational only; severity stays low.

        pii_types = _scan_pii_types(text)
        if pii_types:
            flags.append("sensitive_data_leak")
            flags.extend(f"pii:{t.lower()}" for t in pii_types)
            severity = _worse(severity, "high")

        if _find_toxic_keywords(text):
            flags.append("inappropriate_content")
            severity = _worse(severity, "high")

        if enable_injection:
            inj = self._detector.detect(text)
            if inj.is_injection:
                flags.append(f"prompt_injection_echo:{inj.severity}")
                severity = _worse(severity, inj.severity)
                sanitized = inj.sanitized_input

        external_category = self._external_moderation(text, "output")
        if external_category:
            flags.append(f"external_moderation:{external_category}")
            severity = _worse(severity, "high")

        hard_block = (
            "inappropriate_content" in flags
            or any(f.startswith("external_moderation:") for f in flags)
            or (enable_injection and inj.is_injection and inj.severity == "critical")
        )
        return ModerationResult(not hard_block, flags, severity, sanitized)

    def _external_moderation(self, text: str, kind: str) -> str | None:
        """外部审核引擎（Batch 7）。未配置返回 None；失败 fail-open 放行。"""
        if not text:
            return None
        try:
            from app.core.policy.moderation_provider import get_moderation_provider

            provider = get_moderation_provider()
        except Exception as e:  # pragma: no cover - 配置读取失败视为无引擎
            logger.warning("Moderation provider lookup failed (fail-open): %s", e)
            return None
        if provider is None:
            return None
        try:
            verdict = provider.check(text, kind)
        except Exception as e:
            logger.warning("External moderation call failed (fail-open): %s", e)
            return None
        if verdict is not None and not verdict.allowed:
            logger.warning("External moderation flagged %s text: category=%s", kind, verdict.category)
            return verdict.category or "external_flagged"
        return None


# ═══════════════════════════════════════════════════════════════════════════
# Feature-flag resolution
# ═══════════════════════════════════════════════════════════════════════════

_FLAG_CONFIG_MAP: dict[str, str] = {
    "guardrails.enabled": "GUARDRAILS_ENABLED",
    "guardrails.prompt_injection.enabled": "GUARDRAILS_PROMPT_INJECTION_ENABLED",
    "guardrails.content_moderation.enabled": "GUARDRAILS_CONTENT_MODERATION_ENABLED",
    "guardrails.pii_masking.enabled": "GUARDRAILS_PII_MASKING_ENABLED",
}

GUARDRAIL_FLAG_KEYS: tuple[str, ...] = tuple(_FLAG_CONFIG_MAP)


def _flag_enabled(flag_key: str, context: dict[str, Any] | None = None) -> bool:
    """Resolve a guardrail feature flag.

    Env-var kill-switch first (hard off), then the Java-managed flag scoped
    by the optional context (``user_id`` / ``knowledge_base_id`` /
    ``tenant_id`` / ``environment``).  Security flags fail closed when the
    backend is unreachable.
    """
    env_attr = _FLAG_CONFIG_MAP.get(flag_key)
    if env_attr and not getattr(config, env_attr, True):
        return False
    ctx = context or {}
    return feature_flags.is_enabled(
        flag_key,
        user_id=ctx.get("user_id"),
        knowledge_base_id=ctx.get("knowledge_base_id"),
        tenant_id=ctx.get("tenant_id"),
        environment=ctx.get("environment"),
    )


def _dedupe(items: list[str]) -> list[str]:
    """Deduplicate while preserving first-occurrence order."""
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


@dataclass(frozen=True)
class GuardResult:
    """Unified pipeline verdict."""

    allowed: bool
    sanitized_content: str
    flags: list[str] = field(default_factory=list)
    blocked_reason: str | None = None
    severity: str = "low"

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "sanitized_content": self.sanitized_content,
            "flags": list(self.flags),
            "blocked_reason": self.blocked_reason,
            "severity": self.severity,
        }


class GuardrailsPipeline:
    """Unified content-safety pipeline.

    ``check_input`` run order: injection detection → PII masking → content
    moderation, with a fast-path block on *critical* injection.  ``check_output``
    applies the same stages to model responses (echoes, leaks, toxicity).

    Context is an optional dict with ``user_id``, ``knowledge_base_id``,
    ``tenant_id``, ``environment``, ``channel`` and ``tool_name`` used for
    feature-flag scoping and logging.  ``flag_resolver`` is injectable for
    tests.
    """

    def __init__(
        self,
        detector: PromptInjectionDetector | None = None,
        masker: PIIMasker | None = None,
        moderator: ContentModerator | None = None,
        flag_resolver: Callable[[str, dict[str, Any] | None], bool] | None = None,
    ):
        self._detector = detector or PromptInjectionDetector()
        self._masker = masker or PIIMasker()
        self._moderator = moderator or ContentModerator(self._detector, self._masker)
        self._flag_resolver = flag_resolver or _flag_enabled
        self._stats: dict[str, int] = {
            "input_checks": 0,
            "output_checks": 0,
            "input_blocked": 0,
            "output_blocked": 0,
            "injections_detected": 0,
            "critical_injections": 0,
            "pii_masked": 0,
            "toxic_blocked": 0,
            "inappropriate_blocked": 0,
        }
        self._stats_lock = threading.Lock()

    # ── Feature-flag helpers ──────────────────────────────────────────

    def _enabled(self, flag_key: str, context: dict[str, Any] | None) -> bool:
        try:
            return bool(self._flag_resolver(flag_key, context))
        except Exception:
            logger.exception("Guardrail flag '%s' resolution failed — fail closed", flag_key)
            return False

    def enabled_flags(self, context: dict[str, Any] | None = None) -> dict[str, bool]:
        """Resolved effective state of every guardrail flag (for status APIs)."""
        return {key: self._enabled(key, context) for key in GUARDRAIL_FLAG_KEYS}

    # ── Statistics ───────────────────────────────────────────────────

    def _bump(self, key: str, count: int = 1) -> None:
        with self._stats_lock:
            self._stats[key] += count

    def stats(self) -> dict[str, Any]:
        """Thread-safe snapshot of counters plus the masker's per-type summary."""
        with self._stats_lock:
            stats = dict(self._stats)
        stats["pii_mask_summary"] = self._masker.summary()
        return stats

    def audit_trail(self, limit: int = 50, include_values: bool = False) -> list[dict[str, Any]]:
        """Delegate to the PII masker's audit trail (metadata only by default)."""
        return self._masker.audit_trail(limit=limit, include_values=include_values)

    # ── Input check ──────────────────────────────────────────────────

    def check_input(
        self,
        user_message: str,
        context: dict[str, Any] | None = None,
    ) -> GuardResult:
        """Check a user message (or tool arguments) before use/execution."""
        text = str(user_message or "")
        flags: list[str] = []
        severity = "low"
        context = context or {}
        self._bump("input_checks")

        if not self._enabled("guardrails.enabled", context):
            return GuardResult(True, text, [], None, "low")

        injection_enabled = self._enabled("guardrails.prompt_injection.enabled", context)

        # 1. Prompt injection detection (fast-path on critical).
        if injection_enabled:
            inj = self._detector.detect(text)
            if inj.is_injection:
                self._bump("injections_detected")
                flags.append(f"prompt_injection:{inj.severity}")
                severity = _worse(severity, inj.severity)
                text = inj.sanitized_input
                if inj.severity == "critical":
                    self._bump("input_blocked", 1)
                    self._bump("critical_injections", 1)
                    logger.warning(
                        "Guardrails: input blocked (critical injection) channel=%s patterns=%s",
                        context.get("channel", "input"), inj.matched_patterns,
                    )
                    flags.extend(f"matched:{name}" for name in inj.matched_patterns)
                    return GuardResult(
                        False, text, _dedupe(flags),
                        "critical_prompt_injection", "critical",
                    )

        # 2. PII masking.
        if self._enabled("guardrails.pii_masking.enabled", context):
            masked, entries = self._masker.mask(text)
            if entries:
                self._bump("pii_masked", len(entries))
                flags.extend(f"pii_masked:{e['placeholder_type'].lower()}" for e in entries)
                severity = _worse(severity, "medium")
                text = masked

        # 3. Content moderation.
        if self._enabled("guardrails.content_moderation.enabled", context):
            mod = self._moderator.check_input(text, enable_injection=injection_enabled)
            flags.extend(mod.flags)
            severity = _worse(severity, mod.severity)
            if mod.sanitized is not None:
                text = mod.sanitized
            if not mod.passed:
                self._bump("input_blocked", 1)
                self._bump("toxic_blocked", 1)
                logger.warning(
                    "Guardrails: input blocked channel=%s flags=%s",
                    context.get("channel", "input"), mod.flags,
                )
                return GuardResult(False, text, _dedupe(flags), "content_moderation_blocked", severity)

        return GuardResult(True, text, _dedupe(flags), None, severity)

    # ── Output check ─────────────────────────────────────────────────

    def check_output(
        self,
        ai_response: str,
        context: dict[str, Any] | None = None,
    ) -> GuardResult:
        """Check a model response before returning it to the caller."""
        text = str(ai_response or "")
        flags: list[str] = []
        severity = "low"
        context = context or {}
        self._bump("output_checks")

        if not self._enabled("guardrails.enabled", context):
            return GuardResult(True, text, [], None, "low")

        injection_enabled = self._enabled("guardrails.prompt_injection.enabled", context)

        # 1. Injection echo detection.
        if injection_enabled:
            inj = self._detector.detect(text)
            if inj.is_injection:
                self._bump("injections_detected")
                flags.append(f"prompt_injection_echo:{inj.severity}")
                severity = _worse(severity, inj.severity)
                text = inj.sanitized_input
                if inj.severity == "critical":
                    self._bump("output_blocked", 1)
                    self._bump("critical_injections", 1)
                    logger.warning(
                        "Guardrails: output blocked (critical injection echo) channel=%s patterns=%s",
                        context.get("channel", "output"), inj.matched_patterns,
                    )
                    return GuardResult(
                        False, text, _dedupe(flags),
                        "critical_prompt_injection_echo", "critical",
                    )

        # 2. PII masking — sensitive data leak prevention.
        if self._enabled("guardrails.pii_masking.enabled", context):
            masked, entries = self._masker.mask(text)
            if entries:
                self._bump("pii_masked", len(entries))
                flags.append("sensitive_data_leak")
                flags.extend(f"pii_masked:{e['placeholder_type'].lower()}" for e in entries)
                severity = _worse(severity, "high")
                text = masked

        # 3. Content moderation — hallucination markers, inappropriate content.
        if self._enabled("guardrails.content_moderation.enabled", context):
            mod = self._moderator.check_output(text, enable_injection=injection_enabled)
            flags.extend(mod.flags)
            severity = _worse(severity, mod.severity)
            if mod.sanitized is not None:
                text = mod.sanitized
            if not mod.passed:
                self._bump("output_blocked", 1)
                self._bump("inappropriate_blocked", 1)
                logger.warning(
                    "Guardrails: output blocked channel=%s flags=%s",
                    context.get("channel", "output"), mod.flags,
                )
                return GuardResult(False, text, _dedupe(flags), "inappropriate_content", severity)

        return GuardResult(True, text, _dedupe(flags), None, severity)


# Module-level singleton — the service-wide pipeline.
guardrails_pipeline = GuardrailsPipeline()


# ── Serialization helper for pipeline callers that need raw text -----------
def serialize_tool_arguments(tool_input: dict[str, Any]) -> str:
    """Serialize tool arguments for the guardrail input check."""
    if not tool_input:
        return ""
    try:
        return json.dumps(tool_input, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(tool_input)


__all__ = [
    "InjectionResult",
    "ModerationResult",
    "GuardResult",
    "PromptInjectionDetector",
    "ContentModerator",
    "PIIMasker",
    "GuardrailsPipeline",
    "guardrails_pipeline",
    "serialize_tool_arguments",
    "SEVERITY_ORDER",
    "INJECTION_PATTERNS",
    "PII_PATTERNS",
    "HALLUCINATION_MARKERS",
    "GUARDRAIL_FLAG_KEYS",
]
