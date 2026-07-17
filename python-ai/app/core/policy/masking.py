"""Field-level sensitive-value masking.

Prevents raw sensitive tool input from leaking into approval summaries,
decision logs, or trace output.  Applied at two layers:

  * :func:`mask_sensitive_fields` — scrub a pre-serialised arguments dict
    (used to build ``ApprovalRequest.arguments_summary`` and audit records).
  * :func:`mask_value` — mask a single value.

Masking is recog on well-known field names (keys) and respected JSON-ish
shapes.  The original full input is never surfaced; masked tokens are shown
instead (``[MASKED]`` / ``***``).
"""

from __future__ import annotations

import json
from typing import Any

# Field-name keys considered sensitive; matched case-insensitively and as a
# suffix to tolerate prefixes (e.g. ``business_password``).
_SENSITIVE_KEYS = frozenset({
    "password",
    "password_hash",
    "passwd",
    "secret",
    "secret_key",
    "api_key",
    "apikey",
    "access_key",
    "access_token",
    "refresh_token",
    "auth_token",
    "session_token",
    "client_secret",
    "private_key",
    "authorization",
    "mfa_token",
    "otp",
    "code",
    "pin",
    "id_card",
    "id_number",
    "national_id",
    "passport",
    "credit_card",
    "card_number",
    "cvv",
    "ssn",
    "bank_account",
    "social_security",
    "health",
    "address",
    "phone",
    "phone_number",
    "mobile",
    "email",
    "ip_address",
    "latitude",
    "longitude",
    "location",
})

# Exact-key matches that must never be stored/emitted if they carry secrets.
_ALWAYS_MASK_KEY = frozenset({
    "password",
    "api_key",
    "token",
    "execution_token",
    "private_key",
})

MASKED = "***"

_MAX_DEPTH = 6


def _is_sensitive_key(key: str) -> bool:
    k = (key or "").strip().lower()
    if k in _ALWAYS_MASK_KEY:
        return True
    # Whole-key match, or suffix match against a sensitive token.
    for token in _SENSITIVE_KEYS:
        if k == token or k.endswith("_" + token) or k.startswith(token + "_"):
            return True
    return False


def mask_value(value: Any) -> str:
    """Mask a single sensitive value."""
    return MASKED


def mask_sensitive_fields(
    data: dict[str, Any],
    *,
    depth: int = 0,
) -> dict[str, Any]:
    """Return a deep copy of *data* with sensitive fields masked.

    Recurses into nested dicts / lists up to a bounded depth.  Leaf values
    whose key is sensitive become ``***``.
    """
    if depth > _MAX_DEPTH or not isinstance(data, dict):
        try:
            json.dumps(data, ensure_ascii=False)
            return dict(data) if isinstance(data, dict) else data
        except (TypeError, ValueError):
            return data
    out: dict[str, Any] = {}
    for key, value in data.items():
        if _is_sensitive_key(str(key)):
            out[key] = mask_value(value)
        elif isinstance(value, dict):
            out[key] = mask_sensitive_fields(value, depth=depth + 1)
        elif isinstance(value, list):
            out[key] = [_mask_item(i, depth + 1) for i in value]
        else:
            out[key] = value
    return out


def _mask_item(item: Any, depth: int) -> Any:
    if isinstance(item, dict):
        return mask_sensitive_fields(item, depth=depth)
    if isinstance(item, list):
        return [_mask_item(i, depth + 1) for i in item]
    return item


def build_arguments_summary(tool_input: dict[str, Any], *, max_chars: int = 120) -> str:
    """Produce a masked, truncated summary string for approval audit.

    Sensitive keys are masked; the result is truncated to ``max_chars``.
    """
    masked = mask_sensitive_fields(tool_input or {})
    try:
        summary = json.dumps(masked, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        summary = str(masked)
    if len(summary) > max_chars:
        summary = summary[: max_chars - 1] + "…"
    return summary
