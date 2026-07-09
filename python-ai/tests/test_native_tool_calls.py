"""原生 function calling（Batch 2）单元测试。

覆盖三层：
- ModelGateway：`_call_openai_compatible` / `_call_ollama` 的 tool_calls 提取与
  Ollama arguments 归一化（mock httpx 传输层，无真实网络）。
- ReactAgent `_chat_step`：原生命中、provider 异常降级、flag 关闭走文本。
- `_native_tools_schema`：ToolSpec → OpenAI function 形态转换。

flag 全部通过 monkeypatch feature_flags.is_enabled 控制，不依赖 Java。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

import app.core.agent.react as react_module
import app.core.llm.model_gateway as gateway_module
from app.core.agent.react import ReactAgent
from app.core.llm.base import ChatMessage, LLMResponse
from app.core.tools.spec import SEARCH_KB_SPEC


# ── 测试替身 ───────────────────────────────────────────────────────────────


class _FakePostResponse:
    """httpx.Response 最小替身（is_error 为属性，与真实 httpx 一致）。"""

    def __init__(self, payload: Dict[str, Any]):
        self._payload = payload
        self.status_code = 200
        self.text = ""

    @property
    def is_error(self) -> bool:
        return False

    def json(self) -> Dict[str, Any]:
        return self._payload


def _patch_transport(monkeypatch, payload: Dict[str, Any], captured: List[Dict[str, Any]]):
    """patch gateway 内传输层；captured 收集每次请求的 json payload。"""

    async def fake_post_with_retry(client, url, headers=None, json=None):
        captured.append({"url": url, "json": json})
        return _FakePostResponse(payload)

    monkeypatch.setattr("app.core.llm.http_client.post_with_retry", fake_post_with_retry)
    monkeypatch.setattr("app.core.llm.http_client.get_shared_client", lambda **kw: MagicMock())


def _openai_provider() -> gateway_module.ProviderConfig:
    return gateway_module.ProviderConfig(
        name="deepseek", provider_type="openai",
        base_url="https://api.test", api_key="sk-x",
    )


def _ollama_provider() -> gateway_module.ProviderConfig:
    return gateway_module.ProviderConfig(
        name="local", provider_type="ollama", base_url="http://localhost:11434",
    )


# ── Gateway 提取层 ─────────────────────────────────────────────────────────


class TestOpenAICompatibleToolCalls:
    @pytest.mark.asyncio
    async def test_extracts_tool_calls(self, monkeypatch):
        captured: List[Dict[str, Any]] = []
        payload = {
            "choices": [{
                "message": {
                    "content": "",
                    "tool_calls": [{"id": "c1", "type": "function",
                                    "function": {"name": "search_knowledge_base",
                                                 "arguments": '{"query": "退款"}'}}],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        _patch_transport(monkeypatch, payload, captured)

        content, finish, _usage, tool_calls = await gateway_module.ModelGateway._call_openai_compatible(
            _openai_provider(), "deepseek-chat",
            [ChatMessage(role="user", content="hi")], 0.7, 128,
            {"tools": [{"type": "function"}]},
        )

        assert content == ""
        assert finish == "tool_calls"
        assert tool_calls and tool_calls[0]["function"]["name"] == "search_knowledge_base"
        # tools 进入请求 payload
        assert captured[0]["json"]["tools"] == [{"type": "function"}]

    @pytest.mark.asyncio
    async def test_no_tool_calls_returns_none(self, monkeypatch):
        captured: List[Dict[str, Any]] = []
        payload = {
            "choices": [{"message": {"content": "答案"}, "finish_reason": "stop"}],
            "usage": {},
        }
        _patch_transport(monkeypatch, payload, captured)

        _, _, _, tool_calls = await gateway_module.ModelGateway._call_openai_compatible(
            _openai_provider(), "deepseek-chat",
            [ChatMessage(role="user", content="hi")], 0.7, 128, {},
        )
        assert tool_calls is None


class TestOllamaToolCalls:
    @pytest.mark.asyncio
    async def test_normalizes_dict_arguments(self, monkeypatch):
        captured: List[Dict[str, Any]] = []
        payload = {
            "message": {
                "content": "",
                "tool_calls": [{"function": {"name": "read_chunk",
                                             "arguments": {"chunk_id": "c-1"}}}],
            },
            "prompt_eval_count": 8,
            "eval_count": 4,
        }
        _patch_transport(monkeypatch, payload, captured)

        content, _finish, usage, tool_calls = await gateway_module.ModelGateway._call_ollama(
            _ollama_provider(), "qwen2.5",
            [ChatMessage(role="user", content="hi")], 0.7, 128,
            {"tools": [{"type": "function"}], "tool_choice": "auto"},
        )

        # Ollama dict arguments 归一化为 JSON 字符串（OpenAI 形态）
        assert tool_calls == [{"function": {"name": "read_chunk",
                                            "arguments": json.dumps({"chunk_id": "c-1"})}}]
        assert usage["completion_tokens"] == 4
        # tools/tool_choice 透传到 Ollama /api/chat payload
        assert captured[0]["json"]["tools"] == [{"type": "function"}]
        assert captured[0]["json"]["tool_choice"] == "auto"

    @pytest.mark.asyncio
    async def test_without_tools_payload_unchanged(self, monkeypatch):
        captured: List[Dict[str, Any]] = []
        payload = {"message": {"content": "hello"}, "prompt_eval_count": 1, "eval_count": 1}
        _patch_transport(monkeypatch, payload, captured)

        content, _, _, tool_calls = await gateway_module.ModelGateway._call_ollama(
            _ollama_provider(), "qwen2.5",
            [ChatMessage(role="user", content="hi")], 0.7, 128, None,
        )
        assert content == "hello"
        assert tool_calls is None
        assert "tools" not in captured[0]["json"]


# ── ReactAgent 原生分支 ────────────────────────────────────────────────────


class _ScriptedLLM:
    """按脚本返回预设 LLMResponse 的替身。"""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: List[Dict[str, Any]] = []
        self.model = "scripted"

    async def chat(self, messages, temperature=0.7, max_tokens=2048, **kwargs):
        self.calls.append({"kwargs": kwargs, "messages": list(messages)})
        return self._responses.pop(0)


def _set_native_flag(monkeypatch, enabled: bool):
    from app.utils.feature_flag import feature_flags

    monkeypatch.setattr(
        feature_flags, "is_enabled",
        lambda key, **kw: key == "agent.native_tool_calls.enabled" and enabled,
    )


def _kb_tools():
    return [{"name": SEARCH_KB_SPEC.name, "description": SEARCH_KB_SPEC.description,
             "_spec": SEARCH_KB_SPEC}]


class TestChatStep:
    @pytest.mark.asyncio
    async def test_native_action_extracted_and_content_rewritten(self, monkeypatch):
        _set_native_flag(monkeypatch, True)
        agent = ReactAgent(knowledge_base_id=1)
        llm = _ScriptedLLM([LLMResponse(
            content="", model="scripted",
            tool_calls=[{"id": "c1", "type": "function",
                         "function": {"name": "search_knowledge_base",
                                      "arguments": '{"query": "退款政策"}'}}],
        )])

        response, native = await agent._chat_step(
            llm, [ChatMessage(role="user", content="q")], _kb_tools())

        assert native == ("search_knowledge_base", {"query": "退款政策"})
        # content 回写 Action 文本，保持消息历史纯文本延续
        assert "Action: search_knowledge_base" in response.content
        # tools/tool_choice 进入 LLM 调用
        assert llm.calls[0]["kwargs"]["tools"][0]["function"]["name"] == SEARCH_KB_SPEC.name
        assert llm.calls[0]["kwargs"]["tool_choice"] == "auto"

    @pytest.mark.asyncio
    async def test_provider_error_falls_back_to_text(self, monkeypatch):
        _set_native_flag(monkeypatch, True)
        agent = ReactAgent(knowledge_base_id=1)

        class _FailingThenTextLLM(_ScriptedLLM):
            async def chat(self, messages, temperature=0.7, max_tokens=2048, **kwargs):
                if kwargs.get("tools"):
                    raise RuntimeError("provider does not support tools")
                self.calls.append({"kwargs": kwargs})
                return LLMResponse(content="Final Answer: 文本答案", model="scripted")

        llm = _FailingThenTextLLM([])
        response, native = await agent._chat_step(
            llm, [ChatMessage(role="user", content="q")], _kb_tools())

        assert native is None
        assert response.content == "Final Answer: 文本答案"

    @pytest.mark.asyncio
    async def test_flag_off_skips_native_path(self, monkeypatch):
        _set_native_flag(monkeypatch, False)
        agent = ReactAgent(knowledge_base_id=1)
        llm = _ScriptedLLM([LLMResponse(content="直接回答", model="scripted")])

        response, native = await agent._chat_step(
            llm, [ChatMessage(role="user", content="q")], _kb_tools())

        assert native is None
        assert "tools" not in llm.calls[0]["kwargs"]  # 未向 provider 传 tools
        assert response.content == "直接回答"

    @pytest.mark.asyncio
    async def test_empty_tool_calls_returns_response_without_action(self, monkeypatch):
        _set_native_flag(monkeypatch, True)
        agent = ReactAgent(knowledge_base_id=1)
        llm = _ScriptedLLM([LLMResponse(content="Final Answer: 不需要工具", model="scripted")])

        response, native = await agent._chat_step(
            llm, [ChatMessage(role="user", content="q")], _kb_tools())

        assert native is None
        assert response.content == "Final Answer: 不需要工具"


class TestNativeToolsSchema:
    def test_converts_spec_to_openai_format(self):
        agent = ReactAgent(knowledge_base_id=1)
        schema = agent._native_tools_schema(
            [{"name": SEARCH_KB_SPEC.name, "_spec": SEARCH_KB_SPEC}])

        assert schema[0]["type"] == "function"
        fn = schema[0]["function"]
        assert fn["name"] == SEARCH_KB_SPEC.name
        assert fn["description"] == SEARCH_KB_SPEC.description
        assert "properties" in fn["parameters"]

    def test_tools_without_spec_are_dropped(self):
        agent = ReactAgent(knowledge_base_id=1)
        assert agent._native_tools_schema([{"name": "no_spec"}]) is None
        assert agent._native_tools_schema([]) is None
        assert agent._native_tools_schema(None) is None


# ── max_steps 配置化 ───────────────────────────────────────────────────────


def test_agent_max_steps_defaults_to_config():
    from app.utils.config import config

    agent = ReactAgent(knowledge_base_id=1)
    assert agent.max_steps == config.RAG_AGENT_MAX_STEPS
    assert config.RAG_AGENT_MAX_STEPS >= 12
