"""ModelGateway streaming-path governance tests.

Covers the parts of ``ModelGateway.chat_stream`` that make streaming subject to
the same controls as ``chat``: the exact-match response cache (no re-bill on an
identical prompt), rate limiting, circuit breaking, cost tracking, failover
before the first chunk, graceful legacy degradation (and the no-recursion
guarantee on resolve failure), plus the ``GatewayLLM`` facade and the
``get_llm()`` wiring that routes agent streaming through the gateway.

The gateway talks to providers over HTTP via the shared client, which has no
transport injection point, so provider I/O is replaced by monkeypatching
``gateway._stream_provider`` — the governance logic under test is exactly what
surrounds that call.
"""

import os

import pytest

from app.core.llm.base import ChatMessage, LLMResponse
from app.core.llm.gateway_llm import GatewayLLM
from app.core.llm.model_gateway import (
    GatewayError,
    GatewayResult,
    ModelGateway,
    ModelUsage,
    ProviderConfig,
)
from app.utils.config import config

from app.core.llm import deepseek_llm as ds_mod
from app.core.llm import get_llm


def _messages(*texts: str) -> list:
    return [ChatMessage(role="user", content=text) for text in texts]


def _gateway(*providers, enabled=True, **kwargs) -> ModelGateway:
    return ModelGateway(providers=providers, enabled=enabled, **kwargs)


def _provider(name: str, models=("m1",), rate_limit=None) -> ProviderConfig:
    return ProviderConfig(
        name=name,
        base_url="http://provider.invalid",
        models=list(models),
        enabled=True,
        rate_limit_tokens_per_min=rate_limit,
    )


@pytest.fixture(autouse=True)
def _isolate_cache(monkeypatch):
    """Deterministic cache + gateway behavior for every test."""
    monkeypatch.setattr(config, "LLM_RESPONSE_CACHE_TTL_SECONDS", 300)
    ds_mod._response_cache.clear()
    yield
    ds_mod._response_cache.clear()


# -- streaming governance ----------------------------------------------------

@pytest.mark.asyncio
async def test_chat_stream_records_usage_and_populates_cache(monkeypatch):
    """A successful stream records usage and is served from cache afterwards."""
    gw = _gateway(_provider("p1"))

    async def fake_stream(provider, model, messages, temperature, max_tokens, kwargs):
        yield "hello "
        yield "world"

    monkeypatch.setattr(gw, "_stream_provider", fake_stream)

    async def collect(model, *texts):
        return [c async for c in gw.chat_stream(model, _messages(*texts))]

    assert await collect("p1", "q1") == ["hello ", "world"]

    records = gw.usage_accumulator.records()
    assert len(records) == 1
    usage = records[0]
    assert usage.provider == "p1"
    assert usage.model == "m1"
    assert usage.total_tokens == usage.prompt_tokens + usage.completion_tokens
    assert usage.total_tokens > 0

    # Identical prompt → cache hit: no re-bill, no provider call, one chunk.
    assert await collect("p1", "q1") == ["hello world"]
    assert len(gw.usage_accumulator.records()) == 1
    assert gw._circuits["p1"].total_successes == 1


@pytest.mark.asyncio
async def test_chat_stream_cache_key_isolates_by_messages(monkeypatch):
    """Different prompts must not collide in the cache."""
    gw = _gateway(_provider("p1"))
    calls = []

    async def fake_stream(provider, model, messages, temperature, max_tokens, kwargs):
        calls.append(messages[0].content)
        yield f"answer:{messages[0].content}"

    monkeypatch.setattr(gw, "_stream_provider", fake_stream)

    async def collect(model, *texts):
        return "".join([c async for c in gw.chat_stream(model, _messages(*texts))])

    assert await collect("p1", "q1") == "answer:q1"
    assert await collect("p1", "q2") == "answer:q2"
    assert await collect("p1", "q1") == "answer:q1"  # cached
    assert calls == ["q1", "q2"]


