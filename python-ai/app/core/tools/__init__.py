"""
Tools Module - Tool definitions and execution
"""

from typing import List, Dict, Any, Optional
import json

from .search_tool import SearchTool
from .time_tool import TimeTool
from .calculator_tool import CalculatorTool


__all__ = ['get_tools', 'execute_tool', 'SearchTool', 'TimeTool', 'CalculatorTool']


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
    tools: List[Dict[str, Any]]
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
        result = await tool_instance.execute(**tool_input)

        # Convert result to string if needed
        if isinstance(result, dict):
            return json.dumps(result, ensure_ascii=False, indent=2)
        elif isinstance(result, list):
            return json.dumps(result, ensure_ascii=False, indent=2)
        else:
            return str(result)

    except Exception as e:
        return f"工具执行错误：{str(e)}"
