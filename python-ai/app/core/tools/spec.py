"""ToolSpec — unified tool description model for Agent V1.

Every tool MUST declare its name, input/output JSON Schema, timeout,
risk level, required permissions, and error codes.  The Tool Registry
uses these specs for validation, filtering, and documentation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── Risk levels ────────────────────────────────────────────────────────

class RiskLevel:
    READ_ONLY = "read_only"       # No side-effects; only reads KB data.
    READ_WRITE = "read_write"     # May modify state (NOT in V1).
    EXTERNAL = "external"         # Calls external services (NOT in V1).


# ── Permission constants ───────────────────────────────────────────────

class Permissions:
    KB_READ = "knowledge_base:read"
    KB_WRITE = "knowledge_base:write"
    SYSTEM_TIME = "system:time"
    EXTERNAL_HTTP = "external:http"


# ── Standard error codes ───────────────────────────────────────────────

class ErrorCode:
    TIMEOUT = "tool_timeout"
    SCOPE_DENIED = "knowledge_base_scope_denied"
    PERMISSION_DENIED = "permission_denied"
    INVALID_INPUT = "invalid_input"
    NOT_FOUND = "not_found"
    INTERNAL = "internal_error"
    EMPTY_RESULT = "empty_result"


@dataclass(frozen=True)
class ToolSpec:
    """Immutable, declarative description of a tool.

    Every tool registered in the Agent V1 Tool Registry must provide one
    of these.  The Registry uses the spec for:
      - Agent-version gating (``agent_version``)
      - Permission checks (``required_permissions``)
      - Input validation (``input_schema``)
      - Output documentation (``output_schema``)
      - Timeout enforcement (``timeout_seconds``)
    """

    name: str
    description: str
    input_schema: Dict[str, Any]    # JSON Schema (properties, required, …)
    output_schema: Dict[str, Any]   # JSON Schema for successful result
    risk_level: str = RiskLevel.READ_ONLY
    timeout_seconds: float = 10.0
    required_permissions: List[str] = field(default_factory=lambda: [Permissions.KB_READ])
    error_codes: Dict[str, str] = field(default_factory=lambda: {
        ErrorCode.TIMEOUT: "工具调用超时",
        ErrorCode.SCOPE_DENIED: "无权访问该知识库",
        ErrorCode.PERMISSION_DENIED: "权限不足，操作被拒绝",
        ErrorCode.INVALID_INPUT: "输入参数无效",
        ErrorCode.NOT_FOUND: "未找到请求的资源",
        ErrorCode.INTERNAL: "工具内部错误",
        ErrorCode.EMPTY_RESULT: "未检索到匹配结果",
    })
    agent_version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for LLM tool description."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.input_schema.get("properties", {}),
        }


# ── Predefined V1 tool specs ───────────────────────────────────────────

SEARCH_KB_SPEC = ToolSpec(
    name="search_knowledge_base",
    description=(
        "在知识库中搜索相关文档分块。返回最相关的结果及其相似度分数、"
        "文档来源和内容摘要。当用户询问特定知识或需要查找文档信息时使用。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索查询文本",
                "maxLength": 512,
            },
            "top_k": {
                "type": "integer",
                "description": "返回的结果数量",
                "default": 5,
                "minimum": 1,
                "maximum": 20,
            },
        },
        "required": ["query"],
    },
    output_schema={
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "分块内容摘要"},
                "score": {"type": "number", "description": "相似度分数 (0-1)"},
                "document_id": {"type": "integer"},
                "chunk_id": {"type": "string"},
                "title": {"type": "string", "description": "文档标题"},
            },
        },
    },
    risk_level=RiskLevel.READ_ONLY,
    timeout_seconds=10.0,
    required_permissions=[Permissions.KB_READ],
)

READ_CHUNK_SPEC = ToolSpec(
    name="read_chunk",
    description=(
        "读取指定分块的完整文本内容。当搜索结果中的摘要不足以回答问题时，"
        "使用此工具获取分块全文。每次仅读取一个分块。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "chunk_id": {
                "type": "string",
                "description": "分块标识符，如 '4_chunk_0000'",
                "maxLength": 128,
            },
        },
        "required": ["chunk_id"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "chunk_id": {"type": "string"},
            "content": {"type": "string", "description": "分块全文"},
            "document_id": {"type": "integer"},
            "title": {"type": "string"},
            "block_type": {"type": "string"},
        },
    },
    risk_level=RiskLevel.READ_ONLY,
    timeout_seconds=5.0,
    required_permissions=[Permissions.KB_READ],
)

LIST_DOC_CHUNKS_SPEC = ToolSpec(
    name="list_document_chunks",
    description=(
        "列出指定文档在知识库中的所有分块概览（含前200字摘要）。"
        "当需要了解某文档的整体结构或确定哪些分块值得深入阅读时使用。"
        "最多返回100条。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "document_id": {
                "type": "integer",
                "description": "文档 ID（数字）",
                "minimum": 1,
            },
        },
        "required": ["document_id"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "document_id": {"type": "integer"},
            "chunks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "chunk_id": {"type": "string"},
                        "excerpt": {"type": "string", "maxLength": 200},
                        "block_type": {"type": "string"},
                    },
                },
            },
            "total": {"type": "integer"},
            "truncated": {"type": "boolean"},
        },
    },
    risk_level=RiskLevel.READ_ONLY,
    timeout_seconds=5.0,
    required_permissions=[Permissions.KB_READ],
)

# ── Lookup ─────────────────────────────────────────────────────────────

V1_SPECS: Dict[str, ToolSpec] = {
    SEARCH_KB_SPEC.name: SEARCH_KB_SPEC,
    READ_CHUNK_SPEC.name: READ_CHUNK_SPEC,
    LIST_DOC_CHUNKS_SPEC.name: LIST_DOC_CHUNKS_SPEC,
}
