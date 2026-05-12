"""Tests for the P2 non-streaming DeepSeekLLM exact-match response cache."""

import pytest

from app.core.llm.base import ChatMessage
from app.core.llm.deepseek_llm import DeepSeekLLM, _response_cache


class _FakeLLMResponse:
    is_error = False
    status_code = 200

    def json(self):
        return {
            "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 3},
        }


class _FakeLLMClient:
    async def post(self, url, **kwargs):
        return _FakeLLMResponse()


@pytest.fixture(autouse=True)
def _clear_cache():
    """The cache is module-global; isolate tests from one another."""
    _response_cache.clear()
    yield
    _response_cache.clear()


@pytest.mark.asyncio
async def test_identical_chat_is_served_from_cache(monkeypatch):
    calls = []

    async def _fake_post(client, url, **kwargs):
        calls.append(url)
        return _FakeLLMResponse()

    monkeypatch.setattr(
        "app.core.llm.deepseek_llm.get_shared_client", lambda *a, **k: _FakeLLMClient()
    )
    monkeypatch.setattr("app.core.llm.deepseek_llm.post_with_retry", _fake_post)
    from app.utils.config import config
    monkeypatch.setattr(config, "LLM_RESPONSE_CACHE_TTL_SECONDS", 300)

    llm = DeepSeekLLM(api_key="sk-real-key", model="deepseek-test")
    first = await llm.chat([ChatMessage("user", "hello")])
    second = await llm.chat([ChatMessage("user", "hello")])

    assert first.content == "hi"
    assert second.content == "hi"
    assert len(calls) == 1  # second call served from cache


@pytest.mark.asyncio
async def test_different_messages_miss_the_cache(monkeypatch):
    calls = []

    async def _fake_post(client, url, **kwargs):
        calls.append(url)
        return _FakeLLMResponse()

    monkeypatch.setattr(
        "app.core.llm.deepseek_llm.get_shared_client", lambda *a, **k: _FakeLLMClient()
    )
    monkeypatch.setattr("app.core.llm.deepseek_llm.post_with_retry", _fake_post)
    from app.utils.config import config
    monkeypatch.setattr(config, "LLM_RESPONSE_CACHE_TTL_SECONDS", 300)

    llm = DeepSeekLLM(api_key="sk-real-key", model="deepseek-test")
    await llm.chat([ChatMessage("user", "hello")])
    await llm.chat([ChatMessage("user", "a different question")])

    assert len(calls) == 2


@pytest.mark.asyncio
async def test_cache_can_be_disabled(monkeypatch):
    calls = []

    async def _fake_post(client, url, **kwargs):
        calls.append(url)
        return _FakeLLMResponse()

    monkeypatch.setattr(
        "app.core.llm.deepseek_llm.get_shared_client", lambda *a, **k: _FakeLLMClient()
    )
    monkeypatch.setattr("app.core.llm.deepseek_llm.post_with_retry", _fake_post)
    from app.utils.config import config
    monkeypatch.setattr(config, "LLM_RESPONSE_CACHE_TTL_SECONDS", 0)

    llm = DeepSeekLLM(api_key="sk-real-key", model="deepseek-test")
    await llm.chat([ChatMessage("user", "hello")])
    await llm.chat([ChatMessage("user", "hello")])

    assert len(calls) == 2  # TTL=0 disables the cache entirely
