"""语音 STT/TTS API（Batch 10，默认关闭）。

两条端点均要求内部令牌（Java 会话鉴权后转发），引擎为 OpenAI 兼容音频接口
（/v1/audio/transcriptions、/v1/audio/speech）。`VOICE_ENABLED=false`（默认）
时返回 503，前端按钮不渲染。

设计取舍：
- STT 收**原始音频字节**（非 multipart）：零额外依赖，Java/前端转发均为
  单一二进制体，文件名经 ``X-Audio-Filename`` 头传递；
- 失败语义：引擎不可用/超时 → 503（用户可重试），不做静默降级。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.utils.config import config

router = APIRouter()
logger = logging.getLogger(__name__)

_MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10MB（与文档上传同量级）
_SUPPORTED_AUDIO = {".webm", ".mp3", ".wav", ".m4a", ".ogg"}


def _ensure_enabled() -> None:
    if not config.VOICE_ENABLED:
        raise HTTPException(status_code=503, detail="语音能力未启用（VOICE_ENABLED=false）")


def _auth_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if config.VOICE_OPENAI_API_KEY:
        headers["Authorization"] = f"Bearer {config.VOICE_OPENAI_API_KEY}"
    return headers


def _audio_suffix(filename: str) -> str:
    suffix = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ".webm"
    return suffix if suffix in _SUPPORTED_AUDIO else ""


@router.post("/api/voice/transcribe")
async def transcribe(request: Request, language: str | None = None) -> dict[str, str]:
    """语音转文本（STT）。音频为原始请求体；文件名经 X-Audio-Filename 头。返回 {"text": ...}。"""
    _ensure_enabled()
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="音频内容为空")
    if len(data) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="音频超过 10MB 上限")
    filename = request.headers.get("X-Audio-Filename", "audio.webm")
    suffix = _audio_suffix(filename)
    if not suffix:
        raise HTTPException(status_code=415, detail=f"不支持的音频格式: {filename}")

    import httpx

    url = f"{config.VOICE_OPENAI_BASE_URL.rstrip('/')}/v1/audio/transcriptions"
    files = {"file": (filename, data)}
    form: dict[str, str] = {"model": config.VOICE_STT_MODEL}
    if language:
        form["language"] = language
    headers = {}
    if config.VOICE_OPENAI_API_KEY:
        headers["Authorization"] = f"Bearer {config.VOICE_OPENAI_API_KEY}"
    try:
        async with httpx.AsyncClient(timeout=config.VOICE_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, headers=headers, files=files, data=form)
    except Exception as exc:
        logger.warning("[voice] transcribe upstream error: %s", exc)
        raise HTTPException(status_code=503, detail="语音识别服务暂不可用") from exc
    if resp.status_code >= 400:
        logger.warning("[voice] transcribe upstream %s: %s", resp.status_code, resp.text[:200])
        raise HTTPException(status_code=503, detail="语音识别服务返回错误")
    text = (resp.json() or {}).get("text") or ""
    return {"text": text}


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    voice: str | None = Field(None, max_length=64)


@router.post("/api/voice/synthesize")
async def synthesize(request: SynthesizeRequest) -> Response:
    """文本转语音（TTS）。返回音频二进制（audio/mpeg）。"""
    _ensure_enabled()
    import httpx

    url = f"{config.VOICE_OPENAI_BASE_URL.rstrip('/')}/v1/audio/speech"
    payload = {
        "model": config.VOICE_TTS_MODEL,
        "input": request.text,
        "voice": request.voice or config.VOICE_TTS_VOICE,
        "response_format": "mp3",
    }
    try:
        async with httpx.AsyncClient(timeout=config.VOICE_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, headers=_auth_headers(), json=payload)
    except Exception as exc:
        logger.warning("[voice] synthesize upstream error: %s", exc)
        raise HTTPException(status_code=503, detail="语音合成服务暂不可用") from exc
    if resp.status_code >= 400:
        logger.warning("[voice] synthesize upstream %s: %s", resp.status_code, resp.text[:200])
        raise HTTPException(status_code=503, detail="语音合成服务返回错误")
    return Response(content=resp.content, media_type="audio/mpeg")


@router.get("/api/voice/status")
async def status() -> dict[str, bool]:
    """前端按钮渲染依据（不需要暴露任何敏感配置）。"""
    return {
        "enabled": bool(config.VOICE_ENABLED),
        "stt": bool(config.VOICE_ENABLED and config.VOICE_OPENAI_BASE_URL and config.VOICE_STT_MODEL),
        "tts": bool(config.VOICE_ENABLED and config.VOICE_OPENAI_BASE_URL and config.VOICE_TTS_MODEL),
    }
