"""KB 检索编排管线 — ReAct Agent 的检索侧。

自适应规划 → 检索 → ``[n]`` 编号块上下文 → 保溯源压缩，另含依赖分层并行的
分解检索、空知识库文案与证据门判据。第六十批从 ``react.py`` 抽出：这些逻辑
只依赖知识库作用域（``knowledge_base_id`` / ``retrieval_top_k``），与 ReAct
循环、工具协议、答案质量判据无关。

三条答案管线（``run`` / ``run_stream`` / ``_run_stream_react``）共用本模块。
两条检索入口**至今口径不同**（见 ``retrieve_context`` 与
``retrieve_context_for_stream`` 的 docstring）——本批原样保留该分叉以免夹带
行为变更，统一需评测背书。
"""

import asyncio
import logging
import os
from typing import Any

from ..rag import (
    CompressionConfig,
    CompressionStrategyType,
    IntentResult,
    get_adaptive_retrieval_planner,
    get_compressor,
    get_query_decomposer,
    get_retriever,
)
from ..rag.config import get_config
from .citation import normalize_source

logger = logging.getLogger(__name__)

NO_SUFFICIENT_EVIDENCE_REPLY = (
    "我在当前知识库中未检索到足够依据，无法基于资料回答这个问题。"
    "建议：1) 到「文档」页确认相关资料已完成解析；2) 换一种问法，或补充包含该内容的资料。"
    "我不会编造知识库范围外的内容。"
)

# M10: 检索服务故障 ≠ 知识库无资料 — 单独文案 + retrieval_error 状态，
# 避免把 Milvus/embedding 故障伪装成"证据不足"误导用户
RETRIEVAL_UNAVAILABLE_REPLY = "知识库检索服务暂时不可用，请稍后重试。"

_MIN_COMPRESSION_SAFETY_RATIO = 0.25

_SOURCE_LABELS = {
    "vector": "语义匹配",
    "keyword": "关键词匹配",
    "graph": "知识图谱",
}


def format_numbered_context(results: list) -> tuple[str, list[dict[str, Any]]]:
    """检索结果 → ``[n]`` 编号块上下文。

    编号 n 与返回 sources 的 1-based 序号一一对应；答案中的 ``[n]`` 引用
    标注据此映射回来源 chunk。保溯源压缩（``compress_numbered_blocks``）
    会保持编号稳定——被压掉整个块的编号不再出现，其余编号不变。
    """
    parts: list[str] = []
    sources: list[dict[str, Any]] = []
    for i, r in enumerate(results, 1):
        label = _SOURCE_LABELS.get(r.source, "检索")
        parts.append(f"[{i}] ({label}, 相似度: {r.score:.2f})\n{r.content}")
        sources.append(normalize_source(r))
    return "\n\n".join(parts), sources


