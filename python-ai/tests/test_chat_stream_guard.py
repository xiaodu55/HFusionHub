"""Tests for the streamed chat output guard (第十五轮 P0-5).

非流式路径在 _build_chat_response 中过 guard_model_output；流式通道此前
完全绕过守卫。_content_guarded_sse 包装 SSE 生成器：增量透传 + 流末对
累计回答守卫，命中时在 [DONE] 前补发 content_replace 矫正事件。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.api import chat as chat_api


def _sse(payload) -> str:
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


async def _agen(events):
    for e in events:
        yield e


async def _collect(gen):
    return [e async for e in gen]


@pytest.fixture
def guard(monkeypatch):
    """可控的 guard_model_output 桩。"""
    state = {"verdict": None}

    def fake_guard(text, context):
        return text, state["verdict"]

    monkeypatch.setattr(chat_api._GUARD_POLICY_ENGINE, "guard_model_output", fake_guard)
    return state


@pytest.mark.asyncio
async def test_clean_stream_passes_through_without_correction(guard):
    events = [
        _sse({"event": "run_started"}),
        "data: 你好\n\n",
        "data: 世界\n\n",
        "data: [DONE]\n\n",
    ]
    out = await _collect(chat_api._content_guarded_sse(_agen(events), 1))
    assert out == events  # 原样透传，无矫正事件
    assert not any("content_replace" in e for e in out)


@pytest.mark.asyncio
async def test_violating_stream_emits_replace_event_before_done(guard):
    guard["verdict"] = SimpleNamespace(reason="critical_violation")  # 非空 verdict = 命中违规
    events = [
        _sse({"event": "step_completed", "sequence": 1}),
        _sse({"content": "违规"}),
        _sse({"content": "内容片段"}),
        "data: [DONE]\n\n",
    ]
    out = await _collect(chat_api._content_guarded_sse(_agen(events), 1))

    assert out[-1] == "data: [DONE]\n\n"
    correction = json.loads(out[-2][len("data: "):])
    assert correction["content_replace"] is True
    assert correction["content"] == chat_api._GUARDED_RESPONSE
    # 原始事件仍全部透传（顺序保持）
    assert out[:-2] == events[:-1]


@pytest.mark.asyncio
async def test_cancelled_and_error_events_not_accumulated(guard, monkeypatch):
    seen = {}

    def fake_guard(text, context):
        seen["text"] = text
        return text, None

    monkeypatch.setattr(chat_api._GUARD_POLICY_ENGINE, "guard_model_output", fake_guard)
    events = [
        _sse({"content": "正常内容"}),
        _sse({"content": "", "cancelled": True}),
        _sse({"content": "", "error": "boom"}),
        "data: [DONE]\n\n",
    ]
    out = await _collect(chat_api._content_guarded_sse(_agen(events), 1))
    assert seen["text"] == "正常内容"  # cancelled/error 事件不计入守卫文本
    assert not any("content_replace" in e for e in out)


@pytest.mark.asyncio
async def test_empty_stream_skips_guard(guard, monkeypatch):
    calls = {"n": 0}

    def fake_guard(text, context):
        calls["n"] += 1
        return text, None

    monkeypatch.setattr(chat_api._GUARD_POLICY_ENGINE, "guard_model_output", fake_guard)
    events = ["data: [DONE]\n\n"]
    out = await _collect(chat_api._content_guarded_sse(_agen(events), 1))
    assert out == events
    assert calls["n"] == 0