@pytest.mark.asyncio
async def test_chat_stream_rate_limit_denies_without_usage(monkeypatch):
    """An exhausted rate limit skips the provider: no stream, no usage record."""
    # Cache disabled so the second identical call actually reaches the limiter
    # instead of being served from the response cache.
    monkeypatch.setattr(config, "LLM_RESPONSE_CACHE_TTL_SECONDS", 0)
    gw = _gateway(_provider("p1", rate_limit=1))

    async def fake_stream(provider, model, messages, temperature, max_tokens, kwargs):
        yield "never"  # pragma: no cover — must not be reached

    monkeypatch.setattr(gw, "_stream_provider", fake_stream)

    async def drain(model, *texts):
        return [c async for c in gw.chat_stream(model, _messages(*texts))]

    # First call consumes the single token; short messages estimate ≥ 1 token.
    assert await drain("p1", "hi") == ["never"]

    with pytest.raises(GatewayError, match="rate limited"):
        await drain("p1", "hi")

    # Only the first (successful) call recorded usage; the denied one did not.
    assert len(gw.usage_accumulator.records()) == 1


@pytest.mark.asyncio
async def test_chat_stream_circuit_open_skips_provider(monkeypatch):
    """An open circuit breaker blocks the provider without a call."""
    gw = _gateway(_provider("p1"), failure_threshold=1, cooldown_seconds=60)

    async def fake_stream(provider, model, messages, temperature, max_tokens, kwargs):
        yield "never"  # pragma: no cover

    monkeypatch.setattr(gw, "_stream_provider", fake_stream)

    gw._record_failure("p1", RuntimeError("boom"))
    assert gw._circuit_open("p1")

    with pytest.raises(GatewayError, match="circuit open"):
        async for _ in gw.chat_stream("p1", _messages("hi")):
            pass

    assert gw.usage_accumulator.records() == []


@pytest.mark.asyncio
async def test_chat_stream_fails_over_before_first_chunk(monkeypatch):
    """Primary failure before the first chunk falls through to the fallback."""
    gw = _gateway(_provider("p1"), _provider("p2"))

    async def fake_stream(provider, model, messages, temperature, max_tokens, kwargs):
        if provider.name == "p1":
            raise RuntimeError("p1 upstream down")
        yield "fallback answer"

    monkeypatch.setattr(gw, "_stream_provider", fake_stream)

    chunks = [c async for c in gw.chat_stream("p1", _messages("q"), fallbacks=["p2"])]
    assert chunks == ["fallback answer"]

    assert gw._circuits["p1"].total_failures == 1
    usage = gw.usage_accumulator.records()
    assert len(usage) == 1 and usage[0].provider == "p2"


@pytest.mark.asyncio
async def test_chat_stream_error_after_first_chunk_raises(monkeypatch):
    """Once content flows the stream cannot restart — the error is surfaced."""
    gw = _gateway(_provider("p1"))

    async def fake_stream(provider, model, messages, temperature, max_tokens, kwargs):
        yield "partial"
        raise RuntimeError("mid-stream failure")

    monkeypatch.setattr(gw, "_stream_provider", fake_stream)

    collected = []
    with pytest.raises(RuntimeError, match="after first chunk"):
        async for chunk in gw.chat_stream("p1", _messages("q")):
            collected.append(chunk)
    assert collected == ["partial"]
    assert gw.usage_accumulator.records() == []
    assert gw._circuits["p1"].total_failures == 1


# -- fail-fast（旧链退役后不再静默降级）--------------------------------------

@pytest.mark.asyncio
async def test_chat_stream_raises_when_gateway_disabled():
    """Gateway disabled → clear GatewayError instead of a silent legacy fallback."""
    import pytest as _pytest
    from app.core.llm.model_gateway import GatewayError

    gw = _gateway(_provider("p1"), enabled=False)
    with _pytest.raises(GatewayError, match="not routable"):
        _ = [c async for c in gw.chat_stream("p1", _messages("q"))]


