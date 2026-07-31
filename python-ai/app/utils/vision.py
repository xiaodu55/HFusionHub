"""对话图片输入的视觉辅助（实验特性，CHAT_MULTIMODAL_INPUT_ENABLED 门控）。

职责：
- 校验前端传来的图片 data URL（JPG/PNG/WEBP，单张 ≤5MB，最多 4 张）；
- 逐张调用 Ollama 视觉模型（复用摄入侧同一 VLM 配置，qwen2.5vl）生成中文描述；
- 组装为可拼进用户消息的上下文块。

设计：图片 → 中文描述 → 文本管线的"描述增强"路线，与
core/parser/multimodal_evidence.py 的摄入侧 VLM 用法保持一致——
不要求对话模型本身具备视觉能力。
"""

from __future__ import annotations

import base64
import logging

import httpx

from app.utils.config import config

logger = logging.getLogger(__name__)

MAX_IMAGES = 4
MAX_IMAGE_BYTES = 5 * 1024 * 1024
_ALLOWED_PREFIXES = (
    "data:image/jpeg;base64,",
    "data:image/png;base64,",
    "data:image/webp;base64,",
)
_VLM_PROMPT = (
    "请用中文详细描述这张图片的内容；"
    "如包含文字、表格或数据，请原样转写关键部分，不要遗漏数字。"
)


def is_enabled() -> bool:
    return config.CHAT_MULTIMODAL_INPUT_ENABLED


def _vlm_base_url() -> str:
    return (config.RAG_MULTIMODAL_VLM_BASE_URL or config.OLLAMA_BASE_URL).rstrip("/")


def _vlm_timeout() -> float:
    return float(config.RAG_MULTIMODAL_VLM_TIMEOUT_SECONDS)


def validate_data_urls(data_urls: list[str]) -> list[str]:
    """校验并提取纯 base64 载荷；不合法时抛 ValueError（message 为用户可读文案）。"""
    if not data_urls:
        return []
    if len(data_urls) > MAX_IMAGES:
        raise ValueError(f"每次最多上传 {MAX_IMAGES} 张图片")
    payloads: list[str] = []
    for url in data_urls:
        if not isinstance(url, str) or not url.startswith(_ALLOWED_PREFIXES):
            raise ValueError("仅支持 JPG / PNG / WEBP 格式的图片")
        b64 = url.split(",", 1)[1]
        try:
            raw = base64.b64decode(b64)
        except Exception as exc:  # noqa: BLE001 — 用户输入，统一转友好文案
            raise ValueError("图片数据无法解析") from exc
        if len(raw) > MAX_IMAGE_BYTES:
            raise ValueError("单张图片不能超过 5MB")
        if not raw:
            raise ValueError("图片内容为空")
        payloads.append(b64)
    return payloads


def _describe_one(image_b64: str) -> str:
    """同步调用 Ollama 视觉模型；失败抛异常由调用方统一兜底。"""
    payload = {
        "model": config.RAG_MULTIMODAL_VLM_MODEL,
        "messages": [{"role": "user", "content": _VLM_PROMPT, "images": [image_b64]}],
        "stream": False,
        "options": {"temperature": 0.1},
    }
    resp = httpx.post(
        f"{_vlm_base_url()}/api/chat", json=payload, timeout=_vlm_timeout()
    )
    if resp.status_code != 200:
        raise RuntimeError(f"vision http {resp.status_code}: {resp.text[:200]}")
    content = str(((resp.json().get("message") or {}).get("content")) or "").strip()
    if not content:
        raise RuntimeError("vision empty response")
    return content


def build_image_context(data_urls: list[str]) -> str:
    """校验并描述全部图片，返回可拼进用户消息的上下文块。

    同步阻塞实现——调用方必须放到线程池（asyncio.to_thread）执行。
    未启用时直接拒绝（自防御：端点层已先行校验，这里兜底）；
    任何图片失败都不阻断对话：该图记为"未能解析"。
    """
    if not is_enabled():
        raise RuntimeError(
            "图片输入功能未开启（实验特性，需 CHAT_MULTIMODAL_INPUT_ENABLED=true）"
        )
    payloads = validate_data_urls(data_urls)
    if not payloads:
        return ""
    captions: list[str] = []
    for i, image_b64 in enumerate(payloads, 1):
        try:
            captions.append(f"图片 {i}：{_describe_one(image_b64)}")
        except Exception as exc:  # noqa: BLE001 — 单图失败不阻断
            logger.warning("图片 %d 描述失败: %s", i, exc)
            captions.append(f"图片 {i}：（内容未能解析）")
    return (
        f"[用户在本次消息中附带了 {len(payloads)} 张图片，内容如下]\n"
        + "\n".join(captions)
        + "\n[图片内容结束]"
    )
