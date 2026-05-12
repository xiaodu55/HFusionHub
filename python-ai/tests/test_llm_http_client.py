"""Tests for the shared LLM HTTP transport (P3): connection reuse + retry/backoff."""

import httpx
import pytest

from app.core.llm import http_client
from app.core.llm.base import ChatMessage
from app.core.llm.deepseek_llm import DeepSeekLLM


class _ScriptedClient:
    """Fake AsyncClient that replays a script of outcomes per ``post()`` call."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        outcome = self.script.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return httpx.Response(outcome, request=httpx.Request("POST", url))


@pytest.mark.asyncio
async def test_retries_429_until_success():
    client = _ScriptedClient([429, 429, 200])
    response = await http_client.post_with_retry(
        client, "http://provider/chat", max_retries=3, backoff=0.0
    )
    assert response.status_code == 200
    assert len(client.calls) == 3


@pytest.mark.asyncio
async def test_retries_5xx_but_surfaces_final_status():
    client = _ScriptedClient([500, 502])
    response = await http_client.post_with_retry(
        client, "http://provider/chat", max_retries=1, backoff=0.0
    )
    assert response.status_code == 502
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_does_not_retry_4xx_client_errors():
    client = _ScriptedClient([400])
    response = await http_client.post_with_retry(
        client, "http://provider/chat", max_retries=3, backoff=0.0
    )
    assert response.status_code == 400
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_re_raises_transport_error_after_exhausting_retries():
    client = _ScriptedClient([httpx.ConnectError("All connection attempts failed")] * 4)
    with pytest.raises(httpx.ConnectError, match="All connection attempts failed"):
        await http_client.post_with_retry(
            client, "http://provider/chat", max_retries=3, backoff=0.0
        )
    assert len(client.calls) == 4


class _FakeHttpxClient:
    """Minimal AsyncClient stand-in tracking instances and close state."""

    instances = []

    def __init__(self, *args, **kwargs):
        _FakeHttpxClient.instances.append(self)
        self.is_closed = False

    async def aclose(self):
        self.is_closed = True


@pytest.mark.asyncio
async def test_shared_client_is_reused_and_recreated_after_close(monkeypatch):
    monkeypatch.setattr("app.core.llm.http_client.httpx.AsyncClient", _FakeHttpxClient)
    http_client._shared_clients.clear()
    try:
        first = http_client.get_shared_client("owner-x")
        second = http_client.get_shared_client("owner-x")
        assert first is second
        assert len(_FakeHttpxClient.instances) == 1

        await http_client.aclose_shared_clients()
        assert first.is_closed

        third = http_client.get_shared_client("owner-x")
        assert third is not first
        assert len(_FakeHttpxClient.instances) == 2
    finally:
        http_client._shared_clients.clear()


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


@pytest.mark.asyncio
async def test_deepseek_chat_routes_through_shared_client(monkeypatch):
    """DeepSeekLLM.chat must go through the shared-client/retry path."""
    posted = {}

    async def _fake_post(client, url, **kwargs):
        posted["url"] = url
        return _FakeLLMResponse()

    monkeypatch.setattr(
        "app.core.llm.deepseek_llm.get_shared_client", lambda *a, **k: _FakeLLMClient()
    )
    monkeypatch.setattr("app.core.llm.deepseek_llm.post_with_retry", _fake_post)

    llm = DeepSeekLLM(api_key="sk-real-key", model="deepseek-test")
    result = await llm.chat([ChatMessage("user", "hello")])

    assert result.content == "hi"
    assert posted["url"] == "https://api.deepseek.com/v1/chat/completions"
