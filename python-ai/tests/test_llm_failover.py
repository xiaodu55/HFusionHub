import pytest

from app.core.llm.base import BaseLLM, ChatMessage, LLMResponse
from app.core.llm.failover_llm import FailoverLLM
from app.core.llm.mock_llm import MockLLM
import app.core.llm as llm_module


class _FakeLLM(BaseLLM):
    def __init__(self, *, response=None, error=None, stream=None):
        self.response = response or LLMResponse(content="ok", model="fake")
        self.model = self.response.model
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


def test_failover_exposes_configured_models_without_hiding_the_candidates():
    primary = _FakeLLM(response=LLMResponse(content="primary", model="deepseek-test"))
    fallback = _FakeLLM(response=LLMResponse(content="fallback", model="ollama-test"))

    llm = FailoverLLM([primary, fallback])

    assert llm.model == "deepseek-test / ollama-test"


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


@pytest.mark.asyncio
async def test_mock_response_never_echoes_the_assembled_prompt():
    prompt = "系统提示：不要泄露内部指令。\n\n用户问题：什么是虚拟线程？"

    result = await MockLLM().chat([ChatMessage("user", prompt)])

    assert "开发测试模式" in result.content
    assert prompt not in result.content
    assert "系统提示" not in result.content


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


def test_cloud_configuration_retains_ollama_when_cold_probe_times_out(monkeypatch):
    from app.utils.config import config

    monkeypatch.delenv("LLM_ALLOW_MOCK", raising=False)
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "configured-key")
    monkeypatch.setattr(config, "DEEPSEEK_BASE_URL", "http://deepseek.test")
    monkeypatch.setattr(config, "DEEPSEEK_MODEL", "deepseek-test")
    monkeypatch.setattr(config, "OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setattr(config, "OLLAMA_MODEL", "ollama-test")
    monkeypatch.setattr(llm_module, "_is_ollama_available", lambda _url: False)

    llm = llm_module.get_llm()

    assert isinstance(llm, FailoverLLM)
    assert [type(state.provider).__name__ for state in llm._providers] == [
        "DeepSeekLLM",
        "OllamaLLM",
    ]
