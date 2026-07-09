"""可插拔内容审核 provider（Batch 7）。

在既有本地规则（GuardrailsPipeline / ContentModerator）之上，引入可选的
外部审核引擎：

- ``local``（默认）：不调用任何外部服务，行为与历史版本完全一致；
- ``http``：每次输入/输出审核额外调用一个通用 REST 审核端点
  （阿里云内容安全/网易易盾等均可通过该通用协议接入）。

失败语义：**fail-open**（外部审核不可用时仅告警并放行，本地规则仍生效）——
与仓库"外部引擎失败只跳过、绝不阻断主链路"的既有取舍一致；需要更强保证的
部署可在网关层前置独立的强制审核服务。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

from app.utils.config import config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModerationVerdict:
    """外部审核结论。"""

    allowed: bool
    category: Optional[str] = None  # 命中类别（porn/ad/politics 等，供应商自定义）
    score: Optional[float] = None  # 风险分（0-1，供应商自定义尺度）
    provider: str = "http"
    raw: Optional[Dict[str, Any]] = None


class ModerationProvider(Protocol):
    """审核引擎协议：同步调用，调用方（ContentModerator）本身在同步管线内。"""

    def check(self, text: str, kind: str) -> ModerationVerdict:
        """审核一段文本。kind: "input"（用户输入）| "output"（模型输出）。"""
        ...  # pragma: no cover


def _dot_path(data: Dict[str, Any], path: str) -> Any:
    """按 a.b.c 取嵌套字段；路径非法返回 None。"""
    current: Any = data
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


class HttpModerationProvider:
    """通用 REST 审核引擎（httpx 同步 + 短超时）。

    请求：``POST {endpoint}``，JSON 体 ``{"text": ..., "kind": ...}``，
    ``Authorization: Bearer {api_key}``（配置了才带）。

    响应解析（dot-path，均可按供应商适配）：
    - ``MODERATION_HTTP_FLAGGED_PATH``（默认 ``flagged``，bool）
    - ``MODERATION_HTTP_CATEGORY_PATH``（默认 ``category``）
    - ``MODERATION_HTTP_SCORE_PATH``（默认 ``score``）
    """

    def __init__(
        self,
        endpoint: str,
        api_key: str = "",
        timeout_seconds: float = 2.0,
        flagged_path: str = "flagged",
        category_path: str = "category",
        score_path: str = "score",
    ):
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.flagged_path = flagged_path
        self.category_path = category_path
        self.score_path = score_path

    def check(self, text: str, kind: str) -> ModerationVerdict:
        import httpx

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {"text": text[:6000], "kind": kind}

        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(self.endpoint, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        flagged = bool(_dot_path(data, self.flagged_path))
        return ModerationVerdict(
            allowed=not flagged,
            category=_dot_path(data, self.category_path),
            score=_as_float(_dot_path(data, self.score_path)),
            provider="http",
            raw=None,
        )


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


# ── 工厂（模块级单例）──────────────────────────────────────────────────────

_provider: Optional[ModerationProvider] = None


def get_moderation_provider() -> Optional[ModerationProvider]:
    """按 MODERATION_PROVIDER 配置返回外部审核引擎；local/未配置返回 None。"""
    global _provider
    if _provider is not None:
        return _provider if _provider != _NO_PROVIDER else None
    if config.MODERATION_PROVIDER == "http":
        if not config.MODERATION_HTTP_ENDPOINT:
            logger.warning("MODERATION_PROVIDER=http 但未配置 MODERATION_HTTP_ENDPOINT，外部审核禁用")
            _provider = _NO_PROVIDER
            return None
        _provider = HttpModerationProvider(
            endpoint=config.MODERATION_HTTP_ENDPOINT,
            api_key=config.MODERATION_HTTP_API_KEY,
            timeout_seconds=config.MODERATION_HTTP_TIMEOUT_SECONDS,
            flagged_path=config.MODERATION_HTTP_FLAGGED_PATH,
            category_path=config.MODERATION_HTTP_CATEGORY_PATH,
            score_path=config.MODERATION_HTTP_SCORE_PATH,
        )
        return _provider
    return None


def reset_moderation_provider() -> None:
    """测试用：重置单例。"""
    global _provider
    _provider = None


class _NoProvider:
    """占位哨兵：已判定为"无外部引擎"，避免重复解析配置。"""

    def check(self, text: str, kind: str) -> ModerationVerdict:  # pragma: no cover
        raise NotImplementedError


_NO_PROVIDER = _NoProvider()


__all__ = [
    "ModerationVerdict",
    "ModerationProvider",
    "HttpModerationProvider",
    "get_moderation_provider",
    "reset_moderation_provider",
]
