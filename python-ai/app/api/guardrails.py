"""Content safety guardrails — diagnostics API for the AI control plane.

Exposes the unified :class:`GuardrailsPipeline` to authenticated internal
callers (Java backend).  The ``check-*`` endpoints are *diagnostic*: they
return the verdict and sanitized content so the caller can decide how to
enforce it; they never raise 4xx on a block.  Enforcement happens at the
service choke points (ToolRegistry input check, chat response output check)
via the policy engine.

This router is registered with ``internal_dependencies`` in ``app.main`` —
the internal token is required for every endpoint.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.policy.guardrails import GuardResult, guardrails_pipeline
from app.utils.config import config

router = APIRouter(tags=["guardrails"])


# ── Request / response models ─────────────────────────────────────────────

class GuardrailContext(BaseModel):
    """Optional scoping for feature-flag evaluation and audit logging."""

    user_id: int | None = Field(None, ge=1)
    knowledge_base_id: int | None = Field(None, ge=1)
    tenant_id: int | None = Field(None, ge=1)
    environment: str | None = Field(None, max_length=32)
    channel: str | None = Field(None, pattern="^(chat|tool|input|output)$")
    tool_name: str | None = Field(None, max_length=128)


class GuardCheckRequest(BaseModel):
    """Content to check, with optional flag-scoping context."""

    content: str = Field(..., min_length=1, max_length=20000)
    context: GuardrailContext | None = Field(
        None, description="user_id / knowledge_base_id / environment scoping"
    )


class GuardCheckResponse(BaseModel):
    """Verdict for a single content-safety check."""

    allowed: bool = Field(..., description="True when the content may proceed")
    sanitized_content: str = Field(
        ..., description="Content with dangerous parts removed / PII masked"
    )
    flags: list[str] = Field(
        default_factory=list, description="Findings, e.g. prompt_injection:high, pii:email"
    )
    blocked_reason: str | None = Field(
        None, description="Set when allowed=False (critical_prompt_injection, …)"
    )
    severity: str = Field("low", description="low | medium | high | critical")
    checked_at: str = Field(..., description="ISO-8601 UTC timestamp")


# ── Helpers ───────────────────────────────────────────────────────────────

def _to_response(result: GuardResult) -> dict[str, Any]:
    return {
        "allowed": result.allowed,
        "sanitized_content": result.sanitized_content,
        "flags": list(result.flags),
        "blocked_reason": result.blocked_reason,
        "severity": result.severity,
        "checked_at": datetime.now(UTC).isoformat(),
    }


def _context_dict(context: GuardrailContext | None) -> dict[str, Any] | None:
    if context is None:
        return None
    return {
        k: v for k, v in context.model_dump().items()
        if v is not None
    }


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.post("/api/guardrails/check-input", response_model=GuardCheckResponse)
async def check_input(request: GuardCheckRequest) -> dict[str, Any]:
    """Check a user message for safety (prompt injection, PII, toxic content).

    Diagnostic only — returns the verdict in the body; enforcement happens at
    the ToolRegistry / chat choke points.
    """
    result = guardrails_pipeline.check_input(
        request.content, context=_context_dict(request.context)
    )
    return _to_response(result)


@router.post("/api/guardrails/check-output", response_model=GuardCheckResponse)
async def check_output(request: GuardCheckRequest) -> dict[str, Any]:
    """Check an AI response before returning it (echo, leaks, toxicity).

    Diagnostic only — returns the verdict in the body; the chat layer
    substitutes a refusal when ``allowed`` is False.
    """
    result = guardrails_pipeline.check_output(
        request.content, context=_context_dict(request.context)
    )
    return _to_response(result)


@router.get("/api/guardrails/status")
async def guardrails_status() -> dict[str, Any]:
    """Current guardrail configuration, effective flag state, and statistics.

    Deliberately exposes counts and audit *metadata* only — masked values
    never leave the in-process vault.
    """
    return {
        "enabled": guardrails_pipeline.enabled_flags(),
        "config": {
            "GUARDRAILS_ENABLED": config.GUARDRAILS_ENABLED,
            "GUARDRAILS_PROMPT_INJECTION_ENABLED": config.GUARDRAILS_PROMPT_INJECTION_ENABLED,
            "GUARDRAILS_CONTENT_MODERATION_ENABLED": config.GUARDRAILS_CONTENT_MODERATION_ENABLED,
            "GUARDRAILS_PII_MASKING_ENABLED": config.GUARDRAILS_PII_MASKING_ENABLED,
        },
        "statistics": guardrails_pipeline.stats(),
        "masking_audit_recent": guardrails_pipeline.audit_trail(limit=20),
        "generated_at": datetime.now(UTC).isoformat(),
    }
