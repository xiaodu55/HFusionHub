"""
ReAct Agent Implementation
Implements Reasoning + Acting loop for complex tasks
"""

import json
import re
from typing import List, Dict, Any, Optional, AsyncGenerator

from .agent import Agent, AgentResponse, AgentStep
from ..llm import get_llm, ChatMessage, BaseLLM
from ..tools import get_tools, execute_tool


# System prompt for ReAct agent
REACT_SYSTEM_PROMPT = """你是一个智能助手，能够使用工具来回答问题。

你可以使用以下工具：
{tools_description}

请使用以下格式回答问题：

Thought: 我需要思考如何回答这个问题
Action: 工具名称
Action Input: {{"参数名": "参数值"}}
Observation: 工具返回的结果（系统会自动填充）
... (可以重复 Thought/Action/Observation 多次)
Thought: 我现在知道了答案
Final Answer: 最终答案

重要提示：
1. 每次只能执行一个 Action
2. Action Input 必须是 JSON 格式
3. 如果不需要使用工具，直接给出 Final Answer
4. Final Answer 应该是完整的、有帮助的回答
"""


class ReactAgent(Agent):
    """ReAct Agent implementation"""

    def __init__(
        self,
        knowledge_base_id: int = None,
        model: str = None,
        max_steps: int = 5,
        **kwargs
    ):
        self.knowledge_base_id = knowledge_base_id
        self.model = model
        self.max_steps = max_steps
        self.llm: BaseLLM = None
        self.tools: List[Dict[str, Any]] = []

    def _get_llm(self) -> BaseLLM:
        """Get LLM instance (lazy initialization)"""
        if self.llm is None:
            self.llm = get_llm(model=self.model)
        return self.llm

    def _get_tools(self) -> List[Dict[str, Any]]:
        """Get available tools"""
        if not self.tools:
            self.tools = get_tools(knowledge_base_id=self.knowledge_base_id)
        return self.tools

    def _format_tools_description(self) -> str:
        """Format tools description for system prompt"""
        tools = self._get_tools()
        if not tools:
            return "没有可用的工具"

        descriptions = []
        for tool in tools:
            desc = f"- {tool['name']}: {tool['description']}"
            if 'parameters' in tool:
                params = json.dumps(tool['parameters'], ensure_ascii=False, indent=2)
                desc += f"\n  参数: {params}"
            descriptions.append(desc)

        return "\n".join(descriptions)

    def _parse_action(self, text: str) -> Optional[tuple]:
        """Parse action and action input from text"""
        # Find Action
        action_match = re.search(r'Action:\s*(.+?)(?:\n|$)', text)
        if not action_match:
            return None

        action = action_match.group(1).strip()

        # Find Action Input
        input_match = re.search(r'Action Input:\s*(\{.+?\})(?:\n|$)', text, re.DOTALL)
        if not input_match:
            return None

        try:
            action_input = json.loads(input_match.group(1))
        except json.JSONDecodeError:
            return None

        return action, action_input

    def _parse_final_answer(self, text: str) -> Optional[str]:
        """Parse final answer from text"""
        match = re.search(r'Final Answer:\s*(.+)', text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    async def run(
        self,
        query: str,
        history: List[Dict[str, str]] = None,
        **kwargs
    ) -> AgentResponse:
        """Run ReAct agent"""
        llm = self._get_llm()
        tools = self._get_tools()

        # Build system prompt
        system_prompt = REACT_SYSTEM_PROMPT.format(
            tools_description=self._format_tools_description()
        )

        # Build messages
        messages = [ChatMessage(role="system", content=system_prompt)]

        # Add history
        if history:
            for msg in history[-10:]:  # Keep last 10 messages
                messages.append(ChatMessage(role=msg["role"], content=msg["content"]))

        # Add current query
        messages.append(ChatMessage(role="user", content=query))

        steps = []
        final_answer = None

        # ReAct loop
        for step_num in range(self.max_steps):
            # Get LLM response
            response = await llm.chat(messages=messages, temperature=0.7)
            assistant_text = response.content

            # Parse action
            action_result = self._parse_action(assistant_text)

            if action_result:
                action, action_input = action_result

                # Execute tool
                observation = await execute_tool(action, action_input, tools)

                # Record step
                thought_match = re.search(r'Thought:\s*(.+?)(?:\n|$)', assistant_text)
                thought = thought_match.group(1).strip() if thought_match else ""

                step = AgentStep(
                    thought=thought,
                    action=action,
                    action_input=action_input,
                    observation=observation
                )
                steps.append(step)

                # Add to messages for next iteration
                messages.append(ChatMessage(role="assistant", content=assistant_text))
                messages.append(ChatMessage(role="user", content=f"Observation: {observation}"))
            else:
                # Check for final answer
                final_answer = self._parse_final_answer(assistant_text)
                if final_answer:
                    break
                else:
                    # No action and no final answer, treat as final answer
                    final_answer = assistant_text
                    break

        # If no final answer found, use the last response
        if final_answer is None:
            final_answer = assistant_text if 'assistant_text' in locals() else "无法生成回答"

        return AgentResponse(
            content=final_answer,
            steps=steps,
            model=llm.model if hasattr(llm, 'model') else "unknown",
            token_count=response.token_count if 'response' in locals() else 0,
            finish_reason="stop"
        )

    async def run_stream(
        self,
        query: str,
        history: List[Dict[str, str]] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Run ReAct agent with streaming (simplified version)"""
        # For simplicity, run non-streaming and yield chunks
        response = await self.run(query, history, **kwargs)

        # Yield the final answer in chunks
        chunk_size = 10
        for i in range(0, len(response.content), chunk_size):
            yield response.content[i:i + chunk_size]

    def get_tools(self) -> List[Dict[str, Any]]:
        """Get list of available tools"""
        return self._get_tools()
