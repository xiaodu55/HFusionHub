"""Batch 10 语音端点测试：开关门控（503）+ 参数校验。

上游引擎（/v1/audio/*）通过 mock httpx 不真实调用；开关关闭时
不产生任何上游请求。
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.voice import SynthesizeRequest, status, synthesize, transcribe


class _FakeRequest:
    def __init__(self, data: bytes, filename: str = "audio.webm"):
        self._data = data
        self.headers = {"X-Audio-Filename": filename}

    async def body(self) -> bytes:
        return self._data


@pytest.fixture(autouse=True)
def _voice_disabled(monkeypatch):
    from app.utils.config import config

    monkeypatch.setattr(config, "VOICE_ENABLED", False)
    monkeypatch.setattr(config, "VOICE_OPENAI_BASE_URL", "")
    monkeypatch.setattr(config, "VOICE_STT_MODEL", "")
    monkeypatch.setattr(config, "VOICE_TTS_MODEL", "")
    yield
    monkeypatch.setattr(config, "VOICE_ENABLED", False)


class TestDisabledGate:
    @pytest.mark.asyncio
    async def test_transcribe_returns_503_when_disabled(self, monkeypatch):
        called = {"upstream": False}

        class _FakeClient:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                called["upstream"] = True
                raise AssertionError("关闭时不应调用上游")

            async def __aexit__(self, *a):
                return False

        monkeypatch.setattr("httpx.AsyncClient", _FakeClient)
        with pytest.raises(HTTPException) as excinfo:
            await transcribe(request=_FakeRequest(b"x"), language=None)
        assert excinfo.value.status_code == 503
        assert called["upstream"] is False

    @pytest.mark.asyncio
    async def test_synthesize_returns_503_when_disabled(self, monkeypatch):
        with pytest.raises(HTTPException) as excinfo:
            await synthesize(SynthesizeRequest(text="你好"))
        assert excinfo.value.status_code == 503

    @pytest.mark.asyncio
    async def test_status_reports_disabled(self):
        result = await status()
        assert result == {"enabled": False, "stt": False, "tts": False}


class TestEnabledGuards:
    @pytest.mark.asyncio
    async def test_transcribe_rejects_unsupported_format(self, monkeypatch):
        from app.utils.config import config

        monkeypatch.setattr(config, "VOICE_ENABLED", True)
        with pytest.raises(HTTPException) as excinfo:
            await transcribe(request=_FakeRequest(b"x", filename="a.flac"), language=None)
        assert excinfo.value.status_code == 415

    @pytest.mark.asyncio
    async def test_transcribe_rejects_empty_audio(self, monkeypatch):
        from app.utils.config import config

        monkeypatch.setattr(config, "VOICE_ENABLED", True)
        with pytest.raises(HTTPException) as excinfo:
            await transcribe(request=_FakeRequest(b""), language=None)
        assert excinfo.value.status_code == 400

    @pytest.mark.asyncio
    async def test_status_reports_partial_capability(self, monkeypatch):
        from app.utils.config import config

        monkeypatch.setattr(config, "VOICE_ENABLED", True)
        monkeypatch.setattr(config, "VOICE_OPENAI_BASE_URL", "https://api.test")
        monkeypatch.setattr(config, "VOICE_STT_MODEL", "whisper-1")
        result = await status()
        assert result == {"enabled": True, "stt": True, "tts": False}


class TestSynthesizeRequest:
    def test_text_length_constrained(self):
        with pytest.raises(Exception):
            SynthesizeRequest(text="x" * 2001)
        SynthesizeRequest(text="你好")
