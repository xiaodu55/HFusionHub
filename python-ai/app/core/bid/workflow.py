"""招投标解读工作流（B2）。

以「招标文件知识库」为输入，多专家并发抽取结构化要素：
  1. 要素抽取专家   —— 招标编号/预算/资质要求/工期/保证金/币种/联系方式
  2. 评分办法专家   —— 综合评分法/最低价法 + 评分点（points）
  3. 废标条款专家   —— 废标条款 + 实质性响应条款
  4. 需求清单专家   —— 汇总为投标需求清单（资质/业绩/技术/商务/格式/废标风险）

复用平台多 Agent 协作基础设施（MultiAgentCoordinator + ExpertRole +
CallableExpertAgent）与 RAG 多路检索；每条要素携带 evidence_chunk_ids
（由上下文 [N] 索引回溯到真实 chunk_id），供 Java 落库与前端追溯。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from app.core.agent.collaboration import (
    CallableExpertAgent,
    CollaborationTask,
    ExpertContribution,
    ExpertRole,
    MultiAgentCoordinator,
)
from app.core.bid.extractor import detect_method_type
from app.core.llm import get_llm
from app.core.llm.structured_output import StructuredOutputError, generate_structured
from app.core.rag.retriever import get_retriever

logger = logging.getLogger(__name__)

# ── 检索与上下文预算 ────────────────────────────────────────────────
MAX_CHUNKS = 16
CHUNK_MAX_CHARS = 1500
RETRIEVE_TOP_K = 4
RETRIEVE_QUERIES = (
    "招标文件 资质要求 资格条件",
    "评分办法 评分标准 综合评分",
    "废标 否决投标 无效投标 条款",
    "工期 交货期 保证金 预算 开标",
)

# 并发检索深度（R15-10）
_RETRIEVAL_CONCURRENCY = 5

# ── JSON Schema（generate_structured 校验）─────────────────────────

ELEMENTS_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "elements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "element_key": {
                        "type": "string",
                        "enum": [
                            "tender_number",
                            "budget",
                            "qualification_requirements",
                            "deadline",
                            "bid_bond",
                            "bid_currency",
                            "contact",
                        ],
                    },
                    "element_value": {"type": "string"},
                    "confidence": {"type": "number"},
                    "source_clause": {"type": "string"},
                    "evidence_chunk_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["element_key", "element_value"],
            },
        }
    },
    "required": ["elements"],
}

SCORING_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "scoring_methods": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "method_type": {"type": "string", "enum": ["comprehensive", "lowest_price"]},
                    "total_score": {"type": "number"},
                    "points": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "max_score": {"type": "number"},
                                "weight": {"type": "number"},
                                "scoring_criteria": {"type": "string"},
                            },
                            "required": ["name", "max_score"],
                        },
                    },
                    "evidence_chunk_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["method_type"],
            },
        }
    },
    "required": ["scoring_methods"],
}

CLAUSES_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "disqualification_clauses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause": {"type": "string"},
                    "risk_level": {"type": "string", "enum": ["critical", "warning", "info"]},
                    "evidence_chunk_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["clause"],
            },
        },
        "substantive_response_clauses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause": {"type": "string"},
                    "evidence_chunk_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["clause"],
            },
        },
    },
    "required": ["disqualification_clauses", "substantive_response_clauses"],
}

REQUIREMENTS_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": [
                            "qualification",
                            "performance",
                            "technical",
                            "commercial",
                            "format",
                            "disqualification_risk",
                        ],
                    },
                    "requirement": {"type": "string"},
                    "source_clause": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["category", "requirement"],
            },
        }
    },
    "required": ["requirements"],
}

_SYSTEM_PROMPT = (
    "你是资深招投标咨询专家。请严格依据提供的招标文件片段作答："
    "只提取文件中有依据的信息，不臆测、不补充；无法确定时降低置信度并保留原文出处。"
    "引用格式：[N] 表示第 N 条证据片段，请在你的 evidence_chunk_ids 中列出所依据的编号。"
)


class BidInterpretWorkflow:
    """招投标解读工作流：多专家并发抽取结构化要素。"""

    def __init__(self, llm=None, retriever=None):
        self.llm = llm or get_llm()
        self.retriever = retriever or get_retriever()

    async def run(
        self,
        *,
        project_id: int,
        knowledge_base_id: int,
        title: str,
        tender_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        corpus = await self._retrieve_corpus(knowledge_base_id, title)
        if not corpus:
            return {
                "status": "ok",
                "warning": "未检索到招标文件内容，请确认知识库已完成向量化",
                "elements": [],
                "scoring_methods": [],
                "requirements": [],
            }

        context, chunk_map = self._build_context(corpus)
        task = CollaborationTask(
            query=title or "招标文件解读",
            context={
                "context": context,
                "chunk_map": chunk_map,
                "title": title,
                "tender_number": tender_number,
            },
        )

        coordinator = MultiAgentCoordinator(
            experts=[
                CallableExpertAgent(ExpertRole.ELEMENT_EXTRACTION, self._expert_elements),
                CallableExpertAgent(ExpertRole.SCORING_METHOD, self._expert_scoring),
                CallableExpertAgent(ExpertRole.CLAUSE_EXTRACTION, self._expert_clauses),
                CallableExpertAgent(ExpertRole.REQUIREMENT_SYNTHESIS, self._expert_requirements),
            ],
            synthesizer=self._synthesize,
            max_concurrency=4,
        )
        result = await coordinator.collaborate(task)

        payload = self._assemble(result, chunk_map)
        payload["status"] = "ok"
        if result.errors:
            payload["warnings"] = {
                role.value: msg for role, msg in result.errors.items()
            }
        return payload

    # ── 检索 ──────────────────────────────────────────────────────

    async def _retrieve_corpus(self, knowledge_base_id: int, title: str) -> List[Dict[str, str]]:
        queries = list(RETRIEVE_QUERIES)
        if title:
            queries.append(title)

        # 第十五轮 P1（R15-10）：检索相互独立，并发执行 + 按任务顺序合并——
        # 去重（首见优先）与 MAX_CHUNKS 截断语义与旧串行实现完全一致。
        semaphore = asyncio.Semaphore(_RETRIEVAL_CONCURRENCY)

        async def _retrieve_one(query: str):
            async with semaphore:
                try:
                    return await self.retriever.retrieve(
                        query, knowledge_base_id=knowledge_base_id, top_k=RETRIEVE_TOP_K, enable_rewrite=False
                    )
                except Exception as exc:  # 单次检索失败不影响整体
                    logger.warning("bid retrieval failed for query=%r: %s", query, exc)
                    return None

        results = await asyncio.gather(*(_retrieve_one(query) for query in queries))

        seen: Dict[str, str] = {}
        merged: List[Dict[str, str]] = []
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
    def _build_context(corpus: List[Dict[str, str]]) -> tuple[str, Dict[str, str]]:
        parts: List[str] = []
        chunk_map: Dict[str, str] = {}
        for i, chunk in enumerate(corpus):
            chunk_map[str(i)] = chunk["chunk_id"]
            parts.append(f"[{i}] {chunk['content']}")
        return "\n\n".join(parts), chunk_map

    # ── 专家 ──────────────────────────────────────────────────────

    async def _structured_with_empty_retry(self, prompt: str, schema: Dict[str, Any],
                                           list_key: str) -> Dict[str, Any]:
        """generate_structured 只重试格式错误；schema 合法但列表为空的
        LLM 偶发输出（smoke-bid 曾因此间歇失败）在这里补一次重试。"""
        data = await generate_structured(self.llm, prompt, schema, system_prompt=_SYSTEM_PROMPT)
        if not data.get(list_key):
            logger.warning("bid expert returned empty %r; retrying once with higher temperature", list_key)
            data = await generate_structured(
                self.llm, prompt, schema,
                system_prompt=_SYSTEM_PROMPT, temperature=0.6,
            )
        return data

    async def _expert_elements(self, task: CollaborationTask) -> ExpertContribution:
        data = await self._structured_with_empty_retry(
            self._prompt(task, "请提取招标文件中的关键要素（招标编号/预算/资质要求/工期/保证金/币种/联系方式）。"),
            ELEMENTS_SCHEMA, "elements",
        )
        return ExpertContribution(
            role=ExpertRole.ELEMENT_EXTRACTION,
            content="要素抽取完成",
            metadata={"data": data.get("elements", [])},
        )

    async def _expert_scoring(self, task: CollaborationTask) -> ExpertContribution:
        data = await generate_structured(
            self.llm,
            self._prompt(task, "请解析招标文件中的评分办法：评分方式（综合评分法/最低价法）、评分点及分值、满分。"),
            SCORING_SCHEMA,
            system_prompt=_SYSTEM_PROMPT,
        )
        methods = data.get("scoring_methods", [])
        # 规则交叉校验评分方式：从原始语料识别（LLM 误判为综合评分法、
        # 但文本出现明确"最低价"特征时，以规则为准——最低价法特征决定性）
        rule = detect_method_type(task.context.get("context") or "")
        for method in methods:
            if rule == "lowest_price" and method.get("method_type") != "lowest_price":
                logger.info("bid scoring method corrected by rule -> lowest_price")
                method["method_type"] = "lowest_price"
            method["points_json"] = method.pop("points", method.get("points_json"))
        return ExpertContribution(
            role=ExpertRole.SCORING_METHOD,
            content="评分办法解析完成",
            metadata={"data": methods},
        )

    async def _expert_clauses(self, task: CollaborationTask) -> ExpertContribution:
        data = await generate_structured(
            self.llm,
            self._prompt(task, "请提取招标文件中的废标/否决投标条款与实质性响应条款（原文），并标注风险级别。"),
            CLAUSES_SCHEMA,
            system_prompt=_SYSTEM_PROMPT,
        )
        elements = []
        for item in data.get("disqualification_clauses", []):
            elements.append({
                "element_key": "disqualification_clauses",
                "element_value": item.get("clause", ""),
                "confidence": 0.8,
                "source_clause": item.get("clause", ""),
                "evidence_chunk_ids": item.get("evidence_chunk_ids", []),
                "risk_level": item.get("risk_level", "warning"),
            })
        for item in data.get("substantive_response_clauses", []):
            elements.append({
                "element_key": "substantive_response_clauses",
                "element_value": item.get("clause", ""),
                "confidence": 0.8,
                "source_clause": item.get("clause", ""),
                "evidence_chunk_ids": item.get("evidence_chunk_ids", []),
            })
        return ExpertContribution(
            role=ExpertRole.CLAUSE_EXTRACTION,
            content="废标条款提取完成",
            metadata={"data": elements},
        )

    async def _expert_requirements(self, task: CollaborationTask) -> ExpertContribution:
        data = await self._structured_with_empty_retry(
            self._prompt(task, "请汇总投标需求清单：资质、业绩、技术、商务、格式要求以及废标风险点。"),
            REQUIREMENTS_SCHEMA, "requirements",
        )
        return ExpertContribution(
            role=ExpertRole.REQUIREMENT_SYNTHESIS,
            content="需求清单汇总完成",
            metadata={"data": data.get("requirements", [])},
        )

    @staticmethod
    def _prompt(task: CollaborationTask, instruction: str) -> str:
        ctx = task.context
        title = ctx.get("title") or ""
        tender_number = ctx.get("tender_number") or ""
        header = f"项目：{title}"
        if tender_number:
            header += f"；招标编号：{tender_number}"
        return (
            f"{header}\n\n"
            f"请完成以下任务：\n{instruction}\n\n"
            f"以下是招标文件片段（编号 [N] 对应证据）：\n{ctx['context']}\n\n"
            f"输出为符合给定 Schema 的 JSON。"
        )

    @staticmethod
    async def _synthesize(task: CollaborationTask) -> ExpertContribution:
        contributions: List[ExpertContribution] = task.context.get("contributions", [])
        summary = "；".join(
            f"{c.role.value}: {c.content}" for c in contributions if c.succeeded
        )
        return ExpertContribution(
            role=ExpertRole.SYNTHESIS, content=summary or "无成功贡献"
        )

    # ── 汇总 ──────────────────────────────────────────────────────

    @staticmethod
    def _assemble(result, chunk_map: Dict[str, str]) -> Dict[str, Any]:
        elements: List[Dict[str, Any]] = []
        scoring_methods: List[Dict[str, Any]] = []
        requirements: List[Dict[str, Any]] = []
        for contribution in result.contributions:
            if not contribution.succeeded:
                continue
            data = contribution.metadata.get("data", [])
            if contribution.role == ExpertRole.ELEMENT_EXTRACTION:
                elements.extend(data)
            elif contribution.role == ExpertRole.CLAUSE_EXTRACTION:
                elements.extend(data)
            elif contribution.role == ExpertRole.SCORING_METHOD:
                scoring_methods.extend(data)
            elif contribution.role == ExpertRole.REQUIREMENT_SYNTHESIS:
                requirements.extend(data)
        # 证据索引回溯：["0","3"] → [chunk_id0, chunk_id3]
        for element in elements:
            element["evidence_chunk_ids"] = BidInterpretWorkflow._resolve_evidence(
                element.get("evidence_chunk_ids"), chunk_map
            )
        for method in scoring_methods:
            method["evidence_chunk_ids"] = BidInterpretWorkflow._resolve_evidence(
                method.get("evidence_chunk_ids"), chunk_map
            )
        return {
            "elements": elements,
            "scoring_methods": scoring_methods,
            "requirements": requirements,
        }

    @staticmethod
    def _resolve_evidence(indices, chunk_map: Dict[str, str]):
        if not indices:
            return []
        resolved = []
        for index in indices:
            key = str(index)
            resolved.append(chunk_map.get(key, index))
        return resolved
