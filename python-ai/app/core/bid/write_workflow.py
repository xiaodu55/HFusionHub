"""标书撰写工作流（P1-2 核心）。

以「已确认的需求清单」为输入，按分节（商务/技术/资质/格式）生成标书草稿：
  - commercial    商务标（报价说明、付款方式、商务承诺）
  - technical     技术方案（针对技术/业绩需求逐条应答）
  - qualification 资质文件（针对资质需求，缺项用【待补充】占位）
  - format        格式文件（响应格式/签章/份数要求）

每节以需求清单 + 多知识库检索依据（招标库 / 资质库 / 历史标书库）为输入，
逐条回应需求、不编造数据；证据经 [N] 索引回溯为真实 chunk_id 供前端追溯。

设计取舍：与解读工作流的多专家并发不同，撰写采用**逐节串行**——
1) 长文 SSE 需要确定性的分节完成顺序（bid_section_completed 事件）；
2) 逐节单次 LLM 调用更温和，避免并发长文生成挤压限流。
每节语义上仍是一个独立"专家"（商务/技术/资质/格式），契约与多 Agent 对齐。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from app.core.llm import get_llm
from app.core.llm.structured_output import generate_structured
from app.core.rag.retriever import get_retriever

logger = logging.getLogger(__name__)

# ── 检索与上下文预算 ────────────────────────────────────────────────
MAX_CHUNKS = 20
CHUNK_MAX_CHARS = 1500
RETRIEVE_TOP_K = 4

# 并发检索深度（R15-10）：6 个固定查询 × N KB 场景下限制同时进行的
# 检索数，避免打爆 embedding/Milvus 连接
_RETRIEVAL_CONCURRENCY = 6

# 默认分节结构（可被租户模板 section_defs 覆盖）
DEFAULT_SECTIONS: list[dict[str, str]] = [
    {"key": "commercial", "title": "商务标"},
    {"key": "technical", "title": "技术方案"},
    {"key": "qualification", "title": "资质文件"},
    {"key": "format", "title": "格式文件"},
]

SECTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "section_key": {"type": "string"},
        "content": {
            "type": "string",
            "description": "本节标书正文：逐条回应本分节涉及的需求，编造项用【待补充：XXX】占位",
        },
        "evidence_chunk_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["section_key", "content"],
}

_WRITE_SYSTEM_PROMPT = (
    "你是资深标书撰写专家。请严格依据提供的招标文件片段与需求清单撰写标书分节："
    "逐条回应需求，不编造资质/业绩/数据；需要公司信息、金额、证件号等占位时用【待补充：XXX】标注；"
    "语气正式、结构清晰，可直接放入投标文件。"
    "引用格式：[N] 表示第 N 条证据片段，请在你的 evidence_chunk_ids 中列出所依据的编号。"
)


class BidWriteWorkflow:
    """标书撰写工作流：按分节生成标书草稿，证据可追溯，支持逐节回调。"""

    def __init__(self, llm=None, retriever=None):
        self.llm = llm or get_llm()
        self.retriever = retriever or get_retriever()

    async def run(
        self,
        *,
        project_id: int,
        title: str,
        tender_number: str | None,
        requirements: list[dict[str, Any]],
        knowledge_base_ids: list[int],
        section_defs: list[dict[str, Any]] | None = None,
        on_section_start: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        on_section: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        """生成全部分节草稿。

        :param requirements: 已确认需求清单 [{category, requirement, source_clause}]
        :param knowledge_base_ids: 招标库(+资质库/历史标书库) ID 列表
        :param section_defs: [{key, title}]，缺省用 DEFAULT_SECTIONS
        :param on_section_start: 每节开始前回调（SSE bid_section_started 用）
        :param on_section: 每节完成后回调（SSE bid_section_completed 用）
        """
        corpus = await self._retrieve_corpus(knowledge_base_ids, title)
        context, chunk_map = self._build_context(corpus)
        sections = section_defs or DEFAULT_SECTIONS

        produced: list[dict[str, Any]] = []
        for index, section in enumerate(sections):
            key = section.get("key")
            if on_section_start is not None:
                try:
                    await on_section_start({"section_key": key, "section_title": section.get("title")})
                except Exception:
                    logger.exception("on_section_start callback failed for %s", key)
            payload = await self._write_section(
                section=section,
                requirements=requirements,
                context=context,
                chunk_map=chunk_map,
                title=title,
                tender_number=tender_number,
            )
            produced.append(payload)
            if on_section is not None:
                try:
                    await on_section(payload)
                except Exception:
                    logger.exception("on_section callback failed for %s", key)
        return {"status": "ok", "sections": produced}

    # ── 单节生成 ──────────────────────────────────────────────────

    async def _write_section(
        self,
        *,
        section: dict[str, Any],
        requirements: list[dict[str, Any]],
        context: str,
        chunk_map: dict[str, str],
        title: str,
        tender_number: str | None,
    ) -> dict[str, Any]:
        key = section.get("key")
        prompt = self._section_prompt(section, requirements, context, title, tender_number)
        try:
            data = await generate_structured(
                self.llm,
                prompt,
                SECTION_SCHEMA,
                system_prompt=_WRITE_SYSTEM_PROMPT,
            )
            content = data.get("content") or ""
        except Exception as exc:
            logger.warning("bid write section %s failed: %s", key, exc)
            data = {}
            content = ""
        return {
            "section_key": key,
            "section_title": section.get("title"),
            "content": content,
            "evidence_chunk_ids": self._resolve_evidence(data.get("evidence_chunk_ids"), chunk_map),
            "error": None if content else "本节生成失败，请人工补充",
        }

    # ── 检索 ──────────────────────────────────────────────────────

    async def _retrieve_corpus(self, knowledge_base_ids: list[int], title: str) -> list[dict[str, str]]:
        queries = [title] if title else []
        queries += [
            "资质要求 资格条件",
            "评分办法 评分标准",
            "废标 否决投标 无效投标",
            "实质性响应 必须响应",
            "保证金 截止时间 开标",
            "商务 付款 履约 保修",
        ]
        pairs = [(kb_id, query) for kb_id in knowledge_base_ids or [] for query in queries]
        if not pairs:
            return []

        # 第十五轮 P1（R15-10）：检索之间相互独立，串行执行会把延迟放大为
        # 「查询数 × KB 数 × 单次检索耗时」（最多 7×N 次串行往返）。
        # 并发检索后按任务顺序合并——去重（首见优先）与 MAX_CHUNKS 截断
        # 语义与旧串行实现完全一致；信号量限制并发检索深度。
        semaphore = asyncio.Semaphore(_RETRIEVAL_CONCURRENCY)

        async def _retrieve_one(kb_id: int, query: str):
            async with semaphore:
                try:
                    return await self.retriever.retrieve(
                        query, knowledge_base_id=kb_id, top_k=RETRIEVE_TOP_K, enable_rewrite=False
                    )
                except Exception as exc:
                    logger.warning("bid write retrieval failed kb=%s query=%r: %s", kb_id, query, exc)
                    return None

        results = await asyncio.gather(*(_retrieve_one(kb_id, query) for kb_id, query in pairs))

        seen: dict[str, str] = {}
        merged: list[dict[str, str]] = []
        for result in results:
            if result is None:
                continue
            for item in result.results:
                chunk_id = str(item.metadata.get("chunk_id") or item.document_id)
                if chunk_id in seen or len(merged) >= MAX_CHUNKS:
                    continue
                seen[chunk_id] = chunk_id
                merged.append({"chunk_id": chunk_id, "content": item.content[:CHUNK_MAX_CHARS]})
        return merged

    @staticmethod
    def _build_context(corpus: list[dict[str, str]]) -> tuple[str, dict[str, str]]:
        parts: list[str] = []
        chunk_map: dict[str, str] = {}
        for i, chunk in enumerate(corpus):
            chunk_map[str(i)] = chunk["chunk_id"]
            parts.append(f"[{i}] {chunk['content']}")
        return "\n\n".join(parts), chunk_map

    @staticmethod
    def _resolve_evidence(indices, chunk_map: dict[str, str]):
        if not indices:
            return []
        resolved = []
        for index in indices:
            key = str(index)
            resolved.append(chunk_map.get(key, index))
        return resolved

    # ── Prompt ────────────────────────────────────────────────────

    @staticmethod
    def _section_prompt(
        section: dict[str, Any],
        requirements: list[dict[str, Any]],
        context: str,
        title: str,
        tender_number: str | None,
    ) -> str:
        key = section.get("key")
        section_title = section.get("title") or key
        header = f"项目：{title}"
        if tender_number:
            header += f"；招标编号：{tender_number}"

        # 按分节筛选相关需求
        relevant = []
        for req in requirements:
            category = req.get("category", "")
            if key == "commercial" and category in ("commercial", "disqualification_risk", "performance"):
                relevant.append(req)
            elif key == "technical" and category in ("technical", "performance"):
                relevant.append(req)
            elif key == "qualification" and category in ("qualification",):
                relevant.append(req)
            elif key == "format" and category in ("format", "disqualification_risk", "commercial"):
                relevant.append(req)
        req_lines = []
        for i, req in enumerate(relevant, 1):
            req_lines.append(f"{i}. [{req.get('category', '')}] {req.get('requirement', '')}")
            if req.get("source_clause"):
                req_lines.append(f"   依据：{req['source_clause']}")
        req_block = "\n".join(req_lines) if req_lines else "（本分节无直接需求，请按行业惯例组织内容）"

        return (
            f"{header}\n\n"
            f"请撰写标书分节「{section_title}」（section_key={key}），正文用 Markdown 结构。\n\n"
            f"本分节需回应的需求清单：\n{req_block}\n\n"
            f"以下是招标文件片段（编号 [N] 对应证据）：\n{context}\n\n"
            f"输出为符合给定 Schema 的 JSON，content 为完整分节正文。"
        )
