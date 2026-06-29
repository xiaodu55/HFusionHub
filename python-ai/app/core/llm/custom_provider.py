"""Request-scoped user model providers.

Credentials arrive only from the authenticated Java backend over the internal
service boundary. They are never cached, logged, or included in responses.
"""

from __future__ import annotations

import ipaddress
from typing import Any, Mapping
from urllib.parse import urlparse

from .base import BaseLLM
from .deepseek_llm import DeepSeekLLM
from .ollama_llm import OllamaLLM


_BLOCKED_HOSTS = {
    "169.254.169.254",
    "metadata.google.internal",
    "metadata.azure.internal",
}


def _validated_base_url(raw: str) -> str:
    value = (raw or "").strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Base URL must be a complete http:// or https:// URL")
    if parsed.username or parsed.password:
        raise ValueError("Base URL must not contain credentials")

    hostname = parsed.hostname.lower()
    if hostname in _BLOCKED_HOSTS:
        raise ValueError("This Base URL is not allowed")
    try:
        address = ipaddress.ip_address(hostname)
        if address.is_link_local or address.is_multicast or address.is_unspecified:
            raise ValueError("This Base URL is not allowed")
    except ValueError as exc:
        if str(exc) == "This Base URL is not allowed":
            raise
        # A normal DNS hostname is allowed. Private addresses remain available
        # for self-hosted Ollama/OpenAI-compatible services.
        #
        # SSRF 权衡（有意为之，勿"加固"掉）：放行私网段是自托管模型（内网
        # Ollama/vLLM）的硬需求；对冲手段是仅登录用户可配置自定义供应商 +
        # 出网域名/IP 由部署侧网络策略约束。若未来开放给不可信租户，需改为
        # 白名单制并校验解析后 IP。
    return value


def build_user_llm(provider_config: Mapping[str, Any] | None) -> BaseLLM | None:
    if not provider_config:
        return None

    provider_type = str(provider_config.get("provider_type") or "").strip()
    base_url = _validated_base_url(str(provider_config.get("base_url") or ""))
    model = str(provider_config.get("model") or "").strip()
    if not model or len(model) > 160:
        raise ValueError("Model name is required")

    if provider_type == "ollama":
        return OllamaLLM(base_url=base_url, model=model)

    if provider_type == "openai_compatible":
        api_key = str(provider_config.get("api_key") or "").strip()
        if not api_key:
            raise ValueError("API Key is required for this provider")
        return DeepSeekLLM(api_key=api_key, base_url=base_url, model=model)

    raise ValueError("Unsupported provider type")

