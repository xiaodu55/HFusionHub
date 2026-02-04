"""
ReAct Agent Implementation
Implements Reasoning + Acting loop for complex tasks
"""

import json
import re
import logging
import os
import time
import requests
from typing import List, Dict, Any, Optional, AsyncGenerator

from .agent import Agent, AgentResponse, AgentStep
from ..llm import get_llm, ChatMessage, BaseLLM
from ..tools import get_tools, execute_tool
from ..rag import (
    get_retriever,
    get_intent_classifier,
    get_query_decomposer,
    get_compressor,
    get_reflector,
    get_evaluator,
    IntentResult,
    DecompositionResult,
    SubQuestionStatus,
    CompressionStrategyType,
    CompressionConfig,
    ReflectionStrategyType,
    ReflectionConfig,
    EvaluationStrategyType,
    EvaluationSample,
)

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

    async def _handle_chitchat(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]],
        llm: BaseLLM
    ) -> AgentResponse:
        """处理闲聊"""
        messages = [ChatMessage(role="system", content="你是一个友好的AI助手。")]

        if history:
            for msg in history[-5:]:
                messages.append(ChatMessage(role=msg["role"], content=msg["content"]))

        messages.append(ChatMessage(role="user", content=query))

        response = await llm.chat(messages=messages, temperature=0.7)

        return AgentResponse(
            content=response.content,
            steps=[],
            model=llm.model if hasattr(llm, 'model') else "unknown",
            token_count=response.token_count,
            finish_reason="stop",
            sources=[]
        )

    async def _handle_operation(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]],
        llm: BaseLLM,
        tools: List[Dict[str, Any]]
    ) -> AgentResponse:
        """处理操作指令"""
        # 构建系统提示
        system_prompt = REACT_SYSTEM_PROMPT.format(
            tools_description=self._format_tools_description()
        )

        messages = [ChatMessage(role="system", content=system_prompt)]

        if history:
            for msg in history[-5:]:
                messages.append(ChatMessage(role=msg["role"], content=msg["content"]))

        messages.append(ChatMessage(role="user", content=query))

        steps = []
        final_answer = None

        for step_num in range(self.max_steps):
            response = await llm.chat(messages=messages, temperature=0.7)
            assistant_text = response.content

            action_result = self._parse_action(assistant_text)

            if action_result:
                action, action_input = action_result
                observation = await execute_tool(action, action_input, tools)

                thought_match = re.search(r'Thought:\s*(.+?)(?:\n|$)', assistant_text)
                thought = thought_match.group(1).strip() if thought_match else ""

                step = AgentStep(
                    thought=thought,
                    action=action,
                    action_input=action_input,
                    observation=str(observation)[:500] if observation else None
                )
                steps.append(step)

                messages.append(ChatMessage(role="assistant", content=assistant_text))
                messages.append(ChatMessage(role="user", content=f"Observation: {observation}"))
            else:
                final_answer = self._parse_final_answer(assistant_text)
                if final_answer:
                    break
                else:
                    final_answer = assistant_text
                    break

        if final_answer is None:
            final_answer = assistant_text if 'assistant_text' in locals() else "无法生成回答"

        return AgentResponse(
            content=final_answer,
            steps=steps,
            model=llm.model if hasattr(llm, 'model') else "unknown",
            token_count=response.token_count if 'response' in locals() else 0,
            finish_reason="stop",
            sources=[]
        )

    def _retrieve_context(
        self,
        query: str,
        history: Optional[List[Dict]] = None,
        intent_result: Optional[IntentResult] = None
    ) -> tuple:
        """
        检索相关上下文

        Args:
            query: 用户查询
            history: 对话历史
            intent_result: 意图分类结果（可选）

        Returns:
            (格式化的上下文文本, 来源列表, 自动检测的知识库ID)
        """
        try:
            retriever = get_retriever()
            logger.info(f"[RAG] Calling retriever with knowledge_base_id={self.knowledge_base_id}")
            result = retriever.retrieve(
                query=query,
                knowledge_base_id=self.knowledge_base_id,
                conversation_history=history,
                top_k=3
            )
            logger.info(f"[RAG] Retriever returned {len(result.results)} results")

            if not result.results:
                logger.info("[RAG] No results found, returning empty context")
                return "", [], self.knowledge_base_id

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

            return "\n\n".join(context_parts), sources, self.knowledge_base_id

        except Exception as e:
            logger.error(f"RAG retrieval failed: {e}")
            return "", [], self.knowledge_base_id

    def _auto_detect_knowledge_base(self, query: str) -> Optional[int]:
        """
        自动检测最相关的知识库

        当用户没有选择知识库时，搜索所有知识库并选择最相关的

        Args:
            query: 用户查询

        Returns:
            最相关的知识库 ID，如果没有找到则返回 None
        """
        try:
            from app.core.vectorstore.milvus_store import search_similar

            # 搜索所有知识库（不带 knowledge_base_id 过滤）
            results = search_similar(
                query_text=query,
                top_k=10,  # 获取更多结果以便选择
                knowledge_base_id=None  # 不过滤，搜索所有
            )

            if not results:
                return None

            # 统计每个知识库的匹配结果数量和平均分数
            kb_scores = {}
            for r in results:
                kb_id = r.get("knowledge_base_id")
                if kb_id and kb_id > 0:  # 忽略无效的 knowledge_base_id
                    if kb_id not in kb_scores:
                        kb_scores[kb_id] = {"count": 0, "total_score": 0}
                    kb_scores[kb_id]["count"] += 1
                    kb_scores[kb_id]["total_score"] += r.get("score", 0)

            if not kb_scores:
                return None

            # 选择平均分数最高的知识库
            best_kb_id = None
            best_avg_score = -1

            for kb_id, stats in kb_scores.items():
                avg_score = stats["total_score"] / stats["count"]
                # 考虑结果数量和分数
                # 如果有多个高分结果，优先选择
                if avg_score > best_avg_score and stats["count"] >= 1:
                    best_avg_score = avg_score
                    best_kb_id = kb_id

            logger.info(
                f"Auto-detected knowledge bases: {kb_scores}, "
                f"selected: {best_kb_id} (avg_score: {best_avg_score:.2f})"
            )

            return best_kb_id

        except Exception as e:
            logger.error(f"Auto-detect knowledge base failed: {e}")
            return None

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

    async def _decompose_and_handle(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]],
        intent_result: IntentResult,
        llm: BaseLLM,
        tools: List[Dict[str, Any]]
    ) -> Optional[AgentResponse]:
        """
        分解复杂问题并处理子问题

        Args:
            query: 原始查询
            history: 对话历史
            intent_result: 意图分类结果
            llm: LLM 实例
            tools: 工具列表

        Returns:
            AgentResponse 或 None（如果无法处理）
        """
        try:
            # 获取 QueryDecomposer
            decomposer = get_query_decomposer()

            # 分解查询
            decomposition_result = await decomposer.decompose(
                query=query,
                intent_result=intent_result,
                history=history,
            )

            logger.info(
                f"Query decomposed: {len(decomposition_result.sub_questions)} sub-questions, "
                f"strategy: {decomposition_result.strategy_used}, "
                f"parallel groups: {decomposition_result.parallel_groups}"
            )

            # 如果不需要分解，返回 None 继续原有逻辑
            if not decomposition_result.needs_decomposition:
                return None

            # 处理子问题
            all_sub_answers = []
            all_sources = []
            completed_ids = set()

            # 按层级执行子问题
            for level in decomposition_result.execution_plan:
                # 获取当前层级可执行的子问题
                batch = [q for q in level if q.can_execute(completed_ids)]

                if not batch:
                    continue

                # 并行处理当前批次
                import asyncio
                tasks = [
                    self._handle_sub_question(q, history, llm, tools)
                    for q in batch
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # 收集结果
                for q, result in zip(batch, results):
                    if isinstance(result, Exception):
                        logger.error(f"Sub-question {q.id} failed: {result}")
                        q.status = SubQuestionStatus.FAILED
                        all_sub_answers.append(f"[{q.id}] 处理失败: {str(result)[:100]}")
                    else:
                        answer, sources = result
                        q.status = SubQuestionStatus.COMPLETED
                        q.answer = answer
                        all_sub_answers.append(f"[{q.id}] {answer}")
                        all_sources.extend(sources)

                    completed_ids.add(q.id)

            # 合并所有子问题的答案
            combined_answer = self._merge_sub_answers(query, all_sub_answers)

            return AgentResponse(
                content=combined_answer,
                steps=[],
                model=llm.model if hasattr(llm, 'model') else "unknown",
                token_count=0,
                finish_reason="stop",
                sources=all_sources,
                intent=intent_result.to_dict(),
                decomposition=decomposition_result.to_dict(),
            )

        except Exception as e:
            logger.error(f"Query decomposition failed: {e}")
            return None

    async def _handle_sub_question(
        self,
        sub_question: "SubQuestion",
        history: Optional[List[Dict[str, str]]],
        llm: BaseLLM,
        tools: List[Dict[str, Any]]
    ) -> tuple:
        """
        处理单个子问题

        Args:
            sub_question: 子问题
            history: 对话历史
            llm: LLM 实例
            tools: 工具列表

        Returns:
            (答案, 来源列表)
        """
        sub_question.status = SubQuestionStatus.PROCESSING

        try:
            # 检索相关上下文
            rag_context, rag_sources, _ = self._retrieve_context(
                sub_question.content, history
            )

            # 压缩检索结果
            if rag_context:
                compressor = get_compressor(CompressionStrategyType.EXTRACTIVE)
                compression_result = await compressor.compress(
                    rag_context,
                    CompressionConfig(target_ratio=0.6)
                )
                rag_context = compression_result.compressed_text
                logger.info(
                    f"Compressed sub-question context: "
                    f"{compression_result.original_tokens} -> {compression_result.compressed_tokens} tokens"
                )

            # 构建提示
            if rag_context:
                prompt = f"""基于以下参考资料回答问题。

参考资料：
{rag_context}

问题：{sub_question.content}

请提供准确、简洁的回答。"""
            else:
                prompt = sub_question.content

            # 调用 LLM
            messages = [ChatMessage(role="user", content=prompt)]
            response = await llm.chat(messages=messages, temperature=0.7)

            return response.content, rag_sources

        except Exception as e:
            raise

    def _merge_sub_answers(self, original_query: str, sub_answers: List[str]) -> str:
        """
        合并多个子问题的答案

        Args:
            original_query: 原始查询
            sub_answers: 子问题答案列表

        Returns:
            合并后的答案
        """
        if not sub_answers:
            return "无法回答该问题"

        if len(sub_answers) == 1:
            return sub_answers[0]

        # 构建合并提示
        answers_text = "\n\n".join(sub_answers)

        return f"""根据对问题的分解分析，以下是各部分的回答：

{answers_text}

请综合以上信息回答原始问题：{original_query}"""

    async def run(
        self,
        query: str,
        history: List[Dict[str, str]] = None,
        **kwargs
    ) -> AgentResponse:
        """Run ReAct agent"""
        llm = self._get_llm()
        tools = self._get_tools()

        # 如果没有指定知识库，先尝试自动检测
        auto_detected_kb_id = None
        if self.knowledge_base_id is None:
            auto_detected_kb_id = self._auto_detect_knowledge_base(query)
            if auto_detected_kb_id:
                self.knowledge_base_id = auto_detected_kb_id
                logger.info(f"[RAG] Auto-detected knowledge base: {auto_detected_kb_id}")

        # 如果自动检测到了知识库，跳过意图分类，直接使用 RAG 检索路径
        if auto_detected_kb_id:
            logger.info(f"[RAG] Auto-detected KB, using RAG path directly")
            intent_result = None
        else:
            # 意图分类
            intent_classifier = get_intent_classifier()
            intent_result = await intent_classifier.classify(query, history)

            logger.info(
                f"Query intent: {intent_result.intent.value}, "
                f"complexity: {intent_result.complexity.value}, "
                f"strategy: {intent_result.processing_strategy}"
            )

        # 根据意图决定处理策略（如果自动检测到了知识库，跳过意图分类）
        if intent_result is not None:
            if intent_result.is_direct_llm():
                # 闲聊直接用 LLM 回复
                return await self._handle_chitchat(query, history, llm)

            if intent_result.needs_tool():
                # 操作指令需要使用工具
                return await self._handle_operation(query, history, llm, tools)

            # 对于需要检索的复杂问题，使用 QueryDecomposer
            if intent_result.needs_retrieval() and intent_result.should_decompose():
                decomposition_result = await self._decompose_and_handle(
                    query, history, intent_result, llm, tools
                )
                if decomposition_result:
                    return decomposition_result

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
        logger.info(f"[RAG] Starting retrieval for query: {query[:50]}..., knowledge_base_id: {self.knowledge_base_id}")
        rag_context, rag_sources, auto_detected_kb_id = self._retrieve_context(query, history, intent_result)
        logger.info(f"[RAG] Retrieved context length: {len(rag_context)}, sources count: {len(rag_sources)}, auto_detected_kb_id: {auto_detected_kb_id}")

        # 压缩检索结果
        if rag_context:
            compressor = get_compressor(CompressionStrategyType.EXTRACTIVE)
            compression_result = await compressor.compress(
                rag_context,
                CompressionConfig(target_ratio=0.6)
            )
            rag_context = compression_result.compressed_text
            logger.info(
                f"Compressed RAG context: "
                f"{compression_result.original_tokens} -> {compression_result.compressed_tokens} tokens"
            )

        if rag_context:
            # 将检索到的上下文添加到用户查询中
            enhanced_query = f"""请根据以下参考资料回答用户问题。你必须优先使用参考资料中的信息来回答，不要说"信息有限"或"没有相关内容"。如果参考资料中确实有相关信息，请直接引用并回答。

【参考资料】
{rag_context}

【用户问题】
{query}

请基于参考资料提供详细、准确的回答。回答时请：
1. 直接引用参考资料中的具体内容
2. 如果有多条相关信息，请综合整理
3. 在回答末尾标注来源文档名称"""
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

        # 使用 SelfReflector 评估答案质量
        if final_answer and rag_context:
            try:
                reflector = get_reflector(ReflectionStrategyType.RULE_BASED)
                reflection_config = ReflectionConfig(
                    quality_threshold=0.7,
                    max_retries=1,
                    enable_supplement=False,
                )
                reflection_result = await reflector.reflect(
                    query=query,
                    answer=final_answer,
                    context=rag_context,
                    config=reflection_config,
                )

                logger.info(
                    f"Answer reflected: quality_score={reflection_result.quality_score:.2f}, "
                    f"issues={len(reflection_result.issues)}"
                )

                # 如果反思后答案更好，使用反思后的答案
                if (reflection_result.reflected_answer != final_answer and
                    reflection_result.quality_score >= 0.7):
                    final_answer = reflection_result.reflected_answer

            except Exception as e:
                logger.warning(f"Self-reflection failed: {e}")

        return AgentResponse(
            content=final_answer,
            steps=steps,
            model=llm.model if hasattr(llm, 'model') else "unknown",
            token_count=response.token_count if 'response' in locals() else 0,
            finish_reason="stop",
            sources=list(unique_sources.values()),
            intent=intent_result.to_dict() if intent_result else None,
            auto_detected_kb_id=auto_detected_kb_id
        )

    async def run_stream(
        self,
        query: str,
        history: List[Dict[str, str]] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Run ReAct agent with streaming support"""
        # 导入必要的模块
        from ..rag import get_intent_classifier, get_query_decomposer, get_compressor, get_reflector

        try:
            # 获取自动检测的知识库 ID
            auto_detected_kb_id = None
            if self.knowledge_base_id is None:
                auto_detected_kb_id = self._auto_detect_knowledge_base(query)
                if auto_detected_kb_id:
                    self.knowledge_base_id = auto_detected_kb_id
                    logger.info(f"[RAG] Auto-detected knowledge base: {auto_detected_kb_id}")

            # 如果自动检测到了知识库，跳过意图分类，直接使用 RAG 检索路径
            if auto_detected_kb_id:
                logger.info(f"[RAG] Auto-detected KB, using RAG path directly")
                intent_result = None
            else:
                # 意图分类
                intent_classifier = get_intent_classifier()
                intent_result = await intent_classifier.classify(query, history)

            # 意图是闲聊，直接流式输出
            if intent_result and intent_result.intent == "chitchat":
                llm = get_llm()
                messages = [
                    ChatMessage(role="system", content="你是一个友好的AI助手，可以进行日常闲聊。"),
                    ChatMessage(role="user", content=query)
                ]
                async for chunk in llm.chat_stream(messages=messages, temperature=0.7, max_tokens=2048):
                    yield chunk
                return

            # 意图是操作，也直接流式输出
            if intent_result and intent_result.intent == "operation":
                llm = get_llm()
                messages = [
                    ChatMessage(role="system", content="你是一个智能助手，请回答用户的问题。"),
                    ChatMessage(role="user", content=query)
                ]
                async for chunk in llm.chat_stream(messages=messages, temperature=0.7, max_tokens=2048):
                    yield chunk
                return

            # 检索增强生成
            context = ""
            sources = []

            # 获取检索器
            retriever = get_retriever()

            # 如果知识库 ID 有效，尝试检索
            if self.knowledge_base_id and self.knowledge_base_id > 0:
                try:
                    # Query Decomposition
                    query_decomposer = get_query_decomposer()
                    decomposition_result = await query_decomposer.decompose(query, intent_result, history)

                    if decomposition_result and decomposition_result.sub_questions:
                        all_results = []
                        for sub_q in decomposition_result.sub_questions:
                            result = retriever.retrieve(
                                query=sub_q.content if hasattr(sub_q, 'content') else str(sub_q),
                                knowledge_base_id=self.knowledge_base_id,
                                top_k=3
                            )
                            if result and result.results:
                                for item in result.results:
                                    all_results.append({
                                        "content": item.content,
                                        "score": item.score,
                                        "document_id": item.document_id,
                                        "knowledge_base_id": item.knowledge_base_id,
                                        "source": item.source
                                    })

                        # 去重
                        seen_contents = set()
                        unique_results = []
                        for r in all_results:
                            content = r.get("content", "")
                            if content not in seen_contents:
                                seen_contents.add(content)
                                unique_results.append(r)

                        # Context Compression
                        compressor = get_compressor(CompressionStrategyType.EXTRACTIVE)
                        rag_context = "\n\n".join([r.get("content", "") for r in unique_results])
                        if rag_context:
                            compression_result = await compressor.compress(
                                rag_context,
                                CompressionConfig(target_ratio=0.6)
                            )
                            context = compression_result.compressed_text
                            sources = unique_results
                    else:
                        # 直接检索
                        result = retriever.retrieve(
                            query=query,
                            knowledge_base_id=self.knowledge_base_id,
                            top_k=3
                        )
                        if result and result.results:
                            results = []
                            for item in result.results:
                                results.append({
                                    "content": item.content,
                                    "score": item.score,
                                    "document_id": item.document_id,
                                    "knowledge_base_id": item.knowledge_base_id,
                                    "source": item.source,
                                    "outline_path": item.outline_path or []
                                })
                            # Context Compression
                            compressor = get_compressor(CompressionStrategyType.EXTRACTIVE)
                            rag_context = "\n\n".join([r.get("content", "") for r in results])
                            if rag_context:
                                compression_result = await compressor.compress(
                                    rag_context,
                                    CompressionConfig(target_ratio=0.6)
                                )
                                context = compression_result.compressed_text
                                sources = results
                except Exception as e:
                    logger.error(f"[RAG] Retrieval failed, falling back to direct LLM: {e}", exc_info=True)
                    # 检索失败，继续使用直接 LLM 模式

            # 构建提示词
            if context:
                prompt = f"""请基于以下参考资料回答问题。

参考资料：
{context}

用户问题：{query}

请用中文回答，直接给出答案，不要说"根据参考资料"。"""
            else:
                prompt = query

            # 使用 LLM 流式生成回答
            llm = get_llm()
            messages = [
                ChatMessage(role="system", content="你是一个智能助手，请回答用户的问题。"),
                ChatMessage(role="user", content=prompt)
            ]

            # 流式输出
            async for chunk in llm.chat_stream(messages=messages, temperature=0.7, max_tokens=2048):
                yield chunk

            # 流式结束后，yield sources 信息（嵌入到 content 中）
            if sources:
                # 格式化 sources 以便前端显示
                formatted_sources = []
                for s in sources:
                    # 生成标题：优先使用 outline_path，否则从内容提取
                    outline_path = s.get("outline_path", [])
                    if outline_path:
                        title = " > ".join(outline_path)
                    else:
                        # 从内容第一行提取标题
                        content = s.get("content", "")
                        first_line = content.split("\n")[0].strip()[:50]
                        title = first_line if first_line else "参考片段"
                    formatted_sources.append({
                        "title": title,
                        "score": s.get("score", 0),
                        "content": s.get("content", "")[:150],  # 只保留前150字符
                        "source": s.get("source", "vector")
                    })
                # 使用特殊标记嵌入 sources，前端解析时识别
                sources_event = {
                    "content": "",  # 空内容
                    "sources": formatted_sources
                }
                yield json.dumps(sources_event, ensure_ascii=False)

            # 评估答案质量
            try:
                evaluator = get_evaluator(EvaluationStrategyType.RULE_BASED)
                eval_sample = EvaluationSample(
                    query_id=str(int(time.time() * 1000)),
                    query=query,
                    response=final_answer if 'final_answer' in locals() else "",
                    context=context,
                    sources=sources,
                    metadata={
                        "knowledge_base_id": self.knowledge_base_id,
                        "auto_detected_kb_id": auto_detected_kb_id,
                    }
                )
                eval_result = await evaluator.evaluate(eval_sample)

                logger.info(
                    f"Answer evaluated: overall_score={eval_result.overall_score:.2f}, "
                    f"scores={eval_result.scores}"
                )

                # 将评估结果添加到响应中
                evaluation_event = {
                    "content": "",
                    "evaluation": {
                        "overall_score": eval_result.overall_score,
                        "scores": eval_result.scores,
                        "strategy_used": eval_result.strategy_used,
                    }
                }
                yield json.dumps(evaluation_event, ensure_ascii=False)

            except Exception as eval_error:
                logger.warning(f"Answer evaluation failed: {eval_error}")

        except Exception as e:
            logger.error(f"[RAG] run_stream failed: {e}", exc_info=True)
            # 降级：直接用 LLM 回答
            try:
                llm = get_llm()
                messages = [
                    ChatMessage(role="system", content="你是一个智能助手，请回答用户的问题。"),
                    ChatMessage(role="user", content=query)
                ]
                async for chunk in llm.chat_stream(messages=messages, temperature=0.7, max_tokens=2048):
                    yield chunk
            except Exception as fallback_error:
                logger.error(f"[RAG] Fallback LLM also failed: {fallback_error}", exc_info=True)
                yield f"抱歉，AI服务出现异常，请稍后重试。错误信息：{str(e)}"

    def get_tools(self) -> List[Dict[str, Any]]:
        """Get list of available tools"""
        return self._get_tools()
