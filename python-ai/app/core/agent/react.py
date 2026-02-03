"""
ReAct Agent Implementation
Implements Reasoning + Acting loop for complex tasks
"""

import json
import re
import logging
import os
import requests
from typing import List, Dict, Any, Optional, AsyncGenerator

from .agent import Agent, AgentResponse, AgentStep
from ..llm import get_llm, ChatMessage, BaseLLM
from ..tools import get_tools, execute_tool
from ..rag import get_retriever

logger = logging.getLogger(__name__)


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
5. 当使用知识库搜索结果回答时，请在回答末尾添加来源引用，格式如：[来源: 文档名称]
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

    def _get_document_name(self, document_id: str) -> str:
        """
        从 Java 后端获取文档名称

        Args:
            document_id: 文档ID

        Returns:
            文档名称
        """
        try:
            java_backend_url = os.getenv("JAVA_BACKEND_URL", "http://localhost:8080")
            response = requests.get(
                f"{java_backend_url}/api/document/{document_id}/name",
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 200:
                    return data.get("data", {}).get("name", "未知文档")
        except Exception as e:
            logger.warning(f"Failed to get document name: {e}")

        return f"文档-{document_id}"

    def _retrieve_context(
        self,
        query: str,
        history: Optional[List[Dict]] = None
    ) -> tuple:
        """
        检索相关上下文

        Args:
            query: 用户查询
            history: 对话历史

        Returns:
            (格式化的上下文文本, 来源列表)
        """
        try:
            retriever = get_retriever()
            result = retriever.retrieve(
                query=query,
                knowledge_base_id=self.knowledge_base_id,
                conversation_history=history,
                top_k=3
            )

            if not result.results:
                return "", []

            # 格式化为上下文
            context_parts = []
            sources = []

            for i, r in enumerate(result.results, 1):
                source_label = {
                    "vector": "语义匹配",
                    "keyword": "关键词匹配",
                    "graph": "知识图谱"
                }.get(r.source, "检索")

                context_parts.append(
                    f"[{i}] ({source_label}, 相似度: {r.score:.2f})\n{r.content}"
                )

                # 收集来源信息
                document_name = self._get_document_name(r.document_id)
                sources.append({
                    "document_id": r.document_id,
                    "document_name": document_name,
                    "content": r.content[:200],  # 前200字符
                    "score": r.score,
                    "source": r.source
                })

            return "\n\n".join(context_parts), sources

        except Exception as e:
            logger.error(f"RAG retrieval failed: {e}")
            return "", []

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

        # RAG: 检索相关知识
        rag_context, rag_sources = self._retrieve_context(query, history)
        if rag_context:
            # 将检索到的上下文添加到用户查询中
            enhanced_query = f"""基于以下参考资料回答用户问题。

参考资料：
{rag_context}

用户问题：{query}

请根据参考资料提供准确的回答。如果参考资料不相关，请基于你的知识回答。"""
        else:
            enhanced_query = query

        # Add current query
        messages.append(ChatMessage(role="user", content=enhanced_query))

        steps = []
        final_answer = None
        sources = rag_sources if rag_sources else []

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

                # Collect sources from search results
                if action == "search_knowledge_base" and isinstance(observation, list):
                    for result in observation:
                        if "source" in result and "error" not in result:
                            sources.append({
                                "document_id": result.get("document_id"),
                                "document_name": result.get("document_name", "未知文档"),
                                "content": result.get("content", "")[:200],  # 前200字符
                                "score": result.get("score", 0)
                            })

                # Record step
                thought_match = re.search(r'Thought:\s*(.+?)(?:\n|$)', assistant_text)
                thought = thought_match.group(1).strip() if thought_match else ""

                step = AgentStep(
                    thought=thought,
                    action=action,
                    action_input=action_input,
                    observation=str(observation)[:500] if observation else None
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

        # Deduplicate sources by document_name
        unique_sources = {}
        for source in sources:
            doc_name = source["document_name"]
            if doc_name not in unique_sources:
                unique_sources[doc_name] = source

        return AgentResponse(
            content=final_answer,
            steps=steps,
            model=llm.model if hasattr(llm, 'model') else "unknown",
            token_count=response.token_count if 'response' in locals() else 0,
            finish_reason="stop",
            sources=list(unique_sources.values())
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
