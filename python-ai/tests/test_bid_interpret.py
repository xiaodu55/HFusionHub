"""招投标解读工作流单元测试（B2 垂直化）。

覆盖：
  1. 正常路径：多专家并发产出结构化要素，证据索引回溯为真实 chunk_id
  2. 评分办法规则交叉校验：语料出现"最低价法"特征时覆盖 LLM 判断
  3. 空语料兜底：返回 ok + warning，不抛异常
  4. 单专家失败降级：其余专家数据保留，warnings 携带失败原因
"""

from __future__ import annotations

import json
from typing import AsyncGenerator, Callable, Dict, List, Optional

import pytest

from app.core.bid.workflow import BidInterpretWorkflow
from app.core.llm.base import BaseLLM, ChatMessage, LLMResponse
from app.core.rag.retriever import RetrievalResult
from app.core.rag.postprocessor import ProcessedResult

# ── 假 LLM：按 user prompt 分派返回 schema 合规 JSON ──────────────────


class FakeLLM(BaseLLM):
    def __init__(self, responder: Callable[[str], Dict]):
        self.responder = responder
        self.calls: List[str] = []

    async def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> LLMResponse:
        user = next(m.content for m in messages if m.role == "user")
        self.calls.append(user)
        payload = self.responder(user)
        return LLMResponse(
            content=json.dumps(payload, ensure_ascii=False),
            model="fake",
            token_count=0,
            finish_reason="stop",
        )

    async def chat_stream(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        user = next(m.content for m in messages if m.role == "user")
        payload = self.responder(user)
        yield json.dumps(payload, ensure_ascii=False)

    def is_available(self) -> bool:
        return True


def _corpus_chunks(n: int = 4) -> List[ProcessedResult]:
    """构造 n 个带 chunk_id 的检索结果片段。"""
    return [
        ProcessedResult(
            content=f"招标文件第{i}节内容",
            score=0.9 - i * 0.05,
            document_id=f"doc-{i}",
            metadata={"chunk_id": f"chunk-{i}"},
        )
        for i in range(n)
    ]


class FakeRetriever:
    def __init__(self, results: List[ProcessedResult]):
        self._results = results

    async def retrieve(
        self,
        query: str,
        knowledge_base_id: Optional[int] = None,
        conversation_history: Optional[List[Dict]] = None,
        top_k: int = 5,
        enable_rewrite: bool = True,
    ) -> RetrievalResult:
        return RetrievalResult(query=query, results=self._results[:top_k])


def _default_responder(user_prompt: str) -> Dict:
    if "关键要素" in user_prompt:
        return {
            "elements": [
                {
                    "element_key": "budget",
                    "element_value": "1200000",
                    "confidence": 0.9,
                    "source_clause": "预算不超过120万元",
                    "evidence_chunk_ids": ["0"],
                },
                {
                    "element_key": "qualification_requirements",
                    "element_value": "具备建筑智能化二级以上资质",
                    "confidence": 0.9,
                    "source_clause": "资质要求见投标人须知",
                    "evidence_chunk_ids": ["1"],
                },
            ]
        }
    if "评分办法" in user_prompt:
        return {
            "scoring_methods": [
                {
                    "method_type": "comprehensive",
                    "total_score": 100,
                    "points": [{"name": "技术分", "max_score": 50}],
                    "evidence_chunk_ids": ["2"],
                }
            ]
        }
    # 需求清单 prompt 含"废标风险点"，必须先于废标分支匹配
    if "投标需求清单" in user_prompt:
        return {
            "requirements": [
                {
                    "category": "qualification",
                    "requirement": "须具备建筑智能化二级以上资质",
                    "source_clause": "资质要求",
                    "confidence": 0.9,
                }
            ]
        }
    if "废标" in user_prompt:
        return {
            "disqualification_clauses": [
                {
                    "clause": "投标报价超过预算上限的视为废标",
                    "risk_level": "critical",
                    "evidence_chunk_ids": ["3"],
                }
            ],
            "substantive_response_clauses": [
                {"clause": "投标文件须实质性响应招标要求", "evidence_chunk_ids": ["0"]}
            ],
        }
    return {"elements": []}


# ── 用例 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_interpret_produces_structured_payload_with_evidence():
    workflow = BidInterpretWorkflow(
        llm=FakeLLM(_default_responder), retriever=FakeRetriever(_corpus_chunks())
    )
    payload = await workflow.run(
        project_id=1, knowledge_base_id=1, title="某园区智能化改造项目", tender_number="XX-2026-001"
    )

    assert payload["status"] == "ok"
    # 要素：预算 + 资质 + 2 条废标/实质性条款
    assert len(payload["elements"]) == 4
    budget = next(e for e in payload["elements"] if e["element_key"] == "budget")
    # 证据索引回溯：["0"] → chunk-0
    assert budget["evidence_chunk_ids"] == ["chunk-0"]
    # 评分办法含 points_json
    assert payload["scoring_methods"][0]["method_type"] == "comprehensive"
    assert payload["scoring_methods"][0]["points_json"] == [{"name": "技术分", "max_score": 50}]
    # 需求清单
    assert payload["requirements"][0]["category"] == "qualification"
    # 无失败
    assert "warnings" not in payload


@pytest.mark.asyncio
async def test_interpret_scoring_method_rule_override():
    # 语料含"经评审的最低投标价法" → 规则判定 lowest_price，覆盖 LLM 的 comprehensive
    corpus = _corpus_chunks()
    corpus[0] = ProcessedResult(
        content="本项目采用经评审的最低投标价法进行评标",
        score=0.95,
        document_id="doc-0",
        metadata={"chunk_id": "chunk-0"},
    )
    workflow = BidInterpretWorkflow(
        llm=FakeLLM(_default_responder), retriever=FakeRetriever(corpus)
    )
    payload = await workflow.run(
        project_id=1, knowledge_base_id=1, title="某工程采购项目"
    )

    assert payload["status"] == "ok"
    assert payload["scoring_methods"][0]["method_type"] == "lowest_price"


@pytest.mark.asyncio
async def test_interpret_empty_corpus_returns_warning():
    workflow = BidInterpretWorkflow(llm=FakeLLM(_default_responder), retriever=FakeRetriever([]))
    payload = await workflow.run(project_id=1, knowledge_base_id=1, title="无内容项目")

    assert payload["status"] == "ok"
    assert "warning" in payload
    assert payload["elements"] == []
    assert payload["scoring_methods"] == []
    assert payload["requirements"] == []


@pytest.mark.asyncio
async def test_interpret_single_expert_failure_degrades_gracefully():
    def flaky_responder(user_prompt: str) -> Dict:
        if "评分办法" in user_prompt:
            raise RuntimeError("scoring LLM unavailable")
        return _default_responder(user_prompt)

    workflow = BidInterpretWorkflow(
        llm=FakeLLM(flaky_responder), retriever=FakeRetriever(_corpus_chunks())
    )
    payload = await workflow.run(project_id=1, knowledge_base_id=1, title="某项目")

    assert payload["status"] == "ok"
    # 评分办法专家失败但其余数据保留
    assert len(payload["elements"]) == 4
    assert payload["requirements"][0]["category"] == "qualification"
    assert payload["scoring_methods"] == []
    # 失败原因进入 warnings
    assert "warnings" in payload
    assert "scoring_method" in payload["warnings"]
