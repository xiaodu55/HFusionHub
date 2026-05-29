"""招投标撰写/自检工作流离线评测门禁（P1-4）。

密闭环境（免模型 / 免数据库 / 免网络）跑通 ``BidWriteWorkflow`` 与
``BidCheckWorkflow``，对产出做**确定性校验**（子串匹配，无需 LLM）：

撰写场景（FakeLLM 按分节回显需求清单，FakeRetriever 命中招标语料）：
  - ``requirement_coverage``      已确认需求的关键事实是否被撰写内容覆盖
  - ``section_routing_accuracy``  需求是否被路由到预期分节（锁定
    ``write_workflow._section_prompt`` 的分节过滤逻辑）
  - ``section_completeness``      默认四节全部产出非空内容
  - ``citation_faithfulness``     分节 evidence_chunk_ids 是否全部指向真实语料 chunk

自检场景（确定性规则优先，FakeLLM 返回空 findings 以隔离规则层）：
  - ``bond_recall``               缺保证金 → critical(bond) 被捕获
  - ``deadline_recall``           缺截止时间 → critical(deadline) 被捕获
  - ``disqualification_recall``   缺密封 → warning(disqualification) 被捕获
  - ``substantive_recall``        缺 ★ 响应 → warning(substantive) 被捕获
  - ``false_positive_free``       合规草稿不产生任何 critical finding

全部指标阈值 1.0（确定性规则，可复现）。任一不达标即阻断，
保证 ``bid_*`` 改动必须过此门禁（CI eval-offline job 调用）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import AsyncGenerator, Callable, Dict, List, Optional

from app.core.bid.check_workflow import BidCheckWorkflow
from app.core.bid.write_workflow import BidWriteWorkflow
from app.core.llm.base import BaseLLM, ChatMessage, LLMResponse
from app.core.rag.postprocessor import ProcessedResult
from app.core.rag.retriever import RetrievalResult

logger = logging.getLogger(__name__)

# ── 合成招标语料（3 个 chunk，覆盖保证金/截止/密封/★/评分点）────────────
TENDER_CHUNKS_TEXT: List[str] = [
    "投标人须知：投标保证金人民币 20 万元，须在开标前缴纳。"
    "投标文件递交截止时间为 2026 年 6 月 18 日 9:30，逾期不予受理。",
    "未按招标文件要求密封的投标文件将视为废标。"
    "招标文件带★条款为实质性响应要求，投标人须逐条响应并标注。",
    "评分办法：本项目采用综合评分法。技术方案 40 分，商务部分 30 分，总分 100 分。",
]

# ── 撰写场景：已确认需求清单 ───────────────────────────────────────────
# (requirement_key_phrase, category, 期望路由分节)
CONFIRMED_REQUIREMENTS: List[Dict[str, str]] = [
    {"category": "qualification", "requirement": "投标人须具备建筑智能化工程专业承包资质二级以上"},
    {"category": "performance", "requirement": "近三年须有至少两项合同金额不低于 500 万元的同类业绩"},
    {"category": "technical", "requirement": "施工组织设计方案须满足评分标准并逐条响应"},
    {"category": "commercial", "requirement": "报价须在预算上限 1260 万元以内并附报价明细"},
    {"category": "format", "requirement": "投标文件须按正本一份副本四份密封并加盖公章"},
]

# 与 write_workflow._section_prompt 的分节过滤一致（锁定路由正确性）
EXPECTED_ROUTING: Dict[str, List[str]] = {
    "commercial": ["commercial", "disqualification_risk", "performance"],
    "technical": ["technical", "performance"],
    "qualification": ["qualification"],
    "format": ["format", "disqualification_risk", "commercial"],
}


# ── 自检场景：植入风险的草稿（故意遗漏各废标点）─────────────────────────
RISKY_SECTIONS: List[Dict[str, str]] = [
    {"section_key": "commercial", "content": "报价说明与商务承诺。"},
    {"section_key": "technical", "content": "技术方案正文。"},
    {"section_key": "format", "content": "格式文件正文。"},
]

# 合规草稿：覆盖全部废标点，应零 critical
COMPLIANT_SECTIONS: List[Dict[str, str]] = [
    {
        "section_key": "commercial",
        "content": (
            "我方承诺按招标要求缴纳投标保证金人民币 20 万元，"
            "并确保在 2026 年 6 月 18 日 9:30 截止时间前递交投标文件。"
            "报价明细见附件，总价在预算上限 1260 万元以内。"
        ),
    },
    {
        "section_key": "technical",
        "content": "技术方案逐条响应评分标准，★条款均已标注实质性响应。",
    },
    {
        "section_key": "format",
        "content": "投标文件按正本一份副本四份准备，密封并加盖公章。",
    },
]


# ── 密闭 Fake 组件（与 tests/test_bid_write_check.py 同构）──────────────


class FakeLLM(BaseLLM):
    def __init__(self, responder: Callable[[str], Dict]):
        self.responder = responder

    async def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> LLMResponse:
        user = next(m.content for m in messages if m.role == "user")
        return LLMResponse(
            content=json.dumps(self.responder(user), ensure_ascii=False),
            model="fake",
            token_count=0,
            finish_reason="stop",
        )

    async def chat_stream(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        user = next(m.content for m in messages if m.role == "user")
        yield json.dumps(self.responder(user), ensure_ascii=False)

    def is_available(self) -> bool:
        return True


class FakeRetriever:
    """对任意查询都返回全部招标语料 chunk（检索行为不参与本门禁度量）。"""

    def __init__(self, chunks: List[ProcessedResult]):
        self._chunks = chunks
        self._content_by_chunk = {c.metadata.get("chunk_id"): c.content for c in chunks}

    async def retrieve(
        self,
        query: str,
        knowledge_base_id: Optional[int] = None,
        conversation_history: Optional[List[Dict]] = None,
        top_k: int = 5,
        enable_rewrite: bool = True,
    ) -> RetrievalResult:
        return RetrievalResult(query=query, results=self._chunks[:top_k])


def _tender_chunks() -> List[ProcessedResult]:
    return [
        ProcessedResult(
            content=TENDER_CHUNKS_TEXT[i],
            score=0.95 - i * 0.05,
            document_id=f"tender-{i}",
            metadata={"chunk_id": f"tender-chunk-{i}"},
        )
        for i in range(len(TENDER_CHUNKS_TEXT))
    ]


# ── 撰写场景 ────────────────────────────────────────────────────────────

_REQ_LINE_RE = re.compile(r"^\d+\.\s*\[([^\]]+)\]\s*(.+)$")


def _write_responder(user_prompt: str) -> Dict:
    """按分节回显 prompt 中列出的需求清单，证据引用上下文前两条。

    content 直接引用需求原文 → requirement_coverage / section_routing_accuracy
    度量撰写工作流"把哪些需求送进了哪个分节"，而非 LLM 的措辞能力。
    """
    req_lines = []
    for line in user_prompt.splitlines():
        m = _REQ_LINE_RE.match(line.strip())
        if m:
            req_lines.append(m.group(2).strip())
    body = "\n".join(f"- {r}" for r in req_lines) if req_lines else "本节无直接需求，按行业惯例组织。"
    return {
        "section_key": "placeholder",
        "content": f"# 本节正文\n\n{body}",
        "evidence_chunk_ids": ["0", "1"],
    }


def _run_write_scenario() -> Dict[str, float]:
    workflow = BidWriteWorkflow(
        llm=FakeLLM(_write_responder), retriever=FakeRetriever(_tender_chunks())
    )
    payload = asyncio.run(workflow.run(
        project_id=9001,
        title="滨海园区智能化改造项目",
        tender_number="BH-2026-0618",
        requirements=CONFIRMED_REQUIREMENTS,
        knowledge_base_ids=[201],
    ))
    sections = {s["section_key"]: s for s in payload["sections"]}

    corpus_ids = {f"tender-chunk-{i}" for i in range(len(TENDER_CHUNKS_TEXT))}

    # 1) 需求覆盖：每个需求的关键事实出现在任一分节
    coverage = sum(
        1 for req in CONFIRMED_REQUIREMENTS
        if any(req["requirement"] in s.get("content", "") for s in sections.values())
    ) / len(CONFIRMED_REQUIREMENTS)

    # 2) 分节路由：需求出现在其期望路由分节的内容中
    routed = 0
    for req in CONFIRMED_REQUIREMENTS:
        category = req["category"]
        expected_keys = [
            key for key, cats in EXPECTED_ROUTING.items() if category in cats
        ]
        if any(req["requirement"] in sections.get(key, {}).get("content", "")
               for key in expected_keys):
            routed += 1
    routing = routed / len(CONFIRMED_REQUIREMENTS)

    # 3) 分节完整：默认四节全部产出非空内容
    expected_keys = {"commercial", "technical", "qualification", "format"}
    completeness = sum(
        1 for key in expected_keys
        if sections.get(key, {}).get("content", "").strip()
    ) / len(expected_keys)

    # 4) 引用忠实：全部 evidence_chunk_ids 指向真实语料 chunk
    total_evidence = 0
    faithful_evidence = 0
    for s in sections.values():
        for chunk_id in s.get("evidence_chunk_ids", []):
            total_evidence += 1
            if chunk_id in corpus_ids:
                faithful_evidence += 1
    citation = faithful_evidence / total_evidence if total_evidence else 1.0

    return {
        "requirement_coverage": coverage,
        "section_routing_accuracy": routing,
        "section_completeness": completeness,
        "citation_faithfulness": citation,
    }


# ── 自检场景 ────────────────────────────────────────────────────────────


def _run_check_scenario() -> Dict[str, float]:
    # LLM 返回空 findings：仅度量确定性规则层（可复现的核心）
    workflow = BidCheckWorkflow(
        llm=FakeLLM(lambda _: {"findings": []}), retriever=FakeRetriever(_tender_chunks())
    )
    risky = asyncio.run(workflow.run(
        project_id=9001,
        title="滨海园区智能化改造项目",
        tender_number="BH-2026-0618",
        sections=RISKY_SECTIONS,
        knowledge_base_ids=[201],
    ))
    compliant = asyncio.run(workflow.run(
        project_id=9001,
        title="滨海园区智能化改造项目",
        tender_number="BH-2026-0618",
        sections=COMPLIANT_SECTIONS,
        knowledge_base_ids=[201],
    ))

    def has(severity: str, category: str) -> bool:
        return any(
            f.get("severity") == severity and f.get("category") == category
            for f in risky["findings"]
        )

    return {
        "bond_recall": 1.0 if has("critical", "bond") else 0.0,
        "deadline_recall": 1.0 if has("critical", "deadline") else 0.0,
        "disqualification_recall": 1.0 if has("warning", "disqualification") else 0.0,
        "substantive_recall": 1.0 if has("warning", "substantive") else 0.0,
        "false_positive_free": 1.0 if not any(
            f.get("severity") == "critical" for f in compliant["findings"]
        ) else 0.0,
    }


# ── 汇总与门槛 ──────────────────────────────────────────────────────────

GATE_THRESHOLDS: Dict[str, float] = {
    "requirement_coverage": 1.0,
    "section_routing_accuracy": 1.0,
    "section_completeness": 1.0,
    "citation_faithfulness": 1.0,
    "bond_recall": 1.0,
    "deadline_recall": 1.0,
    "disqualification_recall": 1.0,
    "substantive_recall": 1.0,
    "false_positive_free": 1.0,
}


def run_all() -> Dict[str, float]:
    """运行撰写 + 自检两个场景，返回全部指标。"""
    metrics = {}
    metrics.update(_run_write_scenario())
    metrics.update(_run_check_scenario())
    return metrics


def check_gates(metrics: Dict[str, float], thresholds: Optional[Dict[str, float]] = None) -> List[str]:
    """返回未达门槛的指标名列表（空=通过）。"""
    thresholds = thresholds or GATE_THRESHOLDS
    failures = []
    for key, threshold in thresholds.items():
        value = metrics.get(key)
        if value is None:
            failures.append(f"{key}: missing")
        elif value < threshold:
            failures.append(f"{key}: {value:.3f} < {threshold:.1f}")
    return failures
