"""
Model Gateway API — provider health, usage summary and model catalogue.

Operational endpoints for the AI control plane:

* ``GET /api/gateway/status`` — provider health, circuit breaker states,
  rate-limiter levels (probes enabled providers with a short timeout).
* ``GET /api/gateway/usage`` — recent token usage and cost summary.
* ``GET /api/gateway/models`` — routable models with alias and per-1K pricing.

The endpoints deliberately never expose API keys, provider URLs or prompt
content. They are registered behind the internal-token dependency in
``app/main.py`` alongside the metrics and runtime routers.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter

from app.core.llm.model_gateway import get_model_gateway

router = APIRouter(prefix="/api/gateway", tags=["gateway"])


@router.get("/status")
async def gateway_status() -> dict[str, Any]:
    """Provider health, circuit breaker states and rate limiter levels."""
    return await get_model_gateway().health()


@router.get("/usage")
async def gateway_usage(hours: float = 1.0) -> dict[str, Any]:
    """Recent token usage and cost summary.

    Args:
        hours: Look-back window; clamped to [0.1, 720].
    """
    hours = min(max(hours, 0.1), 720.0)
    since = datetime.now(UTC) - timedelta(hours=hours)
    return get_model_gateway().usage_accumulator.summary(since=since)


@router.get("/models")
async def gateway_models() -> dict[str, Any]:
    """Available models with alias, provider and per-1K pricing."""
    gateway = get_model_gateway()
    return {
        "enabled": gateway.enabled,
        "models": gateway.available_models(),
    }
