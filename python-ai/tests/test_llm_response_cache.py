"""Tests for the P2 non-streaming DeepSeekLLM exact-match response cache
and its normalized (fuzzy) secondary lookup."""


import pytest

from app.core.llm.base import ChatMessage
from app.core.llm.deepseek_llm import (
    DeepSeekLLM,
    _fuzzy_response_cache,
    _response_cache,
)


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
    """The caches are module-global; isolate tests from one another."""
    _response_cache.clear()
    _fuzzy_response_cache.clear()
    yield
    _response_cache.clear()
    _fuzzy_response_cache.clear()


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


# ── 归一化模糊命中（fuzzy secondary lookup） ──────────────────────────────


@pytest.mark.asyncio
async def test_fuzzy_hit_on_whitespace_and_case_difference(monkeypatch):
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
    monkeypatch.setattr(config, "LLM_RESPONSE_CACHE_FUZZY_ENABLED", True)

    llm = DeepSeekLLM(api_key="sk-real-key", model="deepseek-test")
    await llm.chat([ChatMessage("user", "Hello   World")])
    await llm.chat([ChatMessage("user", "hello world")])

    assert len(calls) == 1  # 归一化后同一请求 → 第二次命中模糊索引


@pytest.mark.asyncio
async def test_fuzzy_can_be_disabled(monkeypatch):
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
    monkeypatch.setattr(config, "LLM_RESPONSE_CACHE_FUZZY_ENABLED", False)

    llm = DeepSeekLLM(api_key="sk-real-key", model="deepseek-test")
    await llm.chat([ChatMessage("user", "Hello   World")])
    await llm.chat([ChatMessage("user", "hello world")])

    assert len(calls) == 2  # 模糊命中关闭后归一化差异即未命中


@pytest.mark.asyncio
async def test_fuzzy_hit_respects_ttl(monkeypatch):
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
    monkeypatch.setattr(config, "LLM_RESPONSE_CACHE_FUZZY_ENABLED", True)

    llm = DeepSeekLLM(api_key="sk-real-key", model="deepseek-test")
    await llm.chat([ChatMessage("user", "Hello World")])

    # 将模糊索引条目回拨到 TTL 之外
    from app.core.llm.deepseek_llm import _cache_key, _fuzzy_cache_key
    key = _cache_key("deepseek-test", 0.7, 2048, "sk-real-key", [ChatMessage("user", "Hello World")])
    fuzzy_key = _fuzzy_cache_key(key)
    assert fuzzy_key in _fuzzy_response_cache
    cached_at, cached = _fuzzy_response_cache[fuzzy_key]
    _fuzzy_response_cache[fuzzy_key] = (cached_at - 999, cached)

    await llm.chat([ChatMessage("user", "hello world")])
    assert len(calls) == 2  # 过期后即使归一化相同也重新请求


@pytest.mark.asyncio
async def test_fuzzy_hit_still_keyed_by_api_key_and_model(monkeypatch):
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
    monkeypatch.setattr(config, "LLM_RESPONSE_CACHE_FUZZY_ENABLED", True)

    llm_a = DeepSeekLLM(api_key="sk-key-a", model="deepseek-test")
    llm_b = DeepSeekLLM(api_key="sk-key-b", model="deepseek-test")
    llm_other = DeepSeekLLM(api_key="sk-key-a", model="deepseek-other")

    await llm_a.chat([ChatMessage("user", "Hello World")])
    await llm_b.chat([ChatMessage("user", "hello world")])     # api_key 不同 → miss
    await llm_other.chat([ChatMessage("user", "hello world")])  # model 不同 → miss

    assert len(calls) == 3
