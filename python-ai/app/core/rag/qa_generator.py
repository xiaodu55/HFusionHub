"""QA 对生成（实验特性，RAG_QA_GENERATION_ENABLED 门控）。

文档解析入库时，用对话 LLM 从分块中生成"问题-回答"对，并作为
``block_type="qa"`` 的独立分块并入索引——问句走 BM25/向量双通道召回，
显著提升"用户问法 ≠ 原文表述"场景的命中率。

设计约束：
- 纯逻辑与 LLM 调用分离：LLM 以可等待的 ``llm.chat(messages=...)`` 注入，
  本模块不做任何 IO/配置读取，全部可单测；
- 失败软化：单分块 LLM 失败/输出不可解析只跳过，绝不阻断索引；
- 去重 + 总量上限，防止烧 token 与索引膨胀。
"""

from __future__ import annotations

import json
import logging
import re

from app.core.chunker.text_chunker import VectorChunk
from app.core.llm.base import ChatMessage

logger = logging.getLogger(__name__)

# 低于该字符数的分块没有生成价值（信息量不足）
MIN_CHUNK_CHARS = 80
# 送 LLM 的单分块资料上限（超出截断）
_MAX_CHUNK_FEED = 2000

_QA_PROMPT = (
    "基于以下资料生成 1-2 个最适合检验检索效果的问答对。\n"
    '只输出 JSON 数组，格式：[{"q": "用户可能会问的问题", "a": "基于资料内容的回答"}]，'
    "不要输出任何其他文字。回答必须完全基于资料，不要编造资料外内容。\n\n资料：\n{content}"
)


def _extract_json_array(text: str) -> list[dict]:
    """从 LLM 输出中容错地提取 JSON 对象数组（容忍代码围栏与前后杂讯）。"""
    cleaned = re.sub(r"```(?:json)?", "", text or "").strip()
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start == -1 or end <= start:
        raise ValueError("输出中没有 JSON 数组")
    arr = json.loads(cleaned[start : end + 1])
    if not isinstance(arr, list):
        raise ValueError("JSON 不是数组")
    return [item for item in arr if isinstance(item, dict)]


def _response_text(response: object) -> str:
    """兼容对象/字典两种 LLM 返回形态。"""
    if isinstance(response, dict):
        return str(response.get("content") or "")
    return str(getattr(response, "content", "") or "")


def _norm_q(q: str) -> str:
    # 去空白 + 去中英文标点：同一问题带不带问号视为重复
    return re.sub(r"[\s？?！!。，,．.、；;：:（）()\"']", "", q.lower())


async def generate_qa_chunks(
    chunks: list[VectorChunk],
    document_id: str,
    document_title: str,
    llm: object,
    max_total: int = 20,
    max_per_chunk: int = 2,
    max_source_chunks: int = 12,
) -> list[VectorChunk]:
    """从分块生成 QA 对分块。

    Args:
        chunks: 原始分块（只读取，不修改）。
        document_id: 文档 ID（用于 chunk_id 前缀）。
        document_title: 冗余进 metadata 的文档标题（引用不依赖额外查询）。
        llm: 具备 ``await llm.chat(messages=..., temperature=...)`` 的 LLM 实例。
        max_total: 单文档 QA 分块总量上限。
        max_per_chunk: 单分块最多生成的问答对数（prompt 约束，代码再兜底截断）。
        max_source_chunks: 最多送 LLM 的分块数（控制 token 成本）。

    Returns:
        新构造的 QA 分块列表（调用方自行 append 并重排 index）。
        任何 LLM 失败都被软化——返回已生成的部分或空列表。
    """
    qa_chunks: list[VectorChunk] = []
    seen_questions: set[str] = set()

    for chunk in chunks[:max_source_chunks]:
        if len(qa_chunks) >= max_total:
            break
        source = chunk.content.strip()
        if len(source) < MIN_CHUNK_CHARS:
            continue
        try:
            response = await llm.chat(
                messages=[
                    # 模板内含 JSON 花括号示例，不能用 str.format——用 replace 防 KeyError
                    ChatMessage(
                        role="user",
                        content=_QA_PROMPT.replace("{content}", source[:_MAX_CHUNK_FEED]),
                    )
                ],
                temperature=0.2,
            )
            pairs = _extract_json_array(_response_text(response))
        except Exception as exc:
            logger.warning("QA 生成跳过分块 %s: %s", chunk.chunk_id, exc)
            continue

        added_for_chunk = 0
        for pair in pairs:
            if added_for_chunk >= max_per_chunk or len(qa_chunks) >= max_total:
                break
            q = str(pair.get("q", "")).strip()
            a = str(pair.get("a", "")).strip()
            if not q or not a:
                continue
            key = _norm_q(q)
            if key in seen_questions:
                continue
            seen_questions.add(key)
            qa_chunks.append(
                VectorChunk(
                    chunk_id=f"{document_id}_qa{len(qa_chunks) + 1}",
                    index=len(qa_chunks),
                    content=f"{q}\n{a}",
                    block_type="QA",
                    outline_path=list(chunk.outline_path),
                    metadata={
                        "qa_generated": True,
                        "question": q,
                        "document_title": document_title,
                    },
                )
            )
            added_for_chunk += 1

    return qa_chunks
