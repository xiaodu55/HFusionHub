"""
ReAct Agent Implementation — Agent V1
Implements Reasoning + Acting loop for complex tasks.

Agent V1 changes:
- ``style`` parameter (concise | detailed | report) controls answer verbosity.
- ``tool_calls_count`` is tracked and reported in the response.
- All sources use the canonical V1 format (document_id, chunk_id, title,
  excerpt, score).
- ``_last_sources`` and ``_tool_calls_count`` are exposed for the
  WorkflowRuntime to read partial results on timeout.
"""

import json
import re
import logging
import time
from typing import List, Dict, Any, Optional, AsyncGenerator

from .agent import Agent, AgentResponse, AgentStep
from ..llm import get_llm, ChatMessage, BaseLLM
from ..tools import execute_tool, ToolExecutionPolicy, ToolRegistry, create_v1_registry
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
    get_adaptive_retrieval_planner,
)

logger = logging.getLogger(__name__)

NO_SUFFICIENT_EVIDENCE_REPLY = "我在当前知识库中未检索到足够依据，无法基于资料回答这个问题。"

# ── Evidence integrity constants ───────────────────────────────────────
_MIN_COMPRESSION_SAFETY_RATIO = 0.25
_GROUNDLESS_MARKERS = [
    "未检索到足够依据", "未检索到依据", "证据不足", "无法基于资料",
    "未找到相关", "没有相关信息", "资料中未提及", "资料中未包含",
    "no sufficient evidence", "insufficient evidence", "not found in",
    "cannot answer based on", "does not contain", "does not mention",
]

