"""
Model Gateway — central LLM routing, failover, circuit breaking and cost
tracking for the HFusionHub Python AI service.

The gateway owns a registry of providers (DeepSeek, Ollama, OpenAI-compatible),
resolves model aliases (e.g. ``"gpt-4"`` → a specific provider+model), routes
each chat request through a configurable fallback chain, and records token
usage/cost into a thread-safe accumulator that can be flushed to the Java
backend.

Graceful degradation: when ``MODEL_GATEWAY_ENABLED=false``, no provider is
usable, or a model cannot be resolved, ``ModelGateway.chat`` delegates to the
legacy ``get_llm()`` path so existing callers keep working unchanged.

Streaming is intentionally not routed through the gateway yet; stream callers
should continue to use ``get_llm()`` directly.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple

import httpx

from app.utils.config import config
from .base import ChatMessage

logger = logging.getLogger(__name__)

__all__ = [
    "ModelGateway",
    "ModelUsage",
    "UsageAccumulator",
    "ProviderConfig",
    "CircuitState",
    "TokenBucketRateLimiter",
    "GatewayResult",
    "GatewayError",
    "get_model_gateway",
]

# DeepSeek publishes pricing per 1M tokens; the gateway stores per-1K values.
#   input:  $0.14 / 1M  ->  $0.00014 / 1K
#   output: $0.28 / 1M  ->  $0.00028 / 1K
_DEEPSEEK_PRICE_PER_1K_INPUT = 0.00014
_DEEPSEEK_PRICE_PER_1K_OUTPUT = 0.00028

# Default alias table: alias -> (provider_name, model). ``None`` model means
# "use the provider's first configured model".
_DEFAULT_ALIASES: Dict[str, Tuple[str, Optional[str]]] = {
    "deepseek": ("deepseek", None),
    "deepseek-chat": ("deepseek", "deepseek-chat"),
    "deepseek-reasoner": ("deepseek", "deepseek-reasoner"),
    "ollama": ("ollama", None),
    "gpt-4": ("openai_compatible", "gpt-4"),
    "gpt-4o": ("openai_compatible", "gpt-4o"),
    "gpt-4o-mini": ("openai_compatible", "gpt-4o-mini"),
}


class GatewayError(RuntimeError):
    """Raised when no provider in the chain produced a response."""


# ---------------------------------------------------------------------------
# Configuration & data models
# ---------------------------------------------------------------------------

@dataclass
class ProviderConfig:
    """Configuration for a single model provider.

    ``price_per_1k_*`` values are USD per 1000 tokens. A local Ollama provider
    defaults to zero cost; cloud pricing can be configured via the factory
    (``MODEL_GATEWAY_ALIASES`` / provider env vars) or overridden in tests.
    """

    name: str
    base_url: str
    api_key: Optional[str] = None
    models: List[str] = field(default_factory=list)
    # Protocol used to talk to the provider: "openai" (OpenAI chat-completions
    # compatible, covers DeepSeek) or "ollama" (native /api/chat).
    provider_type: str = "openai"
    price_per_1k_input: float = 0.0
    price_per_1k_output: float = 0.0
    enabled: bool = True
    rate_limit_tokens_per_min: Optional[int] = None


@dataclass
class CircuitState:
    """Mutable circuit-breaker state for one provider."""

    failures: int = 0
    open_until: float = 0.0  # time.monotonic() deadline; 0.0 = closed
    total_failures: int = 0
    total_successes: int = 0
    last_failure_at: Optional[float] = None  # wall-clock seconds


@dataclass
class ModelUsage:
    """Token usage and cost for a single gateway-routed request."""

    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """JSON-serialisable representation (for the Java backend flush)."""
        return {
            "model": self.model,
            "provider": self.provider,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.cost_usd, 8),
            "latency_ms": round(self.latency_ms, 3),
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class GatewayResult:
    """Result of a gateway-routed chat request."""

    content: str
    model: str
    provider: str
    finish_reason: str = "stop"
    usage: Optional[ModelUsage] = None
    fallback_used: bool = False
    # True when the request was served by the legacy ``get_llm()`` path
    # (gateway disabled, nothing to route with, or model unresolved).
    degraded: bool = False


def calculate_cost(
    provider: ProviderConfig,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Compute USD cost from per-1K pricing."""
    return (
        (prompt_tokens / 1000.0 * provider.price_per_1k_input)
        + (completion_tokens / 1000.0 * provider.price_per_1k_output)
    )