@pytest.mark.asyncio
async def test_chat_stream_resolve_failure_raises(monkeypatch):
    """A model the gateway cannot resolve surfaces GatewayError to the caller."""
    import pytest as _pytest
    from app.core.llm.model_gateway import GatewayError

    gw = _gateway(_provider("p1"))

    # Empty model name makes resolve() raise GatewayError.
    with _pytest.raises(GatewayError):
        _ = [c async for c in gw.chat_stream("", _messages("q"))]


# -- GatewayLLM facade --------------------------------------------------------

@pytest.mark.asyncio
async def test_gateway_llm_chat_delegates(monkeypatch):
    gw = _gateway(_provider("p1"))
    usage = ModelUsage(model="m1", provider="p1", total_tokens=42)

    async def fake_chat(model, messages, temperature=0.7, max_tokens=2048, **kwargs):
        return GatewayResult(content="answer", model="m1", provider="p1", usage=usage)

    monkeypatch.setattr(gw, "chat", fake_chat)

    llm = GatewayLLM(gw, model="p1")
    result = await llm.chat(_messages("q"))
    assert isinstance(result, LLMResponse)
    assert result.content == "answer"
    assert result.token_count == 42


@pytest.mark.asyncio
async def test_gateway_llm_stream_delegates(monkeypatch):
    gw = _gateway(_provider("p1"))

    async def fake_stream(model, messages, temperature=0.7, max_tokens=2048, **kwargs):
        yield "a"
        yield "b"

    monkeypatch.setattr(gw, "chat_stream", fake_stream)

    # An explicitly pinned model is used verbatim; an unpinned one resolves to
    # the gateway default (covered by test_gateway_llm_default_model_resolves).
    llm = GatewayLLM(gw, model="p1")
    assert [c async for c in llm.chat_stream(_messages("q"))] == ["a", "b"]
    assert llm.model == "p1"
    assert llm.is_available() is True


@pytest.mark.asyncio
async def test_gateway_llm_default_model_resolves(monkeypatch):
    gw = _gateway(_provider("p1", models=("m1",)))
    llm = GatewayLLM(gw)
    assert llm.model == "m1"


# -- get_llm() wiring ---------------------------------------------------------

def _routable_gateway():
    return _gateway(_provider("p1"))


def test_get_llm_returns_gatewayllm_when_enabled_and_routable(monkeypatch):
    monkeypatch.setenv("MODEL_GATEWAY_STREAM_ENABLED", "true")
    monkeypatch.setenv("LLM_ALLOW_MOCK", "false")
    from app.core.llm import model_gateway as mg_mod

    monkeypatch.setattr(mg_mod, "get_model_gateway", lambda: _routable_gateway())

    llm = get_llm()
    assert isinstance(llm, GatewayLLM)


def test_get_llm_returns_gateway_when_routable(monkeypatch):
    """ModelGateway 是唯一链：可路由时 get_llm 一律返回 GatewayLLM。"""
    monkeypatch.setenv("LLM_ALLOW_MOCK", "false")
    from app.core.llm import model_gateway as mg_mod

    monkeypatch.setattr(mg_mod, "get_model_gateway", lambda: _routable_gateway())

    llm = get_llm()
    assert isinstance(llm, GatewayLLM)


def test_get_llm_raises_when_gateway_cannot_route(monkeypatch):
    """Gateway 不可路由（无任何启用的 provider）→ 明确报错而非静默降级。"""
    import pytest as _pytest

    monkeypatch.setenv("LLM_ALLOW_MOCK", "false")
    from app.core.llm import model_gateway as mg_mod

    dead = _gateway(_provider("p1"), enabled=False)
    monkeypatch.setattr(mg_mod, "get_model_gateway", lambda: dead)

    with _pytest.raises(RuntimeError, match="No LLM provider available"):
        get_llm()


def test_get_llm_mock_still_wins_over_gateway(monkeypatch):
    monkeypatch.setenv("LLM_ALLOW_MOCK", "true")
    from app.core.llm import model_gateway as mg_mod
    from app.core.llm.mock_llm import MockLLM

    monkeypatch.setattr(mg_mod, "get_model_gateway", lambda: _routable_gateway())

    llm = get_llm()
    assert isinstance(llm, MockLLM)