class RetrievalPipeline:
    """知识库作用域内的检索编排。由 ``ReactAgent`` 持有，不依赖 Agent 状态。"""

    def __init__(
        self,
        knowledge_base_id: int | None,
        retrieval_top_k: int | None = None,
    ) -> None:
        self.knowledge_base_id = knowledge_base_id
        self.retrieval_top_k = retrieval_top_k

    async def _retrieve_core(
        self,
        query: str,
        history: list[dict] | None,
        intent_result: IntentResult | None,
        *,
        forward_history: bool,
        override_top_k: bool,
        reraise: bool,
    ) -> tuple[str, list[dict[str, Any]], int | None] | None:
        """规划 → 检索 → 编号块的共享实现，三个开关决定各管线的历史口径。

        返回值中的第三项是既有契约里的 ``auto_detected_kb_id``——本模块只按
        选定知识库检索，故恒等于 ``knowledge_base_id``（自动检测早已退出
        检索路径，字段保留是为了不改动调用方的解包形状）。
        """
        try:
            plan = await get_adaptive_retrieval_planner().plan(
                query=query,
                history=history,
                intent_result=intent_result,
            )
            kwargs: dict[str, Any] = {
                "query": plan.query,
                "knowledge_base_id": self.knowledge_base_id,
                "top_k": (self.retrieval_top_k or plan.top_k) if override_top_k else plan.top_k,
            }
            if forward_history:
                kwargs["conversation_history"] = history
            logger.info("[RAG] Calling retriever with knowledge_base_id=%s", self.knowledge_base_id)
            result = await get_retriever().retrieve(**kwargs)
            logger.info("[RAG] Retriever returned %d results", len(result.results))

            if not result.results:
                logger.info("[RAG] No results found, returning empty context")
                return "", [], self.knowledge_base_id

            context, sources = format_numbered_context(result.results)
            return context, sources, self.knowledge_base_id
        except Exception as exc:
            if reraise:
                raise
            # M10: 不伪装成"无证据"空上下文 — 返回 None 让调用方按服务故障处理
            logger.error("RAG retrieval failed: %s", exc, exc_info=True)
            return None

    async def retrieve_context(
        self,
        query: str,
        history: list[dict] | None = None,
        intent_result: IntentResult | None = None,
    ) -> tuple[str, list[dict[str, Any]], int | None] | None:
        """``run()`` 与 ``_run_stream_react()`` 的检索入口。

        对话历史透传给检索器（多轮改写生效），``retrieval_top_k`` 覆盖规划值；
        检索异常降级为 ``None``（= 服务故障，区别于"检索成功但无结果"）。
        """
        return await self._retrieve_core(
            query, history, intent_result,
            forward_history=True, override_top_k=True, reraise=False,
        )

    async def retrieve_context_for_stream(
        self,
        query: str,
        history: list[dict] | None = None,
        intent_result: IntentResult | None = None,
    ) -> tuple[str, list[dict[str, Any]], int | None] | None:
        """``run_stream()`` 快路径的检索入口（历史形态，原样保留）。

        与 ``retrieve_context`` 的三处差异：历史只进规划器、不进检索器；
        ``top_k`` 一律用规划值（忽略 ``retrieval_top_k`` 覆盖）；异常向上抛出
        而非转成 ``None``——调用方据此发 ``tool_error`` 步骤事件。
        分叉属待评估口径漂移，统一需冻结套件与真机对照。
        """
        return await self._retrieve_core(
            query, history, intent_result,
            forward_history=False, override_top_k=False, reraise=True,
        )

    async def safe_compress(
        self,
        rag_context: str,
        target_ratio: float | None = None,
        query: str | None = None,
    ) -> tuple[str, bool, list[int]]:
        """Compress retrieval context with evidence-integrity guard.

        ``query`` 透传给压缩器：句子评分加入与问题的重叠信号，避免把与
        问题直接相关但事实密度低的句子无差别丢掉。

        返回 ``(压缩后文本, 是否压缩, 可见块号)``：上下文为 [n] 编号块时走
        保溯源压缩（``compress_numbered_blocks``），块号与 ``rag_sources``
        的 1-based 序号一致——答案里的 [n] 引用标注据此映射回来源 chunk，
        被压缩掉的块对生成器不可见、引用无效。
        """
        if not rag_context:
            return rag_context, False, []

        compressor = get_compressor(CompressionStrategyType.EXTRACTIVE)
        compressed, visible_numbers, did_compress = (
            await compressor.strategy.compress_numbered_blocks(
                rag_context,
                # R18：压缩率单一来源化——走 RAGConfig.compression.target_ratio
                # （默认 0.8，RAG_COMPRESSION_TARGET_RATIO 可覆盖）。0.6 旧默认
                # 的过激压缩会丢答案句触发 insufficient_evidence 误杀
                # （ADR-006 后记：真机 20 例对照实验 3/5 可复现修复）。
                CompressionConfig(
                    target_ratio=target_ratio
                    if target_ratio is not None
                    else get_config().compression.target_ratio
                ),
                query=query,
            )
        )

        if not did_compress:
            logger.info(
                "[RAG] Compression skipped: context below minimum threshold "
                f"({compressor.strategy.estimate_tokens(rag_context)} tokens)"
            )
            return rag_context, False, visible_numbers

        compressed_tokens = compressor.strategy.estimate_tokens(compressed)
        original_tokens = compressor.strategy.estimate_tokens(rag_context)
        ratio = compressed_tokens / original_tokens if original_tokens else 1.0
        if ratio < _MIN_COMPRESSION_SAFETY_RATIO and original_tokens > 500:
            logger.warning(
                f"[RAG] Compression over-aggressive "
                f"({original_tokens} -> {compressed_tokens} tokens, "
                f"ratio {ratio:.2f}); falling back to original"
            )
            return rag_context, False, compressor.strategy.list_block_numbers(rag_context)

        logger.info(
            f"[RAG] Compressed context: "
            f"{original_tokens} -> {compressed_tokens} tokens, "
            f"visible blocks: {len(visible_numbers)}"
        )
        return compressed, True, visible_numbers

    async def decompose_retrieve_merge_context(
        self,
        query: str,
        history: list[dict[str, str]] | None,
        intent_result: Any | None,
    ) -> tuple[str, list[dict[str, Any]], str, bool, list[int], dict[str, Any]] | None:
        """分解检索统一实现（第五十七批）：按依赖层并行检索子问题，
        合并编号上下文后统一压缩。

        非流式与流式共用，终结两条语义分叉的旧实现：非流式"逐子问题生成再
        模板拼接"（合并从未真正合成、token_count=0 绕过计费、绕过证据门/
        忠实度守卫）与流式"顺序检索合并上下文"（无依赖分层、无并行）。依赖
        分层的 execution_plan + can_execute 判据从旧答案合并路径移植至此。
        答案由调用方的统一次生成产出——证据门、Groundedness 重试与引用编号
        空间由此恢复一致。

        Returns:
            (raw_context, sources, rag_context, was_compressed,
             visible_block_numbers, decomposition_dict)；
            needs_decomposition=False 时返回 None（调用方回落单路检索）。

        Raises:
            RuntimeError: 全部子问题检索失败（调用方按检索服务故障口径处理，
                与 M10"不伪装成无证据"一致）；单个子问题失败按空结果降级。
        """
        decomposition_result = await get_query_decomposer().decompose(
            query=query, intent_result=intent_result, history=history)
        if not (
            decomposition_result
            and decomposition_result.needs_decomposition
            and decomposition_result.sub_questions
        ):
            return None

        retriever = get_retriever()
        stats = {"attempted": 0, "failed": 0, "last_exc": None}

        async def _sub_retrieve(sub_q: Any) -> list:
            content = getattr(sub_q, "content", None) or str(sub_q)
            stats["attempted"] += 1
            try:
                sub_plan = await get_adaptive_retrieval_planner().plan(
                    query=content,
                    history=history,
                    intent_result=intent_result,
                )
                result = await retriever.retrieve(
                    query=sub_plan.query,
                    knowledge_base_id=self.knowledge_base_id,
                    conversation_history=history,
                    top_k=self.retrieval_top_k or sub_plan.top_k,
                )
                return list(result.results) if result and result.results else []
            except Exception as exc:
                # 单个子问题检索失败按空结果降级，不拖垮整批（M10 口径）；
                # 全部失败在调用方聚合为 RuntimeError
                stats["failed"] += 1
                stats["last_exc"] = exc
                logger.error("Sub-question %r retrieval failed: %s", content[:50], exc)
                return []

        all_results: list = []
        completed_ids: set = set()
        for level in decomposition_result.execution_plan or []:
            batch = [q for q in level if q.can_execute(completed_ids)]
            if not batch:
                continue
            results = await asyncio.gather(
                *[_sub_retrieve(q) for q in batch], return_exceptions=True)
            for q, sub_results in zip(batch, results):
                if isinstance(sub_results, Exception):
                    stats["failed"] += 1
                    stats["last_exc"] = sub_results
                    logger.error(
                        "Sub-question %r retrieval failed: %s",
                        getattr(q, "content", "?"), sub_results)
                    sub_results = []
                all_results.extend(sub_results)
                completed_ids.add(q.id)

        # 防御：execution_plan 未覆盖的子问题兜底检索，保持总量一致
        planned_ids = {
            q.id
            for level in decomposition_result.execution_plan or []
            for q in level
        }
        for q in decomposition_result.sub_questions:
            if getattr(q, "id", None) not in planned_ids:
                all_results.extend(await _sub_retrieve(q))

        if stats["attempted"] and stats["failed"] == stats["attempted"]:
            raise RuntimeError(
                "all sub-question retrievals failed") from stats["last_exc"]

        seen: set = set()
        unique_results: list = []
        for r in all_results:
            content_val = getattr(r, "content", "") or ""
            if content_val not in seen:
                seen.add(content_val)
                unique_results.append(r)

        raw_context, sources = format_numbered_context(unique_results)
        rag_context, was_compressed, visible_numbers = await self.safe_compress(
            raw_context, query=query)
        logger.info(
            "[RAG] Decomposed retrieval: %d sub-questions -> %d unique blocks (compressed=%s)",
            len(decomposition_result.sub_questions), len(unique_results), was_compressed)
        return (raw_context, sources, rag_context, was_compressed,
                visible_numbers, decomposition_result.to_dict())

    async def empty_context_reply(self) -> str:
        """Reply used when retrieval returned nothing for a selected KB.

        Distinguishes "KB empty / still parsing" from "no relevant content"
        so the user gets an actionable hint.
        """
        try:
            # cluster 模式下 all_chunks 是同步分页网络 IO——必须挪出事件循环
            from app.core.vectorstore.milvus_store import _get_store

            def _all_chunks() -> list:
                return _get_store().all_chunks(knowledge_base_id=self.knowledge_base_id)

            corpus = await asyncio.to_thread(_all_chunks)
            has_content = bool(corpus)
        except Exception:
            has_content = True  # 无法确认时按普通无依据处理
        return (
            "当前知识库还没有可检索的内容。如果资料刚上传，可能仍在解析中，"
            "请稍候或到「文档」页查看解析状态；解析完成后即可基于资料回答。"
            if not has_content
            else NO_SUFFICIENT_EVIDENCE_REPLY
        )

    @staticmethod
    def evidence_gate_threshold() -> float:
        """A4 证据门阈值，默认 0 = 关闭。

        实测校准（2026-09-05 runtime）：融合分在单通道命中时上限约 0.5-0.7，
        0.7 阈值会误杀合法查询（实测融合分 0.626 被拒）；而超纲查询的分数
        与正常查询不可分（ADR-006 A1 节）。机制保留、默认关闭，待 runtime
        校准后经 RAG_EVIDENCE_GATE_THRESHOLD 显式开启。
        """
        try:
            return float(os.getenv("RAG_EVIDENCE_GATE_THRESHOLD", "0"))
        except ValueError:
            return 0.0

    @staticmethod
    def below_evidence_gate(sources: list[dict[str, Any]], threshold: float) -> bool:
        """A4 证据门判据：检索最高融合分是否低于路由置信阈值。

        融合分（RRF 归一化到 0-1，顶块=跨通道一致性）构成"检索置信度"：
        多通道一致命中同一顶块时≈1.0，通道分歧/弱相关显著走低。空检索
        结果返回 False（由空上下文分支处理，不属于本门职责）。
        """
        if not sources:
            return False
        best = max(float(s.get("score") or 0.0) for s in sources)
        return best < threshold
