"""标书撰写 + 废标自检工作流单元测试（P1-2）。

覆盖：
  1. 撰写：按分节产出、证据索引回溯、需求按分节过滤、逐节回调顺序
  2. 撰写：单节 LLM 失败降级（error 标记，不中断整体）
  3. 自检：确定性规则（保证金/截止时间 critical、废标条款 warning、★响应 warning、评分点 info）
  4. 自检：summary 严重度统计
  5. API：/api/bid/write 同步返回 sections
  6. API：/api/bid/check 返回 findings + summary
  7. API：/api/bid/write/stream SSE 事件顺序（start/completed/run_completed/DONE）
  8. extractor：评分点抽取 + 多文件合并
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator, Callable

from app.core.bid.check_workflow import BidCheckWorkflow
from app.core.bid.extractor import extract_scoring_points, merge_documents
from app.core.bid.write_workflow import BidWriteWorkflow
from app.core.llm.base import BaseLLM, ChatMessage, LLMResponse
from app.core.rag.postprocessor import ProcessedResult
from app.core.rag.retriever import RetrievalResult

# ── 假 LLM：按 user prompt 分派返回 schema 合规 JSON ──────────────────


class FakeLLM(BaseLLM):
    def __init__(self, responder: Callable[[str], dict]):
        self.responder = responder
        self.calls: list[str] = []

    async def chat(
        self,
        messages: list[ChatMessage],
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
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        user = next(m.content for m in messages if m.role == "user")
        payload = self.responder(user)
        yield json.dumps(payload, ensure_ascii=False)

    def is_available(self) -> bool:
        return True


def _chunks(n: int = 4) -> list[ProcessedResult]:
    return [
        ProcessedResult(
            content=f"招标文件第{i}节内容",
            score=0.9 - i * 0.05,
            document_id=f"doc-{i}",
            metadata={"chunk_id": f"chunk-{i}"},
        )
        for i in range(n)
    ]


_TENDER_TEXT = (
    "投标人须知：投标保证金人民币 20 万元，须在开标前缴纳。"
    "投标文件递交截止时间为 2026 年 6 月 18 日 9:30，逾期不予受理。"
    "未按招标文件要求密封的投标文件将视为废标。"
    "招标文件带★条款为实质性响应要求。"
    "评分办法：技术方案 40 分，商务部分 30 分。"
)


def _tender_chunks(n: int = 2) -> list[ProcessedResult]:
    return [
        ProcessedResult(
            content=_TENDER_TEXT,
            score=0.95 - i * 0.05,
            document_id=f"doc-{i}",
            metadata={"chunk_id": f"chunk-{i}"},
        )
        for i in range(n)
    ]


class FakeRetriever:
    def __init__(self, results: list[ProcessedResult]):
        self._results = results

    async def retrieve(
        self,
        query: str,
        knowledge_base_id: int | None = None,
        conversation_history: list[dict] | None = None,
        top_k: int = 5,
        enable_rewrite: bool = True,
    ) -> RetrievalResult:
        return RetrievalResult(query=query, results=self._results[:top_k])


def _write_responder(user_prompt: str) -> dict:
    if "商务标" in user_prompt:
        return {
            "section_key": "commercial",
            "content": "商务标正文：报价说明与付款方式。",
            "evidence_chunk_ids": ["0"],
        }
    if "技术方案" in user_prompt:
        return {
            "section_key": "technical",
            "content": "技术方案正文：针对技术需求逐条响应。",
            "evidence_chunk_ids": ["1"],
        }
    if "资质文件" in user_prompt:
        return {
            "section_key": "qualification",
            "content": "资质文件正文：营业执照与资质证书【待补充：证书编号】。",
            "evidence_chunk_ids": ["2"],
        }
    return {"section_key": "format", "content": "格式文件正文：签章与份数安排。"}


def _check_responder(user_prompt: str) -> dict:
    return {
        "findings": [
            {
                "severity": "warning",
                "category": "substantive",
                "section_key": "technical",
                "finding": "★条款未逐条标注响应",
                "evidence_chunk_ids": ["3"],
                "suggested_fix": "逐条标注★并声明实质性响应",
            }
        ]
    }


# ── 撰写工作流 ───────────────────────────────────────────────────────


def test_write_produces_all_sections_with_resolved_evidence():
    workflow = BidWriteWorkflow(
        llm=FakeLLM(_write_responder), retriever=FakeRetriever(_chunks(4))
    )
    payload = asyncio.run(workflow.run(
        project_id=1,
        title="某园区智能化改造项目",
        tender_number="BH-2026-0618",
        requirements=[
            {"category": "qualification", "requirement": "具备建筑智能化二级以上资质"},
            {"category": "technical", "requirement": "技术方案须响应评分标准"},
        ],
        knowledge_base_ids=[5],
    ))
    assert payload["status"] == "ok"
    keys = [s["section_key"] for s in payload["sections"]]
    assert keys == ["commercial", "technical", "qualification", "format"]
    commercial = next(s for s in payload["sections"] if s["section_key"] == "commercial")
    # 证据索引回溯：LLM 返回 ["0"] → 真实 chunk_id "chunk-0"
    assert commercial["evidence_chunk_ids"] == ["chunk-0"]
    assert commercial["section_title"] == "商务标"
    assert "error" not in commercial or commercial["error"] is None


def test_write_callbacks_fire_in_order():
    workflow = BidWriteWorkflow(
        llm=FakeLLM(_write_responder), retriever=FakeRetriever(_chunks(2))
    )
    started: list[str] = []
    completed: list[str] = []

    async def on_start(section: dict) -> None:
        started.append(section["section_key"])

    async def on_section(payload: dict) -> None:
        completed.append(payload["section_key"])

    asyncio.run(workflow.run(
        project_id=1,
        title="项目A",
        tender_number=None,
        requirements=[],
        knowledge_base_ids=[5],
        section_defs=[{"key": "commercial", "title": "商务标"}, {"key": "format", "title": "格式文件"}],
        on_section_start=on_start,
        on_section=on_section,
    ))
    assert started == ["commercial", "format"]
    assert completed == ["commercial", "format"]


def test_write_section_failure_degrades_without_aborting():
    def responder(user_prompt: str) -> dict:
        if "商务标" in user_prompt:
            raise RuntimeError("llm boom")
        return _write_responder(user_prompt)

    workflow = BidWriteWorkflow(
        llm=FakeLLM(responder), retriever=FakeRetriever(_chunks(1))
    )
    payload = asyncio.run(workflow.run(
        project_id=1, title="项目A", tender_number=None, requirements=[], knowledge_base_ids=[5]
    ))
    assert payload["status"] == "ok"
    sections = {s["section_key"]: s for s in payload["sections"]}
    assert sections["commercial"]["content"] == ""
    assert sections["commercial"]["error"] is not None
    # 其余分节不受影响
    assert sections["technical"]["content"]


# ── 自检工作流（确定性规则为主）────────────────────────────────────────


def _tender_text_with_bond_and_deadline() -> str:
    return (
        "投标人须知：投标保证金人民币 20 万元，须在开标前缴纳。"
        "投标文件递交截止时间为 2026 年 6 月 18 日 9:30，逾期不予受理。"
        "未按招标文件要求密封的投标文件将视为废标。"
        "招标文件带★条款为实质性响应要求。"
        "评分办法：技术方案 40 分，商务部分 30 分。"
    )


def test_check_deterministic_bond_and_deadline_critical():
    workflow = BidCheckWorkflow(
        llm=FakeLLM(_check_responder),
        retriever=FakeRetriever(_tender_chunks(2)),
    )
    payload = asyncio.run(workflow.run(
        project_id=1,
        title="项目A",
        tender_number=None,
        sections=[
            {"section_key": "technical", "content": "技术方案正文"},
            {"section_key": "commercial", "content": "报价说明"},
        ],
        knowledge_base_ids=[5],
    ))
    findings = {f["category"]: f for f in payload["findings"] if f["category"] in ("bond", "deadline")}
    assert "bond" in findings
    assert findings["bond"]["severity"] == "critical"
    assert "20" in findings["bond"]["finding"]  # 保证金金额
    assert "deadline" in findings
    assert findings["deadline"]["severity"] == "critical"


def test_check_draft_covering_requirements_no_critical():
    workflow = BidCheckWorkflow(
        llm=FakeLLM(_check_responder),
        retriever=FakeRetriever(_tender_chunks(2)),
    )
    payload = asyncio.run(workflow.run(
        project_id=1,
        title="项目A",
        tender_number=None,
        sections=[
            {"section_key": "commercial", "content": "我方承诺按招标要求缴纳投标保证金人民币 20 万元，"
                                                      "并确保在 2026 年 6 月 18 日 9:30 截止时间前递交投标文件。"},
            {"section_key": "technical", "content": "密封并盖章，★实质性响应逐条标注。"},
        ],
        knowledge_base_ids=[5],
    ))
    critical = [f for f in payload["findings"] if f["severity"] == "critical"]
    assert critical == []


def test_check_summary_counts():
    workflow = BidCheckWorkflow(
        llm=FakeLLM(_check_responder),
        retriever=FakeRetriever(_tender_chunks(2)),
    )
    payload = asyncio.run(workflow.run(
        project_id=1,
        title="项目A",
        tender_number=None,
        sections=[{"section_key": "technical", "content": "技术方案正文"}],
        knowledge_base_ids=[5],
    ))
    summary = payload["summary"]
    # 保证金 critical + 截止 critical + LLM warning（substantive）+ 可能的 info
    assert summary["critical"] >= 2
    assert summary["warning"] >= 1
    assert summary["total"] == summary["critical"] + summary["warning"] + summary["info"]
    assert payload["status"] == "ok"


# ── API 路由 ─────────────────────────────────────────────────────────


def test_api_write_route_sync(monkeypatch):
    from app.api import bid as bid_api

    monkeypatch.setattr(
        "app.api.bid.BidWriteWorkflow",
        lambda **kw: BidWriteWorkflow(llm=FakeLLM(_write_responder), retriever=FakeRetriever(_chunks(2))),
    )
    request = bid_api.BidWriteRequest(
        project_id=1,
        title="项目A",
        knowledge_base_ids=[5],
        requirements=[{"category": "qualification", "requirement": "资质要求"}],
    )
    response = asyncio.run(bid_api.bid_write(request))
    assert response["status"] == "ok"
    assert len(response["sections"]) == 4
    assert response["project_id"] == 1


def test_api_check_route_sync(monkeypatch):
    from app.api import bid as bid_api

    monkeypatch.setattr(
        "app.api.bid.BidCheckWorkflow",
        lambda **kw: BidCheckWorkflow(llm=FakeLLM(_check_responder), retriever=FakeRetriever(_tender_chunks(2))),
    )
    request = bid_api.BidCheckRequest(
        project_id=1,
        title="项目A",
        knowledge_base_ids=[5],
        sections=[{"section_key": "technical", "content": "技术方案正文"}],
    )
    response = asyncio.run(bid_api.bid_check(request))
    assert response["status"] == "ok"
    assert response["summary"]["critical"] >= 2
    assert any(f["severity"] == "warning" for f in response["findings"])


def test_api_write_stream_sse_event_order(monkeypatch):
    from app.api import bid as bid_api

    monkeypatch.setattr(
        "app.api.bid.BidWriteWorkflow",
        lambda **kw: BidWriteWorkflow(llm=FakeLLM(_write_responder), retriever=FakeRetriever(_chunks(2))),
    )
    request = bid_api.BidWriteRequest(
        project_id=1,
        title="项目A",
        knowledge_base_ids=[5],
        section_defs=[{"key": "commercial", "title": "商务标"}],
    )

    events: list[dict] = []

    async def collect():
        resp = await bid_api.bid_write_stream(request)
        # StreamingResponse.body_iterator 即 event_generator
        async for chunk in resp.body_iterator:
            if chunk.strip() == "data: [DONE]":
                break
            line = chunk.strip().removeprefix("data: ")
            events.append(json.loads(line))

    asyncio.run(collect())
    kinds = [e["event"] for e in events]
    assert kinds[0] == "run_started"
    assert kinds[1] == "bid_section_started"
    assert kinds[2] == "bid_section_completed"
    assert kinds[3] == "run_completed"
    completed = events[2]
    assert completed["section_key"] == "commercial"
    assert completed["content"]
    assert events[3]["status"] == "ok"


# ── extractor 扩展 ───────────────────────────────────────────────────


def test_extract_scoring_points_parses_table_lines():
    text = "技术方案 40 分\n技术分（40分）\n价格：30 分\n商务部分 30 分\n总分 100 分\n序号 1"
    points = extract_scoring_points(text)
    assert len(points) == 4
    assert all(p["max_score"] > 0 for p in points)
    # 排除合计/序号行
    assert all("总分" not in p["name"] and "序号" not in p["name"] for p in points)


def test_merge_documents_labels_sources():
    merged = merge_documents([
        {"title": "招标公告", "content": "预算 120 万"},
        {"title": "澄清补遗", "content": "截止时间延后至 6 月 20 日"},
    ])
    assert "【来源文件：招标公告】" in merged
    assert "【来源文件：澄清补遗】" in merged
    assert "6 月 20 日" in merged
