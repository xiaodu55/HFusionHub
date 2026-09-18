"""
流式业务工具路由回归测试。

覆盖 ``run_stream()`` → ``_run_stream_react()`` 中"检索上下文非空 **且** 命中
演示业务工具"的组合分支（react.py 的 enhanced_query 改写段）。该分支曾引用未
导入的 ``log``，必抛 NameError 并被外层兜底 except 转成 ``run_error`` 事件——
用户侧表现为：只要业务工具命中且知识库有召回，流式回答整体失败。
"""

import json

import pytest

from app.core.agent.execution_context import AgentExecutionContext
from app.core.agent.react import ReactAgent
from app.core.tools.registry import create_v1_registry

_QUERY = "帮我查询物流"
_RAW_CONTEXT = "[1] (语义匹配, 相似度: 0.90)\n物流时效说明：省内次日达。"
_SOURCES = [{"chunk_id": "c1", "document_id": "d1", "title": "物流", "excerpt": "省内次日达", "score": 0.9}]


class _StubResponse:
    def __init__(self, text: str):
        self.content = text
        self.token_count = 7
        self.model = "stub-model"


class _RecordingStubLLM:
    """返回固定终答并记录收到的消息，用于断言路由指令是否注入。"""

    model = "stub-model"

    def __init__(self, reply: str):
        self._reply = reply
        self.seen_messages: list = []

    async def chat(self, messages=None, temperature=0.7, **kwargs):
        self.seen_messages = list(messages or [])
        return _StubResponse(self._reply)

    async def chat_stream(self, messages=None, temperature=0.7, max_tokens=2048, **kwargs):
        self.seen_messages = list(messages or [])
        yield self._reply


def _make_agent(reply: str) -> tuple[ReactAgent, _RecordingStubLLM]:
    ctx = AgentExecutionContext(
        user_id=1,
        knowledge_base_id=1,
        permissions=frozenset({"knowledge_base:read"}),
        agent_run_id="stream-demo-route",
        mode="read_only",
        capability_profile="approval_write",
    )
    agent = ReactAgent(
        knowledge_base_id=1,
        tool_registry=create_v1_registry(1, agent_version="1.1"),
        execution_context=ctx,
        max_steps=3,
    )
    llm = _RecordingStubLLM(reply)
    # 意图固定为 None：避免分类器把该问句判成 chitchat 而走直答分支
    async def _no_intent(*args, **kwargs):
        return None

    async def _retrieved(*args, **kwargs):
        return (_RAW_CONTEXT, list(_SOURCES), 1, _RAW_CONTEXT, False, [1])

    agent._classify_intent_safely = _no_intent
    agent._retrieve_and_compress = _retrieved
    agent._get_llm = lambda: llm
    return agent, llm


async def _drain(agent: ReactAgent) -> tuple[list[str], list[dict]]:
    chunks: list[str] = []
    events: list[dict] = []
    async for chunk in agent.run_stream(query=_QUERY, history=[]):
        chunks.append(chunk)
        try:
            parsed = json.loads(chunk)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict):
            events.append(parsed)
    return chunks, events


@pytest.mark.asyncio
async def test_demo_tool_route_with_context_does_not_emit_run_error():
    agent, llm = _make_agent("Final Answer: 省内次日达。")
    chunks, events = await _drain(agent)

    run_errors = [e for e in events if e.get("event") == "run_error"]
    assert not run_errors, f"streaming route raised internally: {run_errors}"
    assert "省内次日达。" in "".join(chunks)


@pytest.mark.asyncio
async def test_demo_tool_route_injects_tool_instruction_into_prompt():
    """命中判据的证据：用户消息被改写为指名调用 query_order_logistics。"""
    agent, llm = _make_agent("Final Answer: 已提交查询。")
    await _drain(agent)

    user_turns = [m.content for m in llm.seen_messages if m.role == "user"]
    assert user_turns, "stub LLM never received a prompt"
    assert "query_order_logistics" in user_turns[-1], (
        "demo-tool route did not reach the enhanced_query rewrite"
    )
    # 路由命中时参考资料不应注入（RAG 上下文会让模型改用文字作答）
    assert "<reference_material>" not in user_turns[-1]
