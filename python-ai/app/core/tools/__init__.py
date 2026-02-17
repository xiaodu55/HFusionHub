"""
Tools Module - Tool definitions and execution
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Set
import json
import asyncio

from .search_tool import SearchTool
from .time_tool import TimeTool
from .calculator_tool import CalculatorTool


__all__ = ['get_tools', 'execute_tool', 'ToolExecutionPolicy', 'SearchTool', 'TimeTool', 'CalculatorTool']


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
        elif tool_name == "calculate":
            expression = str(normalized.get("expression", ""))
            if not expression or len(expression) > self.max_input_characters:
                raise ToolPolicyError("invalid_expression")
            normalized["expression"] = expression
        elif normalized:
            raise ToolPolicyError("unexpected_tool_arguments")
        return normalized


def get_tools(
    knowledge_base_id: int = None,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Get list of available tools

    Args:
        knowledge_base_id: Knowledge base ID for search tool

    Returns:
        List of tool definitions
    """
    tools = [
        {
            "name": "search_knowledge_base",
            "description": "搜索知识库中的相关文档。当用户询问特定知识或需要查找文档信息时使用。",
            "parameters": {
                "query": {
                    "type": "string",
                    "description": "搜索查询文本"
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回的结果数量，默认5",
                    "default": 5
                }
            },
            "instance": SearchTool(knowledge_base_id=knowledge_base_id)
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
        }
    ]

    return tools


async def execute_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    tools: List[Dict[str, Any]],
    policy: Optional[ToolExecutionPolicy] = None,
) -> str:
    """
    Execute a tool

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        tools: List of available tools

    Returns:
        Tool execution result as string
    """
    try:
        safe_input = policy.normalize(tool_name, tool_input) if policy else tool_input
    except ToolPolicyError as error:
        return f"错误：工具调用被安全策略拒绝（{error}）"

    # Find the tool
    tool_instance = None
    for tool in tools:
        if tool["name"] == tool_name:
            tool_instance = tool["instance"]
            break

    if tool_instance is None:
        return f"错误：工具 '{tool_name}' 不存在"

    try:
        # Execute the tool
        if policy:
            result = await asyncio.wait_for(
                tool_instance.execute(**safe_input),
                timeout=max(0.1, policy.timeout_seconds),
            )
        else:
            result = await tool_instance.execute(**safe_input)

        # Convert result to string if needed
        if isinstance(result, dict):
            return json.dumps(result, ensure_ascii=False, indent=2)
        elif isinstance(result, list):
            return json.dumps(result, ensure_ascii=False, indent=2)
        else:
            return str(result)

    except asyncio.TimeoutError:
        return "工具执行错误：工具调用超时"
    except Exception as e:
        return f"工具执行错误：{str(e)}"
