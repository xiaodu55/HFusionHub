"""LLM provider selection — ModelGateway is the single routing path.

历史上有两条链：ModelGateway（限流/熔断/成本记账/响应缓存）与旧的具体
provider 链（DeepSeek → Ollama → FailoverLLM），由 ``MODEL_GATEWAY_STREAM_ENABLED``
切换。旧链已退役（2026-08-29）：``get_llm`` 只返回 GatewayLLM 门面（或显式
mock），provider 解析失败直接抛 :class:`GatewayError`，不再静默降级。

``DeepSeekLLM`` / ``OllamaLLM`` 具体类仍保留：响应缓存模块被 gateway 复用，
``custom_provider.build_user_llm``（用户级自定义供应商）也基于它们构建。
"""

import logging
import os

from .base import BaseLLM, ChatMessage, LLMResponse
from .deepseek_llm import DeepSeekLLM
from .gateway_llm import GatewayLLM
from .mock_llm import MockLLM
from .ollama_llm import OllamaLLM

__all__ = [
    "BaseLLM", "ChatMessage", "LLMResponse", "DeepSeekLLM", "OllamaLLM",
    "MockLLM", "GatewayLLM", "get_llm",
]

logger = logging.getLogger(__name__)


def get_llm(model: str = None) -> BaseLLM:
    """Select the LLM for agent/chat use.

    Returns a :class:`GatewayLLM` facade so streaming and non-streaming calls
    get rate limiting, circuit breaking, cost tracking and the exact-match
    response cache. Provider resolution failures surface as :class:`GatewayError`
    at call time instead of silently degrading.

    Raises:
        RuntimeError: no provider is configured at all (nothing for the
            gateway to route to).
    """
    # Explicit test/development mock mode wins over everything — it must never
    # touch configured providers (including the gateway's).
    if os.getenv("LLM_ALLOW_MOCK", "false").lower() in ("true", "1", "yes"):
        logger.info("Using Mock LLM because LLM_ALLOW_MOCK=true")
        return MockLLM()

    from .model_gateway import get_model_gateway

    gateway = get_model_gateway()
    if not gateway._can_route():
        raise RuntimeError(
            "No LLM provider available. Set DEEPSEEK_API_KEY or start Ollama, "
            "or set LLM_ALLOW_MOCK=true for development."
        )
    logger.info("Using GatewayLLM (ModelGateway) for model=%s", model or "<default>")
    return GatewayLLM(gateway, model=model)
