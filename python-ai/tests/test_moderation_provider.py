"""Batch 7 单元测试：可插拔内容审核 provider。

- 工厂：local/未配置 → None；http 且未配 endpoint → 禁用告警；配置齐全 → HttpModerationProvider
- HttpModerationProvider：请求体/头 + dot-path 解析（嵌套 JSON）
- ContentModerator 集成：外部命中 → 硬阻断（flag external_moderation:*）；
  外部异常 → fail-open 放行；local 模式行为不变
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

import app.core.policy.moderation_provider as mp
from app.core.policy.moderation_provider import (
    HttpModerationProvider,
    ModerationVerdict,
    get_moderation_provider,
    reset_moderation_provider,
)
from app.core.policy.guardrails import ContentModerator


@pytest.fixture(autouse=True)
def _reset_provider():
    reset_moderation_provider()
    yield
    reset_moderation_provider()


def _set(monkeypatch, **attrs):
    from app.utils.config import config

    for key, value in attrs.items():
        monkeypatch.setattr(config, key, value)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class TestFactory:
    def test_local_provider_returns_none(self, monkeypatch):
        _set(monkeypatch, MODERATION_PROVIDER="local")
        assert get_moderation_provider() is None

    def test_http_provider_requires_endpoint(self, monkeypatch):
        _set(monkeypatch, MODERATION_PROVIDER="http", MODERATION_HTTP_ENDPOINT="")
        assert get_moderation_provider() is None

    def test_http_provider_constructed_once(self, monkeypatch):
        _set(monkeypatch, MODERATION_PROVIDER="http",
             MODERATION_HTTP_ENDPOINT="https://moderation.test/check")
        first = get_moderation_provider()
        assert isinstance(first, HttpModerationProvider)
        assert get_moderation_provider() is first  # 单例


class TestHttpProvider:
    @pytest.mark.asyncio
    async def test_check_posts_and_parses_dot_path(self, monkeypatch):
        captured: Dict[str, Any] = {}

        class _FakeClient:
            def __init__(self, *a, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def post(self, url, json=None, headers=None):
                captured.update({"url": url, "json": json, "headers": headers})
                return _FakeResponse({"result": {"flagged": True, "label": "politics",
                                                 "risk": 0.93}})

        monkeypatch.setattr("httpx.Client", _FakeClient)
        provider = HttpModerationProvider(
            endpoint="https://moderation.test/check",
            api_key="sk-mod",
            flagged_path="result.flagged",
            category_path="result.label",
            score_path="result.risk",
        )
        verdict = provider.check("敏感文本", "input")

        assert captured["url"] == "https://moderation.test/check"
        assert captured["json"]["text"] == "敏感文本"
        assert captured["json"]["kind"] == "input"
        assert captured["headers"]["Authorization"] == "Bearer sk-mod"
        assert verdict.allowed is False
        assert verdict.category == "politics"
        assert verdict.score == pytest.approx(0.93)


class TestContentModeratorIntegration:
    def test_local_mode_unchanged(self, monkeypatch):
        _set(monkeypatch, MODERATION_PROVIDER="local")
        moderator = ContentModerator()
        result = moderator.check_input("普通问题")
        assert result.passed is True
        assert not any(f.startswith("external_moderation:") for f in result.flags)

    def test_external_flag_blocks_input(self, monkeypatch):
        _set(monkeypatch, MODERATION_PROVIDER="http",
             MODERATION_HTTP_ENDPOINT="https://moderation.test/check")
        reset_moderation_provider()

        class _FlagProvider:
            def check(self, text, kind):
                return ModerationVerdict(allowed=False, category="porn")

        monkeypatch.setattr(mp, "_provider", _FlagProvider())

        moderator = ContentModerator()
        result = moderator.check_input("随便什么文本")
        assert result.passed is False
        assert "external_moderation:porn" in result.flags

    def test_external_exception_fails_open(self, monkeypatch):
        _set(monkeypatch, MODERATION_PROVIDER="http",
             MODERATION_HTTP_ENDPOINT="https://moderation.test/check")
        reset_moderation_provider()

        class _BrokenProvider:
            def check(self, text, kind):
                raise RuntimeError("endpoint down")

        monkeypatch.setattr(mp, "_provider", _BrokenProvider())

        moderator = ContentModerator()
        result = moderator.check_input("普通问题")
        assert result.passed is True  # fail-open：本地规则仍然生效
        assert not any(f.startswith("external_moderation:") for f in result.flags)

    def test_external_flag_blocks_output(self, monkeypatch):
        _set(monkeypatch, MODERATION_PROVIDER="http",
             MODERATION_HTTP_ENDPOINT="https://moderation.test/check")
        reset_moderation_provider()

        class _FlagProvider:
            def check(self, text, kind):
                assert kind == "output"
                return ModerationVerdict(allowed=False, category="ad")

        monkeypatch.setattr(mp, "_provider", _FlagProvider())

        moderator = ContentModerator()
        result = moderator.check_output("模型输出内容")
        assert result.passed is False
        assert "external_moderation:ad" in result.flags