# ---------------------------------------------------------------------------
# Rate limiter & usage accumulator
# ---------------------------------------------------------------------------

class TokenBucketRateLimiter:
    """Token-bucket limiter refilled at capacity per minute (per provider)."""

    def __init__(self, capacity_per_minute: int):
        self._capacity = max(1, capacity_per_minute)
        self._refill_per_second = self._capacity / 60.0
        self._tokens = float(self._capacity)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def try_consume(self, tokens: float) -> bool:
        """Reserve ``tokens`` if available; otherwise deny without borrowing."""
        with self._lock:
            self._refill()
            if self._tokens < tokens:
                return False
            self._tokens -= tokens
            return True

    def available(self) -> float:
        """Current available tokens (after refill)."""
        with self._lock:
            self._refill()
            return round(self._tokens, 2)

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        if elapsed > 0:
            self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_per_second)
            self._last_refill = now


class UsageAccumulator:
    """Thread-safe accumulator for ``ModelUsage`` records.

    Records are kept in a bounded deque (newest last) and also staged in a
    pending list until a ``flush_to_backend`` succeeds. Flushing is best
    effort: failures are logged and the batch is re-staged for the next flush.
    """

    def __init__(self, max_records: int = 10_000):
        self._records: Deque[ModelUsage] = deque(maxlen=max_records)
        self._pending: List[ModelUsage] = []
        self._lock = threading.Lock()

    def record(self, usage: ModelUsage) -> None:
        """Record one request's usage."""
        with self._lock:
            self._records.append(usage)
            self._pending.append(usage)

    def records(self, since: Optional[datetime] = None) -> List[ModelUsage]:
        """Snapshot of recorded usage, optionally filtered by timestamp."""
        with self._lock:
            records = list(self._records)
        if since is not None:
            records = [r for r in records if r.timestamp >= since]
        return records

    def summary(self, since: Optional[datetime] = None) -> Dict[str, Any]:
        """Aggregate usage since ``since``, broken down by model and provider."""
        records = self.records(since)

        by_model: Dict[str, Dict[str, Any]] = {}
        by_provider: Dict[str, Dict[str, Any]] = {}
        totals = {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0,
                  "total_tokens": 0, "cost_usd": 0.0}

        for usage in records:
            totals["requests"] += 1
            totals["prompt_tokens"] += usage.prompt_tokens
            totals["completion_tokens"] += usage.completion_tokens
            totals["total_tokens"] += usage.total_tokens
            totals["cost_usd"] += usage.cost_usd

            for key, bucket in ((usage.model, by_model), (usage.provider, by_provider)):
                entry = bucket.setdefault(key, {
                    "requests": 0, "prompt_tokens": 0, "completion_tokens": 0,
                    "total_tokens": 0, "cost_usd": 0.0,
                })
                entry["requests"] += 1
                entry["prompt_tokens"] += usage.prompt_tokens
                entry["completion_tokens"] += usage.completion_tokens
                entry["total_tokens"] += usage.total_tokens
                entry["cost_usd"] += usage.cost_usd

        return {
            "window_start": since.isoformat() if since is not None else None,
            "total_requests": totals["requests"],
            "total_prompt_tokens": totals["prompt_tokens"],
            "total_completion_tokens": totals["completion_tokens"],
            "total_tokens": totals["total_tokens"],
            "total_cost_usd": round(totals["cost_usd"], 6),
            "by_model": by_model,
            "by_provider": by_provider,
        }

    async def flush_to_backend(self) -> int:
        """POST pending usage to the Java backend; return the flushed count.

        The flush is best effort — a missing internal token, an unreachable
        backend or a failed POST keeps the batch pending for the next flush
        instead of losing it.
        """
        with self._lock:
            batch, self._pending = self._pending, []
        if not batch:
            return 0

        if not config.INTERNAL_API_TOKEN:
            logger.debug("Usage flush skipped: INTERNAL_API_TOKEN not configured")
            with self._lock:
                self._pending = batch + self._pending
            return 0

        url = f"{config.JAVA_BACKEND_URL}/api/internal/model-gateway/usage"
        payload = {
            "flushed_at": datetime.now(timezone.utc).isoformat(),
            "count": len(batch),
            "records": [usage.to_dict() for usage in batch],
        }
        headers = {
            "Content-Type": "application/json",
            "X-Internal-Token": config.INTERNAL_API_TOKEN,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(url, headers=headers, json=payload)
            if response.is_error:
                raise RuntimeError(f"Java backend returned {response.status_code}")
            logger.info("Flushed %d model-usage records to Java backend", len(batch))
            return len(batch)
        except Exception as exc:
            logger.warning("Model-usage flush failed, re-staging %d records: %s", len(batch), exc)
            with self._lock:
                self._pending = batch + self._pending
            return 0


# ---------------------------------------------------------------------------
# ModelGateway
# ---------------------------------------------------------------------------

class ModelGateway:
    """Central model routing and cost-tracking service.

    Maintains the provider registry, resolves aliases, applies circuit
    breakers and per-provider rate limits, then falls through a primary →
    fallback chain until a provider answers.
    """

    def __init__(
        self,
        providers: Optional[Iterable[ProviderConfig]] = None,
        aliases: Optional[Dict[str, Tuple[str, Optional[str]]]] = None,
        enabled: bool = True,
        failover_enabled: bool = True,
        cost_tracking_enabled: bool = True,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
    ):
        self.enabled = enabled
        self._failover_enabled = failover_enabled
        self._cost_tracking_enabled = cost_tracking_enabled
        self._failure_threshold = max(1, failure_threshold)
        self._cooldown_seconds = max(0.0, cooldown_seconds)

        self._providers: Dict[str, ProviderConfig] = {}
        self._circuits: Dict[str, CircuitState] = {}
        self._limiters: Dict[str, Optional[TokenBucketRateLimiter]] = {}
        self._aliases: Dict[str, Tuple[str, Optional[str]]] = dict(aliases or {})
        self._lock = threading.Lock()

        self.usage_accumulator = UsageAccumulator()
        for provider in providers or []:
            self.register_provider(provider)

    # -- registry -----------------------------------------------------------

    def register_provider(self, provider: ProviderConfig) -> None:
        """Register (or replace) a provider with its circuit and rate limiter."""
        self._providers[provider.name] = provider
        self._circuits[provider.name] = CircuitState()
        self._limiters[provider.name] = (
            TokenBucketRateLimiter(provider.rate_limit_tokens_per_min)
            if provider.rate_limit_tokens_per_min
            else None
        )

    def add_alias(self, alias: str, provider: str, model: Optional[str] = None) -> None:
        """Map an alias (e.g. ``"gpt-4"``) to a provider+model pair."""
        self._aliases[alias] = (provider, model)

    @property
    def providers(self) -> Dict[str, ProviderConfig]:
        return dict(self._providers)

    # -- routing ------------------------------------------------------------

    def resolve(self, model: str) -> Tuple[str, str]:
        """Resolve a model reference to a ``(provider_name, model_name)`` pair.

        Accepted forms, in priority order:

        * ``"provider:model"`` — explicit provider targeting
        * a registered provider name — its first configured model
        * a registered alias (e.g. ``"gpt-4"``)
        * an exact model name known to a provider
        * anything else — passed through to the default provider

        Raises:
            GatewayError: nothing usable can be resolved.
        """
        model = (model or "").strip()
        if not model:
            raise GatewayError("Empty model name")

        if ":" in model:
            provider_name, _, explicit_model = model.partition(":")
            provider = self._providers.get(provider_name)
            if provider is not None:
                if not provider.enabled:
                    raise GatewayError(f"Provider {provider_name!r} is disabled")
                return provider_name, explicit_model or self._provider_default_model(provider)

        provider = self._providers.get(model)
        if provider is not None:
            if not provider.enabled:
                raise GatewayError(f"Provider {model!r} is disabled")
            return model, self._provider_default_model(provider)

        alias = self._aliases.get(model)
        if alias is not None:
            provider_name, alias_model = alias
            target = self._providers.get(provider_name)
            if target is None or not target.enabled:
                raise GatewayError(
                    f"Alias {model!r} points to unavailable provider {provider_name!r}"
                )
            return provider_name, alias_model or self._provider_default_model(target)

        for name, candidate in self._providers.items():
            if candidate.enabled and model in candidate.models:
                return name, model

        default = self._default_provider()
        if default is None:
            raise GatewayError(f"No enabled provider available for model {model!r}")
        logger.info("Model %r not registered; passing through to provider %r", model, default.name)
        return default.name, model

    async def chat(
        self,
        model: str,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        fallbacks: Optional[List[str]] = None,
        **kwargs,
    ) -> GatewayResult:
        """Route a chat request through the provider chain.

        Args:
            model: Model name, alias, ``"provider:model"`` or provider name.
            messages: Chat messages to send.
            fallbacks: Optional per-request fallback chain (same reference
                forms as ``model``). Ignored when failover is disabled.
            **kwargs: Extra provider payload parameters (e.g. ``response_format``).

        Returns:
            GatewayResult with content, resolved model/provider and usage.

        Raises:
            GatewayError: every provider in the chain failed or was skipped.
        """
        start = time.perf_counter()

        if not self._can_route():
            return await self._legacy_chat(messages, temperature, max_tokens, kwargs)

        try:
            provider_name, resolved_model = self.resolve(model)
        except GatewayError as exc:
            logger.warning("Model %r could not be resolved; using legacy path: %s", model, exc)
            return await self._legacy_chat(messages, temperature, max_tokens, kwargs)

        errors: List[str] = []
        for candidate, candidate_model in self._build_chain(provider_name, resolved_model, fallbacks):
            if self._circuit_open(candidate):
                errors.append(f"{candidate}: circuit open")
                continue

            limiter = self._limiters.get(candidate)
            estimated_tokens = self._estimate_tokens(messages)
            if limiter is not None and not limiter.try_consume(estimated_tokens):
                errors.append(f"{candidate}: rate limited")
                continue

            provider = self._providers[candidate]
            try:
                content, finish_reason, raw_usage = await self._call_provider(
                    provider, candidate_model, messages, temperature, max_tokens, kwargs
                )
            except Exception as exc:
                self._record_failure(candidate, exc)
                errors.append(f"{candidate}: {exc}")
                continue

            self._record_success(candidate)
            usage = self._build_usage(provider, candidate_model, raw_usage, start)
            if self._cost_tracking_enabled:
                self.usage_accumulator.record(usage)
            return GatewayResult(
                content=content,
                model=candidate_model,
                provider=candidate,
                finish_reason=finish_reason,
                usage=usage,
                fallback_used=candidate != provider_name,
            )

        raise GatewayError(
            "All model providers failed: " + ("; ".join(errors) or "no candidates")
        )

    # -- provider calls -----------------------------------------------------

    async def _call_provider(
        self,
        provider: ProviderConfig,
        model: str,
        messages: List[ChatMessage],
        temperature: float,
        max_tokens: int,
        kwargs: Dict[str, Any],
    ) -> Tuple[str, str, Dict[str, Any]]:
        """Invoke one provider; return ``(content, finish_reason, usage)``."""
        if provider.provider_type == "ollama":
            return await self._call_ollama(provider, model, messages, temperature, max_tokens)
        return await self._call_openai_compatible(
            provider, model, messages, temperature, max_tokens, kwargs
        )

    @staticmethod
    async def _call_openai_compatible(
        provider: ProviderConfig,
        model: str,
        messages: List[ChatMessage],
        temperature: float,
        max_tokens: int,
        kwargs: Dict[str, Any],
    ) -> Tuple[str, str, Dict[str, Any]]:
        """Chat-completions protocol (DeepSeek, OpenAI-compatible endpoints)."""
        headers = {"Content-Type": "application/json"}
        if provider.api_key:
            headers["Authorization"] = f"Bearer {provider.api_key}"

        payload = {
            "model": model,
            "messages": [{"role": msg.role, "content": msg.content} for msg in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{provider.base_url.rstrip('/')}/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            if response.is_error:
                detail = response.text[:1000]
                try:
                    detail = (response.json().get("error", {}).get("message") or detail)[:1000]
                except ValueError:
                    pass
                raise RuntimeError(
                    f"Provider {provider.name} request failed ({response.status_code}): {detail}"
                )
            data = response.json()

        choice = data["choices"][0]
        content = choice["message"].get("content") or ""
        finish_reason = choice.get("finish_reason") or "stop"
        usage = data.get("usage") or {}
        return content, finish_reason, usage

    @staticmethod
    async def _call_ollama(
        provider: ProviderConfig,
        model: str,
        messages: List[ChatMessage],
        temperature: float,
        max_tokens: int,
    ) -> Tuple[str, str, Dict[str, Any]]:
        """Native Ollama ``/api/chat`` protocol."""
        payload = {
            "model": model,
            "messages": [{"role": msg.role, "content": msg.content} for msg in messages],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{provider.base_url.rstrip('/')}/api/chat", json=payload
            )
            if response.is_error:
                raise RuntimeError(
                    f"Provider {provider.name} request failed ({response.status_code}): {response.text[:1000]}"
                )
            data = response.json()

        content = data.get("message", {}).get("content") or ""
        usage = {
            "prompt_tokens": data.get("prompt_eval_count", 0) or 0,
            "completion_tokens": data.get("eval_count", 0) or 0,
        }
        return content, "stop", usage

    # -- circuit breaker & rate limiting ------------------------------------

    def _can_route(self) -> bool:
        """Gateway can take over when enabled and at least one provider is usable."""
        return bool(self.enabled and any(p.enabled for p in self._providers.values()))

    def _circuit_open(self, provider_name: str) -> bool:
        circuit = self._circuits.get(provider_name)
        return bool(circuit and circuit.open_until > time.monotonic())

    def _record_failure(self, provider_name: str, error: Exception) -> None:
        circuit = self._circuits.get(provider_name)
        if circuit is None:
            return
        with self._lock:
            circuit.failures += 1
            circuit.total_failures += 1
            circuit.last_failure_at = time.time()
            if circuit.failures >= self._failure_threshold:
                circuit.open_until = time.monotonic() + self._cooldown_seconds
        if circuit.open_until > 0 and time.monotonic() <= circuit.open_until:
            logger.warning(
                "Circuit breaker OPEN for provider %s (%d/%d failures): %s",
                provider_name, circuit.failures, self._failure_threshold, error,
            )
        else:
            logger.warning(
                "Provider %s failed (%d/%d): %s",
                provider_name, circuit.failures, self._failure_threshold, error,
            )

    def _record_success(self, provider_name: str) -> None:
        circuit = self._circuits.get(provider_name)
        if circuit is None:
            return
        with self._lock:
            circuit.failures = 0
            circuit.open_until = 0.0
            circuit.total_successes += 1

    def _build_chain(
        self,
        primary: str,
        model: str,
        fallbacks: Optional[List[str]],
    ) -> List[Tuple[str, str]]:
        """Primary first, then per-request fallbacks (deduplicated, only enabled)."""
        chain: List[Tuple[str, str]] = []
        seen: set = set()

        def append(provider_name: str, provider_model: str) -> None:
            provider = self._providers.get(provider_name)
            if provider is None or not provider.enabled or provider_name in seen:
                return
            seen.add(provider_name)
            chain.append((provider_name, provider_model))

        append(primary, model)
        if self._failover_enabled and fallbacks:
            for fallback in fallbacks:
                try:
                    fb_provider, fb_model = self.resolve(fallback)
                except GatewayError:
                    continue
                append(fb_provider, fb_model)
        return chain

    # -- usage & helpers ----------------------------------------------------

    def _build_usage(
        self,
        provider: ProviderConfig,
        model: str,
        raw_usage: Dict[str, Any],
        start: float,
    ) -> ModelUsage:
        prompt_tokens = int(raw_usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(raw_usage.get("completion_tokens", 0) or 0)
        total_tokens = int(raw_usage.get("total_tokens", 0) or 0) or (prompt_tokens + completion_tokens)
        return ModelUsage(
            model=model,
            provider=provider.name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=calculate_cost(provider, prompt_tokens, completion_tokens),
            latency_ms=(time.perf_counter() - start) * 1000.0,
        )

    @staticmethod
    def _estimate_tokens(messages: List[ChatMessage]) -> int:
        """Rough pre-flight token estimate (chars / 4) for rate limiting."""
        chars = sum(len(message.content or "") for message in messages)
        return max(1, chars // 4)

    def _default_provider(self) -> Optional[ProviderConfig]:
        for provider in self._providers.values():
            if provider.enabled:
                return provider
        return None

    @staticmethod
    def _provider_default_model(provider: ProviderConfig) -> str:
        return provider.models[0] if provider.models else provider.name

    def available_models(self) -> List[Dict[str, Any]]:
        """Catalogue of routable models with alias, provider and per-1K pricing."""
        seen: set = set()
        models: List[Dict[str, Any]] = []

        def add(alias: Optional[str], provider_name: str, model: str) -> None:
            provider = self._providers.get(provider_name)
            if provider is None or not provider.enabled:
                return
            key = (provider_name, model)
            if key in seen:
                return
            seen.add(key)
            models.append({
                "alias": alias,
                "provider": provider_name,
                "model": model,
                "price_per_1k_input_usd": provider.price_per_1k_input,
                "price_per_1k_output_usd": provider.price_per_1k_output,
            })

        for alias, (provider_name, alias_model) in self._aliases.items():
            provider = self._providers.get(provider_name)
            add(alias, provider_name, alias_model or self._provider_default_model(provider)) \
                if provider is not None else None

        for name, provider in self._providers.items():
            for model in provider.models:
                add(None, name, model)

        return models

    # -- health -------------------------------------------------------------

    async def warmup(self) -> None:
        """Probe all enabled providers once at startup (best effort).

        Called from the app startup event to pre-populate availability
        knowledge so the first request does not pay the probe cost. Never
        raises — a dead provider is simply recorded as unavailable.
        """
        try:
            results = await self._probe_all()
            available = [name for name, ok in results.items() if ok]
            unavailable = [name for name, ok in results.items() if not ok]
            logger.info(
                "Model gateway warmup: %d/%d providers available%s",
                len(available), len(results),
                f" ({', '.join(unavailable)} unavailable)" if unavailable else "",
            )
        except Exception as exc:
            logger.warning("Model gateway warmup failed: %s", exc)

    async def health(self) -> Dict[str, Any]:
        """Per-provider operational state (never exposes URLs or keys).

        Circuit states: ``closed`` (healthy), ``open`` (temporarily disabled
        by repeated failures), ``half_open`` (cooldown elapsed, trial allowed).
        ``available`` probes each enabled provider concurrently with a short
        timeout, so a status page is not blocked by a dead endpoint.
        """
        now = time.monotonic()
        probe_results = await self._probe_all()

        payload: Dict[str, Any] = {
            "gateway_enabled": self.enabled,
            "failover_enabled": self._failover_enabled,
            "cost_tracking_enabled": self._cost_tracking_enabled,
            "providers": [],
        }
        for name, provider in self._providers.items():
            circuit = self._circuits.get(name)
            state, cooldown_remaining = "closed", None
            if circuit is not None:
                if circuit.open_until > now:
                    state = "open"
                    cooldown_remaining = round(circuit.open_until - now, 2)
                elif circuit.open_until > 0:
                    state = "half_open"

            limiter = self._limiters.get(name)
            payload["providers"].append({
                "provider": name,
                "type": provider.provider_type,
                "enabled": provider.enabled,
                "available": probe_results.get(name, False),
                "circuit": state,
                "failure_count": circuit.failures if circuit else 0,
                "total_failures": circuit.total_failures if circuit else 0,
                "total_successes": circuit.total_successes if circuit else 0,
                "cooldown_remaining_seconds": cooldown_remaining,
                "rate_limit_tokens_remaining": (
                    limiter.available() if limiter is not None and provider.enabled else None
                ),
                "model_count": len(provider.models),
            })
        return payload

    async def _probe_all(self) -> Dict[str, bool]:
        async def probe_one(provider: ProviderConfig) -> Tuple[str, bool]:
            if not provider.enabled:
                return provider.name, False
            try:
                async with httpx.AsyncClient(timeout=1.5) as client:
                    if provider.provider_type == "ollama":
                        response = await client.get(f"{provider.base_url.rstrip('/')}/api/tags")
                    else:
                        headers = {"Authorization": f"Bearer {provider.api_key}"} \
                            if provider.api_key else {}
                        response = await client.get(
                            f"{provider.base_url.rstrip('/')}/v1/models", headers=headers
                        )
                    return provider.name, response.status_code == 200
            except Exception:
                return provider.name, False

        results = await asyncio.gather(*(probe_one(p) for p in self._providers.values()))
        return dict(results)

    # -- legacy fallback ----------------------------------------------------

    async def _legacy_chat(
        self,
        messages: List[ChatMessage],
        temperature: float,
        max_tokens: int,
        kwargs: Dict[str, Any],
    ) -> GatewayResult:
        """Graceful degradation: delegate to the existing ``get_llm()`` path."""
        from . import get_llm

        llm = get_llm()
        response = await llm.chat(messages=messages, temperature=temperature, max_tokens=max_tokens, **kwargs)
        return GatewayResult(
            content=response.content,
            model=response.model,
            provider="legacy",
            finish_reason=response.finish_reason,
            degraded=True,
        )


# ---------------------------------------------------------------------------
# Environment helpers & singleton factory
# ---------------------------------------------------------------------------

def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        logger.warning("Env var %s is not an integer; using default %s", name, default)
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        logger.warning("Env var %s is not a number; using default %s", name, default)
        return default


def _load_alias_overrides() -> Dict[str, Tuple[str, Optional[str]]]:
    """Optional ``MODEL_GATEWAY_ALIASES`` JSON: {"alias": "provider:model"}."""
    raw = os.getenv("MODEL_GATEWAY_ALIASES", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("MODEL_GATEWAY_ALIASES is not valid JSON; ignoring")
        return {}

    overrides: Dict[str, Tuple[str, Optional[str]]] = {}
    for alias, target in parsed.items():
        if not isinstance(target, str):
            logger.warning("MODEL_GATEWAY_ALIASES entry %r is not a string; ignoring", alias)
            continue
        provider_name, _, model = target.partition(":")
        overrides[str(alias)] = (provider_name, model or None)
    return overrides


def _build_gateway_from_config() -> ModelGateway:
    """Assemble the default gateway from env/config (see module docstring)."""
    gateway = ModelGateway(
        enabled=_env_bool("MODEL_GATEWAY_ENABLED", default=True),
        failover_enabled=_env_bool("MODEL_FAILOVER_ENABLED", default=True),
        cost_tracking_enabled=_env_bool("MODEL_COST_TRACKING_ENABLED", default=True),
        failure_threshold=_env_int("MODEL_GATEWAY_FAILURE_THRESHOLD", 3),
        cooldown_seconds=_env_float("MODEL_GATEWAY_COOLDOWN_SECONDS", 30.0),
    )

    default_rate = _env_int("MODEL_GATEWAY_RATE_LIMIT_PER_MIN", 60_000)

    # DeepSeek — cloud provider; only usable when an API key is configured.
    gateway.register_provider(ProviderConfig(
        name="deepseek",
        provider_type="openai",
        base_url=config.DEEPSEEK_BASE_URL,
        api_key=config.DEEPSEEK_API_KEY or None,
        models=[config.DEEPSEEK_MODEL, "deepseek-chat", "deepseek-reasoner"],
        price_per_1k_input=_DEEPSEEK_PRICE_PER_1K_INPUT,
        price_per_1k_output=_DEEPSEEK_PRICE_PER_1K_OUTPUT,
        enabled=bool(config.DEEPSEEK_API_KEY),
        rate_limit_tokens_per_min=default_rate,
    ))

    # Ollama — local; free (or configurable) by default.
    gateway.register_provider(ProviderConfig(
        name="ollama",
        provider_type="ollama",
        base_url=config.OLLAMA_BASE_URL,
        models=[config.OLLAMA_MODEL],
        price_per_1k_input=float(os.getenv("OLLAMA_PRICE_INPUT_PER_1K", "0.0")),
        price_per_1k_output=float(os.getenv("OLLAMA_PRICE_OUTPUT_PER_1K", "0.0")),
        enabled=True,
        rate_limit_tokens_per_min=_env_int("OLLAMA_RATE_LIMIT_PER_MIN", default_rate),
    ))

    # OpenAI-compatible — opt-in via env (base URL + API key required).
    openai_base = os.getenv("OPENAI_COMPATIBLE_BASE_URL", "").strip()
    openai_api_key = os.getenv("OPENAI_COMPATIBLE_API_KEY", "").strip()
    openai_models = [
        item.strip()
        for item in os.getenv("OPENAI_COMPATIBLE_MODELS", "gpt-4,gpt-4o,gpt-4o-mini").split(",")
        if item.strip()
    ]
    gateway.register_provider(ProviderConfig(
        name="openai_compatible",
        provider_type="openai",
        base_url=openai_base.rstrip("/") or "https://api.openai.com/v1",
        api_key=openai_api_key or None,
        models=openai_models,
        price_per_1k_input=_env_float("OPENAI_COMPATIBLE_PRICE_INPUT_PER_1K", 0.0005),
        price_per_1k_output=_env_float("OPENAI_COMPATIBLE_PRICE_OUTPUT_PER_1K", 0.0015),
        enabled=bool(openai_base and openai_api_key),
        rate_limit_tokens_per_min=_env_int("OPENAI_COMPATIBLE_RATE_LIMIT_PER_MIN", default_rate),
    ))

    aliases = dict(_DEFAULT_ALIASES)
    aliases.update(_load_alias_overrides())
    for alias, (provider_name, alias_model) in aliases.items():
        gateway.add_alias(alias, provider_name, alias_model)

    return gateway


_gateway_instance: Optional[ModelGateway] = None
_gateway_lock = threading.Lock()


def get_model_gateway() -> ModelGateway:
    """Return the process-wide ModelGateway singleton (built lazily)."""
    global _gateway_instance
    with _gateway_lock:
        if _gateway_instance is None:
            _gateway_instance = _build_gateway_from_config()
        return _gateway_instance
