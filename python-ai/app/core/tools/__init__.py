"""
Tools Module - Tool definitions and execution

Agent V1 whitelist: search_knowledge_base, read_chunk, list_document_chunks
Non-V1 tools (calculate, get_current_time, web_search) are available only when
the tool policy explicitly allows them.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Set
import json
import asyncio

from .search_tool import SearchTool
from .time_tool import TimeTool
from .calculator_tool import CalculatorTool
from .web_search_tool import WebSearchTool
from .read_chunk_tool import ReadChunkTool
from .list_document_chunks_tool import ListDocumentChunksTool


__all__ = ['get_tools', 'execute_tool', 'ToolExecutionPolicy',
           'SearchTool', 'TimeTool', 'CalculatorTool', 'WebSearchTool',
           'ReadChunkTool', 'ListDocumentChunksTool',
           'AGENT_V1_TOOL_NAMES']


# Agent V1 whitelist — only these tools may be invoked by the knowledge-base
# research agent.  Any tool not in this set is out of V1 scope.
AGENT_V1_TOOL_NAMES: Set[str] = {
    "search_knowledge_base",
    "read_chunk",
    "list_document_chunks",
}


class ToolPolicyError(ValueError):
    """A tool call did not satisfy the single-agent safety policy."""


@dataclass(frozen=True)
class ToolExecutionPolicy:
    """Allow only bounded, read-only tools and normalise their inputs."""

    allowed_names: Set[str]
    knowledge_base_id: Optional[int] = None
    timeout_seconds: float = 10.0
    max_search_results: int = 5
    max_input_characters: int = 512

    def normalize(self, tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name not in self.allowed_names:
            raise ToolPolicyError(f"tool_not_allowed:{tool_name}")
        if not isinstance(tool_input, dict):
            raise ToolPolicyError("invalid_tool_input")
        normalized = dict(tool_input)

        if tool_name == "search_knowledge_base":
            if not self.knowledge_base_id:
                raise ToolPolicyError("knowledge_base_required")
            normalized.pop("knowledge_base_id", None)
            query = str(normalized.get("query", "")).strip()
            if not query or len(query) > self.max_input_characters:
                raise ToolPolicyError("invalid_search_query")
            try:
                requested_top_k = int(normalized.get("top_k", self.max_search_results))
            except (TypeError, ValueError) as error:
                raise ToolPolicyError("invalid_top_k") from error
            normalized["query"] = query
            normalized["top_k"] = max(1, min(requested_top_k, self.max_search_results))

        elif tool_name == "read_chunk":
            if not self.knowledge_base_id:
                raise ToolPolicyError("knowledge_base_required")
            chunk_id = str(normalized.get("chunk_id", "")).strip()
            if not chunk_id or len(chunk_id) > 128:
                raise ToolPolicyError("invalid_chunk_id")
            normalized["chunk_id"] = chunk_id

        elif tool_name == "list_document_chunks":
            if not self.knowledge_base_id:
                raise ToolPolicyError("knowledge_base_required")
            try:
                doc_id = int(normalized.get("document_id", 0))
            except (TypeError, ValueError) as error:
                raise ToolPolicyError("invalid_document_id") from error
            if doc_id <= 0:
                raise ToolPolicyError("invalid_document_id")
            normalized["document_id"] = doc_id

        elif tool_name == "calculate":
            expression = str(normalized.get("expression", ""))
            if not expression or len(expression) > self.max_input_characters:
                raise ToolPolicyError("invalid_expression")
            normalized["expression"] = expression

        elif tool_name == "get_current_time":
            # No parameters to validate — the tool ignores all input.
            pass

        elif tool_name == "web_search":
            query = str(normalized.get("query", "")).strip()
            if not query or len(query) > self.max_input_characters:
                raise ToolPolicyError("invalid_search_query")
            try:
                mr = int(normalized.get("max_results", 5))
            except (TypeError, ValueError):
                mr = 5
            normalized["query"] = query
            normalized["max_results"] = max(1, min(mr, 10))

        elif normalized:
            raise ToolPolicyError("unexpected_tool_arguments")
        return normalized


def get_tools(
    knowledge_base_id: int = None,
    v1_only: bool = True,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Get list of available tools.

    When ``v1_only=True`` (default), only the three Agent V1 knowledge-base
    research tools are returned.  Callers that need the full suite (MCP server,
    non-agent use-cases) must explicitly pass ``v1_only=False``.

    Agent V1 whitelist: search_knowledge_base, read_chunk, list_document_chunks.

    Args:
        knowledge_base_id: Knowledge base ID for scoped tools.
        v1_only: If True (default), return only V1-whitelisted tools.

    Returns:
        List of tool definitions.
    """
    all_tools = [
        {
            "name": "search_knowledge_base",
            "description": "在知识库中搜索相关文档分块。返回最相关的结果及其相似度分数、文档来源和内容摘要。当用户询问特定知识或需要查找文档信息时使用。",
            "parameters": {
                "query": {
                    "type": "string",
                    "description": "搜索查询文本"
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回的结果数量，默认5，最大20",
                    "default": 5
                }
            },
            "instance": SearchTool(knowledge_base_id=knowledge_base_id)
        },
        {
            "name": "read_chunk",
            "description": "读取指定分块的完整文本内容。当搜索结果中的摘要不足以回答问题时，使用此工具获取分块全文。每次仅读取一个分块。",
            "parameters": {
                "chunk_id": {
                    "type": "string",
                    "description": "分块标识符，如 '4_chunk_0000'"
                }
            },
            "instance": ReadChunkTool(knowledge_base_id=knowledge_base_id)
        },
        {
            "name": "list_document_chunks",
            "description": "列出指定文档在知识库中的所有分块概览（含前200字摘要）。当需要了解某文档的整体结构或确定哪些分块值得深入阅读时使用。最多返回100条。",
            "parameters": {
                "document_id": {
                    "type": "integer",
                    "description": "文档 ID（数字）"
                }
            },
            "instance": ListDocumentChunksTool(knowledge_base_id=knowledge_base_id)
        },
        {
            "name": "get_current_time",
            "description": "获取当前日期和时间。当用户询问现在时间、日期时使用。",
            "parameters": {},
            "instance": TimeTool()
        },
        {
            "name": "calculate",
            "description": "执行数学计算。当用户需要计算数学表达式时使用。",
            "parameters": {
                "expression": {
                    "type": "string",
                    "description": "数学表达式，如 '2 + 3 * 4'"
                }
            },
            "instance": CalculatorTool()
        },
        {
            "name": "web_search",
            "description": "搜索互联网获取最新信息。当用户询问知识库之外的信息或需要实时数据时使用。",
            "parameters": {
                "query": {
                    "type": "string",
                    "description": "搜索查询文本"
                },
                "max_results": {
                    "type": "integer",
                    "description": "返回的最大结果数(1-10)",
                    "default": 5
                }
            },
            "instance": WebSearchTool()
        }
    ]

    if v1_only:
        return [t for t in all_tools if t["name"] in AGENT_V1_TOOL_NAMES]
    return all_tools



