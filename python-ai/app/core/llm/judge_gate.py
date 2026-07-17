"""LLM-as-judge 外部模型门禁（P2-8 / R15-28 最小落地）。

私有部署（央国企、总包等机密场景）必须保证**评测/judge 用途的 LLM 调用
不流经外部模型服务**——标书正文与评标语义属于敏感数据，交给外部 API
评分等于数据出域。

用法（评测策略构造模型名处统一接入）::

    from app.core.llm.judge_gate import resolve_judge_model
    self.model = resolve_judge_model(model)

行为：
  - ``MODEL_GATEWAY_NO_EXTERNAL_JUDGE`` 未开启（默认）→ 原样返回，无影响；
  - 开启后：judge 一律改用 ``MODEL_GATEWAY_INTERNAL_JUDGE_MODEL`` 指定的
    内网模型（如 ollama 上的本地模型）；未配置内网模型则直接拒绝评测
    （fail-closed），并记录审计日志。
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

ENV_NO_EXTERNAL_JUDGE = "MODEL_GATEWAY_NO_EXTERNAL_JUDGE"
ENV_INTERNAL_JUDGE_MODEL = "MODEL_GATEWAY_INTERNAL_JUDGE_MODEL"


def _flag_on(name: str) -> bool:
    return os.getenv(name, "false").lower() in ("true", "1", "yes")


def resolve_judge_model(model: str | None) -> str | None:
    """返回 judge/评测用途应使用的模型名；开启强制模式且未配置内网模型时抛错。"""
    if not _flag_on(ENV_NO_EXTERNAL_JUDGE):
        return model

    internal = os.getenv(ENV_INTERNAL_JUDGE_MODEL, "").strip()
    if not internal:
        logger.error(
            "LLM judge 被拒绝：%s 已开启但未配置 %s（私有部署要求 judge 走内网模型）",
            ENV_NO_EXTERNAL_JUDGE, ENV_INTERNAL_JUDGE_MODEL,
        )
        raise RuntimeError(
            "敏感部署模式：LLM-as-judge 禁止使用外部模型，"
            f"请配置 {ENV_INTERNAL_JUDGE_MODEL} 指向内网模型"
        )
    if model and model != internal:
        logger.warning("LLM judge 强制内网模型: %s -> %s", model, internal)
    return internal
