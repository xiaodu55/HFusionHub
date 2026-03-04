"""Agent V1 end-to-end contract tests.

Verifies:
- Non-streaming response JSON keys match the Java AiClient.ChatResponse contract.
- knowledge_base_id is REQUIRED on /api/agent/v1/chat.
- V1-whitelisted tools are the only tools available to ReactAgent.
- web_search is NOT callable in Agent V1.
- Status codes and source format are consistent.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.api.chat import router, ChatResponse, AgentV1Request
from app.core.tools import get_tools, AGENT_V1_TOOL_NAMES, ToolExecutionPolicy
from app.core.agent import ReactAgent, AgentResponse

# ---------------------------------------------------------------------------
# FastAPI test app
# ---------------------------------------------------------------------------

from fastapi import FastAPI
app = FastAPI()
app.include_router(router)
client = TestClient(app)


# ---------------------------------------------------------------------------
# 1. Response JSON key contract (Java AiClient.ChatResponse compat)
# ---------------------------------------------------------------------------

class TestResponseContract:
    """Every V1 non-streaming response MUST include the keys that Java's
    AiClient.ChatResponse Jackson mapper expects."""

    JAVA_REQUIRED_KEYS = {
        "content",       # AiClient.ChatResponse.content
        "model",         # AiClient.ChatResponse.model
        "token_count",   # AiClient.ChatResponse.tokenCount
        "sources",       # AiClient.ChatResponse.sources
    }

    V1_KEYS = {
        "answer", "status", "agent_run_id", "token_usage",
        "tool_calls_count", "style_used", "max_tool_steps",
        "error_detail", "failed_tool",
    }

    def test_chat_response_model_has_java_keys(self):
        """ChatResponse Pydantic model serialises all Java-compat keys."""
        resp = ChatResponse(
            content="test answer",
            answer="test answer",
            model="test-model",
            token_count=42,
            sources=[{"document_id": 1, "chunk_id": "1_chunk_0000"}],
            status="completed",
            agent_run_id="uuid-123",
            tool_calls_count=2,
            style_used="concise",
        )
        data = json.loads(resp.model_dump_json())
        for key in self.JAVA_REQUIRED_KEYS:
            assert key in data, f"Java-required key '{key}' missing from ChatResponse JSON"
        # content and answer must be present and equal.
        assert data["content"] == "test answer"
        assert data["answer"] == "test answer"

    def test_chat_response_model_has_v1_keys(self):
        """ChatResponse serialises all V1 keys."""
        resp = ChatResponse(
            content="v1 test",
            answer="v1 test",
            status="insufficient_evidence",
            agent_run_id="run-1",
            token_usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            tool_calls_count=0,
            style_used="report",
            max_tool_steps=5,
            error_detail=None,
            failed_tool=None,
        )
        data = json.loads(resp.model_dump_json())
        for key in self.V1_KEYS:
            assert key in data, f"V1 key '{key}' missing from ChatResponse JSON"

    def test_status_enum_values(self):
        """Status must be one of the four V1 values."""
        valid = {"completed", "insufficient_evidence", "tool_error", "timeout"}
        for status_val in valid:
            resp = ChatResponse(content="ok", answer="ok", status=status_val)
            data = json.loads(resp.model_dump_json())
            assert data["status"] == status_val

    def test_sources_format(self):
        """Each source entry must have document_id, chunk_id, title, excerpt, score."""
        source = {
            "document_id": 4,
            "chunk_id": "4_chunk_0000",
            "title": "财务报告.pdf",
            "excerpt": "营收达到12.8亿元...",
            "score": 0.923,
        }
        resp = ChatResponse(content="ok", answer="ok", sources=[source])
        data = json.loads(resp.model_dump_json())
        assert len(data["sources"]) == 1
        s = data["sources"][0]
        assert s["document_id"] == 4
        assert s["chunk_id"] == "4_chunk_0000"
        assert "title" in s
        assert "excerpt" in s
        assert "score" in s


# ---------------------------------------------------------------------------
# 2. knowledge_base_id enforcement
# ---------------------------------------------------------------------------

class TestKnowledgeBaseIdRequired:
    """Agent V1 endpoint MUST reject requests without knowledge_base_id."""

    def test_agent_v1_request_validates_kb_id(self):
        """AgentV1Request Pydantic model requires knowledge_base_id."""
        with pytest.raises(Exception):
            AgentV1Request(message="hello")  # missing knowledge_base_id

    def test_agent_v1_request_accepts_valid(self):
        """AgentV1Request with KB ID is valid."""
        req = AgentV1Request(message="hello", knowledge_base_id=1)
        assert req.knowledge_base_id == 1

    def test_agent_v1_endpoint_rejects_missing_kb(self):
        """POST /api/agent/v1/chat without knowledge_base_id → 422."""
        resp = client.post("/api/agent/v1/chat", json={"message": "hello"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 3. V1 tool whitelist
# ---------------------------------------------------------------------------

class TestV1ToolWhitelist:
    """Only search_knowledge_base, read_chunk, list_document_chunks are
    available to the Agent V1 ReactAgent, regardless of workflow flag."""

    def test_get_tools_v1_only_excludes_non_v1_tools(self):
        """get_tools(v1_only=True) returns exactly V1 tools."""
        tools = get_tools(knowledge_base_id=1, v1_only=True)
        names = {t["name"] for t in tools}
        assert names == AGENT_V1_TOOL_NAMES
        assert "web_search" not in names
        assert "calculate" not in names
        assert "get_current_time" not in names

    def test_get_tools_v1_only_includes_all_v1_tools(self):
        """All three V1 tools are present."""
        tools = get_tools(knowledge_base_id=1, v1_only=True)
        names = {t["name"] for t in tools}
        assert "search_knowledge_base" in names
        assert "read_chunk" in names
        assert "list_document_chunks" in names

    def test_react_agent_only_sees_v1_tools(self):
        """ReactAgent._get_tools() returns only V1 tools by default."""
        agent = ReactAgent(knowledge_base_id=1)
        tools = agent._get_tools()
        names = {t["name"] for t in tools}
        assert names == AGENT_V1_TOOL_NAMES
        assert "web_search" not in names

    def test_tool_policy_rejects_web_search(self):
        """web_search is rejected by the V1 ToolExecutionPolicy."""
        policy = ToolExecutionPolicy(
            allowed_names=AGENT_V1_TOOL_NAMES,
            knowledge_base_id=1,
        )
        with pytest.raises(ValueError, match="tool_not_allowed"):
            policy.normalize("web_search", {"query": "test"})

    def test_tool_policy_rejects_calculate(self):
        """calculate is rejected by the V1 ToolExecutionPolicy."""
        policy = ToolExecutionPolicy(
            allowed_names=AGENT_V1_TOOL_NAMES,
            knowledge_base_id=1,
        )
        with pytest.raises(ValueError, match="tool_not_allowed"):
            policy.normalize("calculate", {"expression": "1+1"})

    def test_v1_tools_are_normalized(self):
        """All three V1 tools pass normalization."""
        policy = ToolExecutionPolicy(
            allowed_names=AGENT_V1_TOOL_NAMES,
            knowledge_base_id=1,
        )
        # search_knowledge_base
        assert policy.normalize("search_knowledge_base", {"query": "test"}) == {
            "query": "test", "top_k": 5,
        }
        # read_chunk
        assert policy.normalize("read_chunk", {"chunk_id": "4_chunk_0000"}) == {
            "chunk_id": "4_chunk_0000",
        }
        # list_document_chunks
        assert policy.normalize("list_document_chunks", {"document_id": 4}) == {
            "document_id": 4,
        }


# ---------------------------------------------------------------------------
# 4. AgentResponse V1 fields
# ---------------------------------------------------------------------------

class TestAgentResponseV1:
    """AgentResponse dataclass must support all V1 fields."""

    def test_to_dict_includes_all_keys(self):
        resp = AgentResponse(
            content="final answer",
            answer="final answer",
            status="completed",
            sources=[{"document_id": 1, "chunk_id": "1_chunk_0000", "title": "doc", "excerpt": "...", "score": 0.9}],
            agent_run_id="run-123",
            token_count=100,
            token_usage={"prompt_tokens": 60, "completion_tokens": 40, "total_tokens": 100},
            tool_calls_count=2,
            style_used="detailed",
            max_tool_steps=5,
        )
        d = resp.to_dict()
        assert d["answer"] == "final answer"
        assert d["status"] == "completed"
        assert d["agent_run_id"] == "run-123"
        assert d["token_usage"]["total_tokens"] == 100
        assert d["tool_calls_count"] == 2
        assert d["style_used"] == "detailed"

    def test_content_answer_sync(self):
        """content and answer are always in sync via __post_init__."""
        resp = AgentResponse(content="hello")
        assert resp.answer == "hello"
        assert resp.content == "hello"

        resp2 = AgentResponse(answer="world")
        assert resp2.content == "world"
        assert resp2.answer == "world"

    def test_insufficient_evidence_response(self):
        """insufficient_evidence: sources empty, status correct."""
        resp = AgentResponse(
            content="未检索到足够依据",
            answer="未检索到足够依据",
            status="insufficient_evidence",
            sources=[],
            finish_reason="insufficient_evidence",
        )
        d = resp.to_dict()
        assert d["status"] == "insufficient_evidence"
        assert d["sources"] == []

    def test_tool_error_response(self):
        """tool_error includes error_detail and failed_tool."""
        resp = AgentResponse(
            content="服务暂时不可用",
            answer="服务暂时不可用",
            status="tool_error",
            error_detail="Milvus connection refused",
            failed_tool="search_knowledge_base",
        )
        d = resp.to_dict()
        assert d["status"] == "tool_error"
        assert d["error_detail"] == "Milvus connection refused"
        assert d["failed_tool"] == "search_knowledge_base"


# ---------------------------------------------------------------------------
# 5. AGENT_V1_TOOL_NAMES constant
# ---------------------------------------------------------------------------

def test_agent_v1_tool_names_is_exactly_three():
    """The V1 whitelist contains exactly three tools."""
    assert AGENT_V1_TOOL_NAMES == {"search_knowledge_base", "read_chunk", "list_document_chunks"}


# ---------------------------------------------------------------------------
# 6. End-to-end regression: /api/agent/v1/chat ↔ Java AiClient simulation
# ---------------------------------------------------------------------------

class TestAgentV1EndToEnd:
    """Simulate the exact request Java's AiClient.agentV1Chat() would send."""

    def test_v1_endpoint_returns_java_compat_keys(self):
        """Non-streaming V1 response includes all Java AiClient fields."""
        resp = client.post("/api/agent/v1/chat", json={
            "message": "测试问题",
            "knowledge_base_id": 1,
            "conversation_id": 1,
            "history": [],
            "stream": False,
            "style": "detailed",
            "max_tool_steps": 5,
            "request_id": "test-java-001",
        })
        assert resp.status_code == 200, f"V1 endpoint returned {resp.status_code}: {resp.text[:300]}"
        data = resp.json()

        # Java-compat keys must be present.
        for key in ("content", "model", "token_count", "sources", "steps", "auto_detected_kb_id"):
            assert key in data, f"Java key '{key}' missing"

        # V1 keys must be present.
        for key in ("answer", "status", "agent_run_id", "tool_calls_count", "style_used"):
            assert key in data, f"V1 key '{key}' missing"

        # content and answer must be equal.
        assert data["content"] == data["answer"], "content and answer must be identical"

        # model must NOT be "fallback".
        assert data["model"] != "fallback", f"model is fallback — Agent error: {data.get('error_detail', '')}"
        assert data["model"] != "", "model must not be empty"

        # status must be a valid V1 value.
        assert data["status"] in ("completed", "insufficient_evidence", "tool_error", "timeout"), \
            f"Invalid status: {data['status']}"

    def test_v1_endpoint_rejects_missing_kb_422(self):
        """Without knowledge_base_id, the V1 endpoint returns 422."""
        resp = client.post("/api/agent/v1/chat", json={
            "message": "hello",
            "history": [],
            "stream": False,
        })
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"

    def test_v1_endpoint_sources_have_canonical_format(self):
        """When sources are returned, each entry has document_id, chunk_id, title, excerpt, score."""
        resp = client.post("/api/agent/v1/chat", json={
            "message": "1785288404409",
            "knowledge_base_id": 1,
            "history": [],
            "stream": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        for source in data.get("sources", []):
            # Skip V1 metadata pseudo-entries.
            if source.get("_v1"):
                continue
            assert "document_id" in source, f"Missing document_id in source: {source}"
            assert "chunk_id" in source, f"Missing chunk_id in source: {source}"
            assert "title" in source, f"Missing title in source: {source}"
            assert "excerpt" in source, f"Missing excerpt in source: {source}"
            assert "score" in source, f"Missing score in source: {source}"

    def test_v1_chat_endpoint_still_works(self):
        """General /api/chat still works for backward compat."""
        resp = client.post("/api/chat", json={
            "message": "hello",
            "history": [],
            "stream": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "content" in data
        assert "model" in data
        assert data["model"] != "fallback"