async def execute_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    tools: List[Dict[str, Any]],
    policy: Optional[ToolExecutionPolicy] = None,
) -> str:
    """
    Execute a tool.

    Args:
        tool_name: Name of the tool to execute.
        tool_input: Input parameters for the tool.
        tools: List of available tools.
        policy: Optional safety policy for input validation and timeout.

    Returns:
        Tool execution result as a JSON string.
    """
    try:
        safe_input = policy.normalize(tool_name, tool_input) if policy else tool_input
    except ToolPolicyError as error:
        return json.dumps({"error": f"工具调用被安全策略拒绝（{error}）"}, ensure_ascii=False)

    # Find the tool instance.
    tool_instance = None
    for tool in tools:
        if tool["name"] == tool_name:
            tool_instance = tool["instance"]
            break

    if tool_instance is None:
        return json.dumps({"error": f"工具 '{tool_name}' 不存在"}, ensure_ascii=False)

    try:
        # Execute the tool with optional timeout.
        if policy:
            result = await asyncio.wait_for(
                tool_instance.execute(**safe_input),
                timeout=max(0.1, policy.timeout_seconds),
            )
        else:
            result = await tool_instance.execute(**safe_input)

        # Always return JSON so the agent can parse the output reliably.
        if isinstance(result, (dict, list)):
            return json.dumps(result, ensure_ascii=False, indent=2)
        else:
            return json.dumps({"result": str(result)}, ensure_ascii=False)

    except asyncio.TimeoutError:
        return json.dumps({"error": "工具调用超时"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"工具执行错误：{str(e)}"}, ensure_ascii=False)
