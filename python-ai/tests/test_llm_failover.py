import pytest

from app.core.llm.base import BaseLLM, ChatMessage, LLMResponse
from app.core.llm.failover_llm import FailoverLLM
import app.core.llm as llm_module


class _FakeLLM(BaseLLM):
    def __init__(self, *, response=None, error=None, stream=None):
        self.response = response or LLMResponse(content="ok", model="fake")
        self.error = error
        self.stream = stream if stream is not None else ["ok"]
        self.chat_calls = 0
        self.stream_calls = 0

    async def chat(self, messages, temperature=0.7, max_tokens=2048, **kwargs):
        self.chat_calls += 1
        if self.error:
            raise self.error
        return self.response

    async def chat_stream(self, messages, temperature=0.7, max_tokens=2048, **kwargs):
        self.stream_calls += 1
        for item in self.stream:
            if isinstance(item, Exception):
                raise item
            yield item

    def is_available(self):
        return True


@pytest.mark.asyncio
async def test_fails_over_before_any_response_content_is_emitted():
    primary = _FakeLLM(error=RuntimeError("primary unavailable"))
    fallback = _FakeLLM(response=LLMResponse(content="fallback", model="local"))

    result = await FailoverLLM([primary, fallback]).chat([ChatMessage("user", "hello")])

    assert result.content == "fallback"
    assert primary.chat_calls == 1
    assert fallback.chat_calls == 1


@pytest.mark.asyncio
async def test_stream_fails_over_only_before_the_first_chunk():
    primary = _FakeLLM(stream=[RuntimeError("connection refused")])
    fallback = _FakeLLM(stream=["fallback stream"])
    chunks = [chunk async for chunk in FailoverLLM([primary, fallback]).chat_stream([ChatMessage("user", "hello")])]

    assert chunks == ["fallback stream"]
    assert fallback.stream_calls == 1


@pytest.mark.asyncio
async def test_stream_never_mixes_providers_after_content_is_visible():
    primary = _FakeLLM(stream=["primary ", RuntimeError("broken mid-stream")])
    fallback = _FakeLLM(stream=["fallback"])
    stream = FailoverLLM([primary, fallback]).chat_stream([ChatMessage("user", "hello")])

    assert await anext(stream) == "primary "
    with pytest.raises(RuntimeError, match="after response content"):
        await anext(stream)
    assert fallback.stream_calls == 0


def test_ollama_probe_caches_failures_and_uses_bounded_timeout(monkeypatch):
    llm_module._ollama_probe_cache.clear()
    calls = []

    def unavailable(url, *, timeout):
        calls.append((url, timeout))
        raise OSError("connection refused")

    monkeypatch.setattr("httpx.get", unavailable)

    assert llm_module._is_ollama_available("http://ollama.test/") is False
    assert llm_module._is_ollama_available("http://ollama.test") is False
    assert calls == [
        ("http://ollama.test/api/tags", llm_module._OLLAMA_PROBE_TIMEOUT_SECONDS)
    ]


def test_ollama_probe_cache_is_scoped_to_the_endpoint(monkeypatch):
    llm_module._ollama_probe_cache.clear()
    calls = []

    class _Response:
        status_code = 200

    def available(url, *, timeout):
        calls.append((url, timeout))
        return _Response()

    monkeypatch.setattr("httpx.get", available)

    assert llm_module._is_ollama_available("http://one.test") is True
    assert llm_module._is_ollama_available("http://two.test") is True
    assert [url for url, _ in calls] == [
        "http://one.test/api/tags", "http://two.test/api/tags",
    ]
