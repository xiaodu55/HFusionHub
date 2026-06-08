"""Tests for the LLM-as-judge external-model gate (P2-8 / R15-28)."""

from __future__ import annotations

import pytest

from app.core.llm.judge_gate import resolve_judge_model


def test_passes_through_when_enforcement_off(monkeypatch):
    monkeypatch.delenv("MODEL_GATEWAY_NO_EXTERNAL_JUDGE", raising=False)
    assert resolve_judge_model("deepseek-chat") == "deepseek-chat"
    assert resolve_judge_model(None) is None


def test_rewrites_to_internal_model_when_enforced(monkeypatch):
    monkeypatch.setenv("MODEL_GATEWAY_NO_EXTERNAL_JUDGE", "true")
    monkeypatch.setenv("MODEL_GATEWAY_INTERNAL_JUDGE_MODEL", "ollama-qwen3-8b")
    assert resolve_judge_model("deepseek-chat") == "ollama-qwen3-8b"
    assert resolve_judge_model(None) == "ollama-qwen3-8b"


def test_fail_closed_when_internal_model_unconfigured(monkeypatch):
    monkeypatch.setenv("MODEL_GATEWAY_NO_EXTERNAL_JUDGE", "true")
    monkeypatch.delenv("MODEL_GATEWAY_INTERNAL_JUDGE_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="内网模型"):
        resolve_judge_model("deepseek-chat")


def test_internal_model_passes_through_unchanged(monkeypatch):
    monkeypatch.setenv("MODEL_GATEWAY_NO_EXTERNAL_JUDGE", "true")
    monkeypatch.setenv("MODEL_GATEWAY_INTERNAL_JUDGE_MODEL", "ollama-qwen3-8b")
    assert resolve_judge_model("ollama-qwen3-8b") == "ollama-qwen3-8b"
