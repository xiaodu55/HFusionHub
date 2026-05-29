"""废标风险自检工作流（P1-2 核心）。

对已写好的标书分节做三类核对：
  1. 确定性规则核对照   —— 保证金/截止时间/格式签章/资质证书等高频废标点
  2. 废标条款关键词对照 —— 招标文件明确的废标条款相关动作项是否在标书中体现
  3. LLM 语义检查       —— 实质性响应/评分点覆盖/条款遗漏（与规则结果合并）

产出 findings 列表（severity: critical|warning|info），供 Java 落库
bid_check_report 与前端 CheckReport 视图按严重度分组展示。critical 级
（如投标保证金缺失、明确废标条款未响应）必须人工确认后才能放行。

确定性规则优先：可测试、可解释，作为"废标自检"最可信的部分；
LLM 检查作为补充（引入语义覆盖），两者 evidence 均可回溯 chunk_id。
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from app.core.bid.extractor import extract_disqualification_clauses, extract_scoring_points
from app.core.llm import get_llm
from app.core.llm.structured_output import generate_structured
from app.core.rag.retriever import get_retriever

logger = logging.getLogger(__name__)

# ── 检索与上下文预算 ────────────────────────────────────────────────
MAX_CHUNKS = 20
CHUNK_MAX_CHARS = 1500
RETRIEVE_TOP_K = 4

# ── 高频废标点关键词：招标文件显式要求但标书未体现 → 触发 finding ─────
# topic -> (keyword, category, severity)
FORMAT_TOPICS: Dict[str, tuple[str, str, str]] = {
    "投标保证金": ("保证金", "bond", "warning"),
    "递交截止时间": ("截止", "deadline", "warning"),
    "开标时间": ("开标", "deadline", "warning"),
    "密封": ("密封", "format", "warning"),
    "盖章": ("盖章", "format", "info"),
    "签字": ("签字", "format", "info"),
    "正本": ("正本", "format", "info"),
    "份数": ("份数", "format", "info"),
    "授权委托书": ("授权委托书", "format", "info"),
    "营业执照": ("营业执照", "qualification", "info"),
    "资质证书": ("资质证书", "qualification", "info"),
    "项目负责人": ("项目负责人", "technical", "info"),
}

# 保证金金额：如「投标保证金：人民币 20 万元」「保证金 5 万元」
_BOND_AMOUNT_RE = re.compile(r"保证金[^。；;\n]{0,40}?(\d+(?:\.\d+)?)\s*(万元|元)")
# 截止时间：如「2026 年 6 月 18 日 9:30」「6 月 18 日 9 时 30 分」「6月18日9:30」
_DEADLINE_RE = re.compile(
    r"(?:投标文件|投标)?[^。；;\n]{0,20}?(?:递交|提交|送达)?[^。；;\n]{0,10}?截止[^。；;\n]{0,60}?"
    r"(\d{4}\s*年)?\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*(\d{1,2}\s*[:：时]\s*\d{1,2}(?:\s*分)?)?"
)
_STAR_RE = re.compile(r"★|\*")

CHECK_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["critical", "warning", "info"]},
                    "category": {
                        "type": "string",
                        "enum": ["disqualification", "substantive", "format", "bond", "deadline"],
                    },
                    "section_key": {"type": "string"},
                    "finding": {"type": "string"},
                    "evidence_chunk_ids": {"type": "array", "items": {"type": "string"}},
                    "suggested_fix": {"type": "string"},
                },
                "required": ["severity", "finding"],
            },
        }
    },
    "required": ["findings"],
}

_CHECK_SYSTEM_PROMPT = (
    "你是资深废标风险审查专家。请逐条对照招标文件要求审查标书草稿，找出会导致"
    "废标/否决/扣分的风险点。只报告有依据的问题，不臆测；证据引用格式 [N]。"
    "severity 分级：critical=不处理必废标（如保证金缺失、明确废标条款未响应）；"
    "warning=大概率扣分或可能废标；info=提示性建议。"
)

# 常见废标条款动作词（从条款原文中提取可检查的关键词）
_DISQUALIFICATION_ACTION_WORDS = (
    "密封", "盖章", "签字", "正本", "副本", "授权委托书", "资格证明",
    "有效报价", "实质性响应", "单价", "总价", "有效期",
)


class BidCheckWorkflow:
    """废标风险自检工作流：确定性规则 + LLM 语义检查。"""

    def __init__(self, llm=None, retriever=None):
        self.llm = llm or get_llm()
        self.retriever = retriever or get_retriever()

    async def run(
        self,
        *,
        project_id: int,
        title: str,
        tender_number: Optional[str],
        sections: List[Dict[str, Any]],
        knowledge_base_ids: List[int],
        requirements: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        corpus = await self._retrieve_corpus(knowledge_base_ids, title)
        context, chunk_map = self._build_context(corpus)
        drafts = {
            s.get("section_key", ""): (s.get("content") or "") for s in sections
        }
        draft_text = "\n".join(drafts.values())

        findings: List[Dict[str, Any]] = []
        # 1) 确定性规则
        findings.extend(self._deterministic_checks(context, draft_text, drafts))
        # 2) LLM 语义检查（上下文中含废标条款）
        if context:
            try:
                llm_findings = await self._llm_checks(
                    context, drafts, requirements, chunk_map, title, tender_number
                )
                findings.extend(llm_findings)
            except Exception as exc:
                logger.warning("bid check llm pass failed: %s", exc)

        summary = {
            "total": len(findings),
            "critical": sum(1 for f in findings if f.get("severity") == "critical"),
            "warning": sum(1 for f in findings if f.get("severity") == "warning"),
            "info": sum(1 for f in findings if f.get("severity") == "info"),
        }
        return {"status": "ok", "findings": findings, "summary": summary}

    # ── 确定性规则检查（核心、可测试）─────────────────────────────

    def _deterministic_checks(
        self, tender_text: str, draft_text: str, drafts: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        findings: List[Dict[str, Any]] = []
        if not tender_text:
            return findings

        # 1) 高频废标点：招标显式要求 → 标书未体现
        for topic, (keyword, category, severity) in FORMAT_TOPICS.items():
            if keyword in tender_text and keyword not in draft_text:
                findings.append({
                    "severity": severity,
                    "category": category,
                    "section_key": self._locate_section(drafts, keyword),
                    "finding": f"招标文件显式要求「{topic}」相关事项（含关键词「{keyword}」），"
                               f"但标书全文未体现，请核对补充",
                    "evidence_chunk_ids": [],
                    "suggested_fix": f"在相应分节补充「{topic}」内容并逐字核对招标要求",
                })

        # 2) 保证金金额
        bond_m = _BOND_AMOUNT_RE.search(tender_text)
        if bond_m:
            amount = bond_m.group(1) + bond_m.group(2)
            if "保证金" not in draft_text:
                findings.append({
                    "severity": "critical",
                    "category": "bond",
                    "section_key": self._locate_section(drafts, "商务"),
                    "finding": f"招标文件要求投标保证金 {amount}，标书未体现保证金金额/缴纳方式",
                    "evidence_chunk_ids": [],
                    "suggested_fix": "在商务标补充保证金金额、缴纳方式与缴纳时间，并附缴纳凭证",
                })

        # 3) 截止/开标时间
        deadline_m = _DEADLINE_RE.search(tender_text)
        if deadline_m:
            date_str = f"{deadline_m.group(2)}月{deadline_m.group(3)}日"
            if deadline_m.group(4):
                date_str += f" {deadline_m.group(4)}"
            if "截止" not in draft_text and "开标" not in draft_text:
                findings.append({
                    "severity": "critical",
                    "category": "deadline",
                    "section_key": None,
                    "finding": f"招标文件要求投标截止/开标时间约 {date_str}，标书未标注递交截止时间，"
                               f"存在超时递交废标风险",
                    "evidence_chunk_ids": [],
                    "suggested_fix": "在封面/授权书/商务标显式标注投标截止时间，并与物流/递交安排对齐",
                })

        # 4) 废标条款动作项
        for clause in extract_disqualification_clauses(tender_text):
            matched = [w for w in _DISQUALIFICATION_ACTION_WORDS if w in clause]
            if matched and not any(w in draft_text for w in matched):
                findings.append({
                    "severity": "warning",
                    "category": "disqualification",
                    "section_key": None,
                    "finding": f"废标条款涉及「{'/'.join(matched)}」，标书未体现对应处理，存在否决风险。"
                               f"条款原文：{clause[:80]}",
                    "evidence_chunk_ids": [],
                    "suggested_fix": f"在标书中落实「{'/'.join(matched)}」相关动作并逐条对照废标条款自检",
                })

        # 5) 实质性响应标记（★/实质性响应条款）
        if (_STAR_RE.search(tender_text) or "实质性响应" in tender_text) and (
            "★" not in draft_text and "实质性" not in draft_text
        ):
            findings.append({
                "severity": "warning",
                "category": "substantive",
                "section_key": None,
                "finding": "招标文件含实质性响应条款（★/实质性要求），标书未逐条标注★响应",
                "evidence_chunk_ids": [],
                "suggested_fix": "在技术/商务分节逐条标注★，并逐项给出实质性响应声明",
            })

        # 6) 评分点覆盖提示（info）
        for point in extract_scoring_points(tender_text):
            name = point.get("name", "")
            if name and len(name) >= 2 and name not in draft_text:
                findings.append({
                    "severity": "info",
                    "category": "format",
                    "section_key": self._locate_section(drafts, name),
                    "finding": f"评分项「{name}」在标书中未直接体现，可能影响该项得分",
                    "evidence_chunk_ids": [],
                    "suggested_fix": f"确认评分项「{name}」（满分 {point.get('max_score')} 分）已在对应分节充分响应",
                })
        return findings

    @staticmethod
    def _locate_section(drafts: Dict[str, str], keyword: str) -> Optional[str]:
        """粗定位关键词所在分节；找不到返回 None（项目级 finding）。"""
        for key, content in drafts.items():
            if content and keyword in content:
                return key
        return None

    # ── LLM 语义检查 ─────────────────────────────────────────────

    async def _llm_checks(
        self,
        context: str,
        drafts: Dict[str, str],
        requirements: Optional[List[Dict[str, Any]]],
        chunk_map: Dict[str, str],
        title: str,
        tender_number: Optional[str],
    ) -> List[Dict[str, Any]]:
        draft_block = "\n\n".join(
            f"### {key}\n{content[:4000]}" for key, content in drafts.items() if content
        ) or "（标书草稿为空）"
        req_block = ""
        if requirements:
            req_block = "\n".join(
                f"- [{r.get('category', '')}] {r.get('requirement', '')}"
                for r in requirements[:40]
            )
        prompt = (
            f"项目：{title}"
            + (f"；招标编号：{tender_number}" if tender_number else "")
            + "\n\n"
            + f"招标文件片段（编号 [N] 对应证据）：\n{context}\n\n"
            + (f"需求清单：\n{req_block}\n\n" if req_block else "")
            + f"标书草稿：\n{draft_block}\n\n"
            + "请对照招标要求审查标书草稿，输出发现的风险点（符合给定 Schema 的 JSON）。"
        )
        data = await generate_structured(
            self.llm, prompt, CHECK_SCHEMA, system_prompt=_CHECK_SYSTEM_PROMPT
        )
        findings = []
        for item in data.get("findings", []):
            item["evidence_chunk_ids"] = self._resolve_evidence(
                item.get("evidence_chunk_ids"), chunk_map
            )
            findings.append(item)
        return findings

    # ── 检索 ──────────────────────────────────────────────────────

    async def _retrieve_corpus(self, knowledge_base_ids: List[int], title: str) -> List[Dict[str, str]]:
        queries = [title] if title else []
        queries += [
            "废标 否决投标 无效投标 条款",
            "实质性响应 必须响应 ★",
            "保证金 截止时间 开标 密封",
            "格式 签章 份数 正本",
        ]
        seen: Dict[str, str] = {}
        merged: List[Dict[str, str]] = []
        for kb_id in knowledge_base_ids or []:
            for query in queries:
                try:
                    result = await self.retriever.retrieve(
                        query, knowledge_base_id=kb_id, top_k=RETRIEVE_TOP_K, enable_rewrite=False
                    )
                except Exception as exc:
                    logger.warning("bid check retrieval failed kb=%s query=%r: %s", kb_id, query, exc)
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

    @staticmethod
    def _resolve_evidence(indices, chunk_map: Dict[str, str]):
        if not indices:
            return []
        resolved = []
        for index in indices:
            key = str(index)
            resolved.append(chunk_map.get(key, index))
        return resolved