# ── Style prompts ──────────────────────────────────────────────────────
_STYLE_PROMPTS = {
    "concise": "请用简洁的语言回答（不超过200字），直接给出结论和关键依据。",
    "detailed": "请提供详细的段落级回答，包含具体数据和上下文。",
    "report": (
        "请生成一份结构化的分析报告，使用 Markdown 格式。"
        "包含以下章节：## 概述、## 详细分析、## 关键发现、## 建议（如适用）。"
        "每个断言需注明来源。"
    ),
}


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
    """ReAct Agent implementation — Agent V1 compatible."""

    def __init__(
        self,
        knowledge_base_id: int = None,
        model: str = None,
        max_steps: int = 5,
        tool_policy: Optional[ToolExecutionPolicy] = None,
        style: str = "detailed",
        tool_registry: Optional[ToolRegistry] = None,
        **kwargs
    ):
        self.knowledge_base_id = knowledge_base_id
        self.model = model
        self.max_steps = max_steps
        self.tool_policy = tool_policy
        self.style = style if style in _STYLE_PROMPTS else "detailed"
        self.llm: BaseLLM = None
        self.tools: List[Dict[str, Any]] = []

        # Agent V1: Tool Registry is the SINGLE source of truth for tools.
        # Agents MUST NOT bypass the registry.
        self._registry: Optional[ToolRegistry] = tool_registry

        # Agent V1: track tool calls and sources for partial-result reporting.
        self._tool_calls_count: int = 0
        self._last_sources: List[Dict[str, Any]] = []

    def _get_llm(self) -> BaseLLM:
        """Get LLM instance (lazy initialization)"""
        if self.llm is None:
            self.llm = get_llm(model=self.model)
        return self.llm

    def _get_tools(self) -> List[Dict[str, Any]]:
        """Get available tools from the Tool Registry.

        The Registry is the single choke point — agents cannot get tools
        any other way.  Each tool dict carries a ``_registry`` back-reference
        so ``execute_tool`` can route through the Registry.
        """
        if not self.tools:
            if self._registry is not None:
                raw = self._registry.get_tools(v1_only=True)
            elif self._has_selected_knowledge_base():
                self._registry = create_v1_registry(self.knowledge_base_id)
                raw = self._registry.get_tools(v1_only=True)
            else:
                # No KB → no KB-scoped tools.  Return empty list.
                return []
            # Attach registry back-reference so execute_tool uses it.
            for t in raw:
                t["_registry"] = self._registry
            self.tools = raw
        return self.tools

    def _has_selected_knowledge_base(self) -> bool:
        """Only a Java-authorized conversation may enable knowledge-base RAG."""
        return self.knowledge_base_id is not None and self.knowledge_base_id > 0

    # ── Agent V1 canonical source format ───────────────────────────────

    @staticmethod
    def _citation_from_result(result: Any) -> Dict[str, Any]:
        """Build the canonical Agent V1 citation from a retrieved chunk."""
        metadata = getattr(result, "metadata", {}) or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                metadata = {}

        document_id = getattr(result, "document_id", None) or metadata.get("document_id")
        chunk_id = (
            getattr(result, "chunk_id", None)
            or metadata.get("chunk_id")
        )
        content = getattr(result, "content", "") or ""
        title = metadata.get("document_title") or f"文档 #{document_id}"
        score = getattr(result, "score", 0) or 0

        return {
            "document_id": int(document_id) if document_id is not None else None,
            "chunk_id": chunk_id,
            "title": title,
            "excerpt": content[:300] if content else "",
            "score": float(score),
        }

    @staticmethod
    def _citation_from_dict(source: Dict[str, Any]) -> Dict[str, Any]:
        """Normalise a dict-based source to the canonical Agent V1 format."""
        metadata = source.get("metadata", {})
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                metadata = {}

        doc_id = source.get("document_id") or metadata.get("document_id")
        chunk_id = source.get("chunk_id") or metadata.get("chunk_id")
        content = source.get("content", "") or ""
        title = metadata.get("document_title") or source.get("document_name") or f"文档 #{doc_id}"
        score = source.get("score", 0) or 0

        return {
            "document_id": int(doc_id) if doc_id is not None else None,
            "chunk_id": chunk_id,
            "title": title,
            "excerpt": content[:300] if content else "",
            "score": float(score),
        }

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
            answer=response.content,
            steps=[],
            model=llm.model if hasattr(llm, 'model') else "unknown",
            token_count=response.token_count,
            finish_reason="stop",
            status="completed",
            sources=[],
            style_used=self.style,
        )

    async def _handle_operation(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]],
        llm: BaseLLM,
        tools: List[Dict[str, Any]]
    ) -> AgentResponse:
        """处理操作指令"""
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
                observation = await execute_tool(action, action_input, tools, policy=self.tool_policy)
                self._tool_calls_count += 1

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
            answer=final_answer,
            steps=steps,
            model=llm.model if hasattr(llm, 'model') else "unknown",
            token_count=response.token_count if 'response' in locals() else 0,
            finish_reason="stop",
            status="completed",
            sources=[],
            tool_calls_count=self._tool_calls_count,
            max_tool_steps=self.max_steps,
            style_used=self.style,
        )

    async def _retrieve_context(
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
            plan = await get_adaptive_retrieval_planner().plan(
                query=query,
                history=history,
                intent_result=intent_result,
            )
            logger.info(f"[RAG] Calling retriever with knowledge_base_id={self.knowledge_base_id}")
            result = await retriever.retrieve(
                query=plan.query,
                knowledge_base_id=self.knowledge_base_id,
                conversation_history=history,
                top_k=plan.top_k,
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

                sources.append(self._citation_from_result(r))

            return "\n\n".join(context_parts), sources, self.knowledge_base_id

        except Exception as e:
            logger.error(f"RAG retrieval failed: {e}")
            return "", [], self.knowledge_base_id

    async def _safe_compress(
        self,
        rag_context: str,
        target_ratio: float = 0.6,
    ) -> tuple[str, bool]:
        """Compress retrieval context with evidence-integrity guard."""
        if not rag_context:
            return rag_context, False

        compressor = get_compressor(CompressionStrategyType.EXTRACTIVE)
        result = await compressor.compress(
            rag_context,
            CompressionConfig(target_ratio=target_ratio),
        )

        if result.compressed_text == rag_context:
            logger.info(
                "[RAG] Compression skipped: context below minimum threshold "
                f"({result.original_tokens} tokens)"
            )
            return rag_context, False

        if (result.compression_ratio < _MIN_COMPRESSION_SAFETY_RATIO
                and result.original_tokens > 500):
            logger.warning(
                f"[RAG] Compression over-aggressive "
                f"({result.original_tokens} -> {result.compressed_tokens} tokens, "
                f"ratio {result.compression_ratio:.2f}); falling back to original"
            )
            return rag_context, False

        logger.info(
            f"[RAG] Compressed context: "
            f"{result.original_tokens} -> {result.compressed_tokens} tokens"
        )
        return result.compressed_text, True

    @staticmethod
    def _is_groundless_answer(answer: str) -> bool:
        """Return True when the answer text signals the model found no usable evidence."""
        answer_lower = answer.lower()
        return any(marker.lower() in answer_lower for marker in _GROUNDLESS_MARKERS)

    @staticmethod
    def _build_rag_prompt(context: str, query: str, style: str = "detailed") -> str:
        """Build the evidence-first prompt used by both streaming and non-streaming paths."""
        style_instruction = _STYLE_PROMPTS.get(style, _STYLE_PROMPTS["detailed"])

        return (
            "请仅根据以下参考资料回答用户问题。"
            "不要补充资料中没有的信息；若资料不足以支持答案，请明确说明“未检索到足够依据”。\n\n"
            "【参考资料】\n"
            f"{context}\n\n"
            "【用户问题】\n"
            f"{query}\n\n"
            f"【回答要求】\n{style_instruction}\n\n"
            "请基于参考资料提供准确回答，并在适用处说明依据。"
        )

    def _parse_action(self, text: str) -> Optional[tuple]:
        """Parse action and action input from text"""
        action_match = re.search(r'Action:\s*(.+?)(?:\n|$)', text)
        if not action_match:
            return None

        action = action_match.group(1).strip()

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
        """分解复杂问题并处理子问题"""
        try:
            decomposer = get_query_decomposer()

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

            if not decomposition_result.needs_decomposition:
                return None

            all_sub_answers = []
            all_sources = []
            completed_ids = set()

            for level in decomposition_result.execution_plan:
                batch = [q for q in level if q.can_execute(completed_ids)]

                if not batch:
                    continue

                import asyncio
                tasks = [
                    self._handle_sub_question(q, history, llm, tools)
                    for q in batch
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

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

            combined_answer = self._merge_sub_answers(query, all_sub_answers)

            return AgentResponse(
                content=combined_answer,
                answer=combined_answer,
                steps=[],
                model=llm.model if hasattr(llm, 'model') else "unknown",
                token_count=0,
                finish_reason="stop",
                status="completed",
                sources=all_sources,
                intent=intent_result.to_dict(),
                decomposition=decomposition_result.to_dict(),
                tool_calls_count=self._tool_calls_count,
                max_tool_steps=self.max_steps,
                style_used=self.style,
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
        """处理单个子问题"""
        sub_question.status = SubQuestionStatus.PROCESSING

        try:
            rag_context, rag_sources, _ = await self._retrieve_context(
                sub_question.content, history
            )

            if rag_context:
                rag_context, _ = await self._safe_compress(rag_context)

            if rag_context:
                prompt = f"""基于以下参考资料回答问题。

参考资料：
{rag_context}

问题：{sub_question.content}

请提供准确、简洁的回答。"""
            else:
                prompt = sub_question.content

            messages = [ChatMessage(role="user", content=prompt)]
            response = await llm.chat(messages=messages, temperature=0.7)

            return response.content, rag_sources

        except Exception as e:
            raise

    def _merge_sub_answers(self, original_query: str, sub_answers: List[str]) -> str:
        """合并多个子问题的答案"""
        if not sub_answers:
            return "无法回答该问题"

        if len(sub_answers) == 1:
            return sub_answers[0]

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
        """Run ReAct agent — Agent V1."""
        # Reset per-run counters.
        self._tool_calls_count = 0
        self._last_sources = []

        # Accept style override from kwargs.
        if "style" in kwargs:
            self.style = kwargs["style"] if kwargs["style"] in _STYLE_PROMPTS else self.style

        llm = self._get_llm()
        tools = self._get_tools()

        has_selected_kb = self._has_selected_knowledge_base()
        auto_detected_kb_id = None
        intent_result = None
        if not has_selected_kb:
            intent_classifier = get_intent_classifier()
            intent_result = await intent_classifier.classify(query, history)

            logger.info(
                f"Query intent: {intent_result.intent.value}, "
                f"complexity: {intent_result.complexity.value}, "
                f"strategy: {intent_result.processing_strategy}"
            )

        if intent_result is not None:
            if intent_result.is_direct_llm():
                return await self._handle_chitchat(query, history, llm)

            if intent_result.needs_tool():
                return await self._handle_operation(query, history, llm, tools)

            if not has_selected_kb:
                return await self._handle_chitchat(query, history, llm)

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

        messages = [ChatMessage(role="system", content=system_prompt)]

        if history:
            for msg in history[-10:]:
                messages.append(ChatMessage(role=msg["role"], content=msg["content"]))

        # RAG: 检索相关知识
        logger.info(f"[RAG] Starting retrieval for query: {query[:50]}..., knowledge_base_id: {self.knowledge_base_id}")
        raw_context, rag_sources, auto_detected_kb_id = await self._retrieve_context(query, history, intent_result)
        logger.info(f"[RAG] Retrieved context length: {len(raw_context)}, sources count: {len(rag_sources)}, auto_detected_kb_id: {auto_detected_kb_id}")

        rag_context, was_compressed = await self._safe_compress(raw_context)

        if has_selected_kb and not rag_context:
            self._last_sources = []
            return AgentResponse(
                content=NO_SUFFICIENT_EVIDENCE_REPLY,
                answer=NO_SUFFICIENT_EVIDENCE_REPLY,
                steps=[],
                model=llm.model if hasattr(llm, 'model') else "unknown",
                token_count=0,
                finish_reason="insufficient_evidence",
                status="insufficient_evidence",
                sources=[],
                intent=intent_result.to_dict() if intent_result else None,
                tool_calls_count=self._tool_calls_count,
                max_tool_steps=self.max_steps,
                style_used=self.style,
            )

        if rag_context:
            enhanced_query = self._build_rag_prompt(rag_context, query, self.style)
        else:
            enhanced_query = query

        messages.append(ChatMessage(role="user", content=enhanced_query))

        steps = []
        final_answer = None
        sources = list(rag_sources) if rag_sources else []
        self._last_sources = list(sources)

        # ReAct loop
        for step_num in range(self.max_steps):
            response = await llm.chat(messages=messages, temperature=0.7)
            assistant_text = response.content

            action_result = self._parse_action(assistant_text)

            if action_result:
                action, action_input = action_result
                self._tool_calls_count += 1

                observation = await execute_tool(action, action_input, tools, policy=self.tool_policy)

                # Collect sources from tool results (Agent V1 canonical format).
                if action == "search_knowledge_base":
                    try:
                        obs_data = json.loads(observation) if isinstance(observation, str) else observation
                        if isinstance(obs_data, list):
                            for result in obs_data:
                                if isinstance(result, dict) and "error" not in result:
                                    sources.append(self._citation_from_dict(result))
                                    self._last_sources = list(sources)
                    except (json.JSONDecodeError, TypeError):
                        pass

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

        # Deduplicate sources by chunk_id.
        unique_sources: Dict[str, Dict[str, Any]] = {}
        for source in sources:
            source_key = source.get("chunk_id") or f"{source.get('document_id')}:{source.get('excerpt', '')[:80]}"
            if source_key not in unique_sources:
                unique_sources[source_key] = source
        deduped_sources = list(unique_sources.values())
        self._last_sources = deduped_sources

        # ── Groundedness check ──
        groundedness_failed = False
        if (has_selected_kb and rag_sources
                and self._is_groundless_answer(final_answer)
                and was_compressed):
            logger.warning(
                "[RAG] Model returned groundless answer despite non-empty retrieval. "
                "Retrying with uncompressed context."
            )
            try:
                retry_prompt = self._build_rag_prompt(raw_context, query, self.style)
                retry_messages = [ChatMessage(role="system", content=system_prompt)]
                if history:
                    for msg in history[-10:]:
                        retry_messages.append(ChatMessage(role=msg["role"], content=msg["content"]))
                retry_messages.append(ChatMessage(role="user", content=retry_prompt))
                retry_response = await llm.chat(messages=retry_messages, temperature=0.7)
                retry_text = retry_response.content
                if not self._is_groundless_answer(retry_text):
                    final_answer = retry_text
                    logger.info("[RAG] Groundedness retry succeeded with uncompressed context.")
                else:
                    groundedness_failed = True
                    logger.error(
                        "[RAG] Groundedness retry also returned groundless answer. "
                        f"Raw context length: {len(raw_context)}, "
                        f"sources: {len(rag_sources)}"
                    )
            except Exception as retry_err:
                groundedness_failed = True
                logger.error(f"[RAG] Groundedness retry failed: {retry_err}")

        # Self-reflection
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

                if (reflection_result.reflected_answer != final_answer and
                    reflection_result.quality_score >= 0.7):
                    final_answer = reflection_result.reflected_answer

            except Exception as e:
                logger.warning(f"Self-reflection failed: {e}")

        # Determine V1 status.
        if groundedness_failed and not final_answer:
            v1_status = "insufficient_evidence"
            finish_reason = "insufficient_evidence"
        else:
            v1_status = "completed"
            finish_reason = "stop"

        return AgentResponse(
            content=final_answer,
            answer=final_answer,
            steps=steps,
            model=llm.model if hasattr(llm, 'model') else "unknown",
            token_count=response.token_count if 'response' in locals() else 0,
            finish_reason=finish_reason,
            status=v1_status,
            sources=deduped_sources,
            intent=intent_result.to_dict() if intent_result else None,
            auto_detected_kb_id=auto_detected_kb_id,
            tool_calls_count=self._tool_calls_count,
            max_tool_steps=self.max_steps,
            style_used=self.style,
        )

    async def run_stream(
        self,
        query: str,
        history: List[Dict[str, str]] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Run ReAct agent with streaming support — Agent V1."""
        # Reset per-run counters.
        self._tool_calls_count = 0
        self._last_sources = []

        if "style" in kwargs:
            self.style = kwargs["style"] if kwargs["style"] in _STYLE_PROMPTS else self.style

        from ..rag import get_intent_classifier, get_query_decomposer, get_compressor, get_reflector

        try:
            has_selected_kb = self._has_selected_knowledge_base()
            auto_detected_kb_id = None
            intent_result = None
            if not has_selected_kb:
                intent_classifier = get_intent_classifier()
                intent_result = await intent_classifier.classify(query, history)

            if not has_selected_kb and intent_result and intent_result.intent == "chitchat":
                llm = get_llm()
                messages = [
                    ChatMessage(role="system", content="你是一个友好的AI助手，可以进行日常闲聊。"),
                    ChatMessage(role="user", content=query)
                ]
                async for chunk in llm.chat_stream(messages=messages, temperature=0.7, max_tokens=2048):
                    yield chunk
                return

            if not has_selected_kb and intent_result and intent_result.intent == "operation":
                llm = get_llm()
                messages = [
                    ChatMessage(role="system", content="你是一个智能助手，请回答用户的问题。"),
                    ChatMessage(role="user", content=query)
                ]
                async for chunk in llm.chat_stream(messages=messages, temperature=0.7, max_tokens=2048):
                    yield chunk
                return

            context = ""
            raw_context = ""
            sources: List[Dict[str, Any]] = []
            was_compressed = False
            retriever = get_retriever()

            if has_selected_kb:
                try:
                    retrieval_plan = await get_adaptive_retrieval_planner().plan(
                        query=query,
                        history=history,
                        intent_result=intent_result,
                    )
                    query_decomposer = get_query_decomposer()
                    decomposition_result = await query_decomposer.decompose(query, intent_result, history)

                    if decomposition_result and decomposition_result.sub_questions:
                        all_results = []
                        for sub_q in decomposition_result.sub_questions:
                            sub_query = sub_q.content if hasattr(sub_q, 'content') else str(sub_q)
                            sub_plan = await get_adaptive_retrieval_planner().plan(
                                query=sub_query,
                                history=history,
                                intent_result=intent_result,
                            )
                            result = await retriever.retrieve(
                                query=sub_plan.query,
                                knowledge_base_id=self.knowledge_base_id,
                                top_k=sub_plan.top_k,
                            )
                            if result and result.results:
                                for item in result.results:
                                    all_results.append({
                                        "content": item.content,
                                        "score": item.score,
                                        "document_id": item.document_id,
                                        "knowledge_base_id": item.knowledge_base_id,
                                        "source": item.source,
                                        "outline_path": item.outline_path or [],
                                        "metadata": item.metadata or {},
                                    })

                        seen_contents = set()
                        unique_results = []
                        for r in all_results:
                            content_val = r.get("content", "")
                            if content_val not in seen_contents:
                                seen_contents.add(content_val)
                                unique_results.append(r)

                        raw_context = "\n\n".join([r.get("content", "") for r in unique_results])
                        context, was_compressed = await self._safe_compress(raw_context)
                        sources = [self._citation_from_dict(r) for r in unique_results]
                    else:
                        result = await retriever.retrieve(
                            query=retrieval_plan.query,
                            knowledge_base_id=self.knowledge_base_id,
                            top_k=retrieval_plan.top_k,
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
                                    "outline_path": item.outline_path or [],
                                    "metadata": item.metadata or {},
                                })
                            raw_context = "\n\n".join([r.get("content", "") for r in results])
                            context, was_compressed = await self._safe_compress(raw_context)
                            sources = [self._citation_from_dict(r) for r in results]
                except Exception as e:
                    logger.error(f"[RAG] Retrieval failed, falling back to direct LLM: {e}", exc_info=True)

            self._last_sources = sources

            if has_selected_kb and not context:
                yield NO_SUFFICIENT_EVIDENCE_REPLY
                return

            prompt = self._build_rag_prompt(context, query, self.style) if context else query

            llm = get_llm()
            messages = [
                ChatMessage(role="system", content="你是一个智能助手，请回答用户的问题。"),
                ChatMessage(role="user", content=prompt)
            ]

            final_answer_parts: list[str] = []
            async for chunk in llm.chat_stream(messages=messages, temperature=0.7, max_tokens=2048):
                final_answer_parts.append(chunk)
                yield chunk
            final_answer = "".join(final_answer_parts)

            # ── Groundedness check (streaming) ──
            if (has_selected_kb and sources
                    and self._is_groundless_answer(final_answer)
                    and was_compressed
                    and raw_context):
                logger.warning(
                    "[RAG:stream] Model returned groundless answer despite non-empty retrieval. "
                    "Retrying with uncompressed context."
                )
                try:
                    retry_prompt = self._build_rag_prompt(raw_context, query, self.style)
                    retry_messages = [
                        ChatMessage(role="system", content="你是一个智能助手，请回答用户的问题。"),
                        ChatMessage(role="user", content=retry_prompt)
                    ]
                    retry_parts: list[str] = []
                    async for chunk in llm.chat_stream(messages=retry_messages, temperature=0.7, max_tokens=2048):
                        retry_parts.append(chunk)
                        yield chunk
                    retry_text = "".join(retry_parts)
                    if not self._is_groundless_answer(retry_text):
                        final_answer = retry_text
                        logger.info("[RAG:stream] Groundedness retry succeeded.")
                    else:
                        logger.error(
                            "[RAG:stream] Groundedness retry also returned groundless answer. "
                            f"Raw context length: {len(raw_context)}, "
                            f"sources: {len(sources)}"
                        )
                except Exception as retry_err:
                    logger.error(f"[RAG:stream] Groundedness retry failed: {retry_err}")

            # Yield sources as a JSON event (Agent V1 canonical format).
            if sources:
                formatted_sources = [self._citation_from_dict(s) for s in sources]
                sources_event = {"content": "", "sources": formatted_sources}
                yield json.dumps(sources_event, ensure_ascii=False)

            # Evaluate answer quality.
            try:
                evaluator = get_evaluator(EvaluationStrategyType.RULE_BASED)
                eval_sample = EvaluationSample(
                    query_id=str(int(time.time() * 1000)),
                    query=query,
                    response=final_answer,
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
            if self._has_selected_knowledge_base():
                yield NO_SUFFICIENT_EVIDENCE_REPLY
                return
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
