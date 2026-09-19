"""RetrievalPipeline 单测：检索入口口径、依赖分层并行分解与降级判据。

覆盖第六十批自 ``react.py`` 抽出的检索编排（``app/core/agent/retrieval_pipeline.py``）：
- ``retrieve_context`` / ``retrieve_context_for_stream`` 三处历史口径分叉（本批有意保留）；
- ``safe_compress`` 的四条路径（空短路 / 策略拒压 / 过激压缩守卫 / 正常放行）；
- ``decompose_retrieve_merge_context`` 的依赖分层并行、内容去重、
  部分失败降级、全部失败升格 ``RuntimeError``、执行计划漏项兜底；
- ``empty_context_reply`` 的"库空 vs 无相关证据"文案分流。

证据门与 groundedness 判据的测试见 ``test_react_evidence_gate.py``。
"""

from types import SimpleNamespace

import pytest

import app.core.agent.retrieval_pipeline as rp_module
from app.core.agent.retrieval_pipeline import (
    NO_SUFFICIENT_EVIDENCE_REPLY,
    RetrievalPipeline,
)
from app.core.rag.query_decomposer import (
    DecompositionResult,
    SubQuestion,
)


class _FakeRetrieverResult:
    def __init__(self, results):
        self.results = results


def _chunk(content: str, chunk_id: str, score: float = 0.8):
    return SimpleNamespace(
        source="vector",
        score=score,
        content=content,
        chunk_id=chunk_id,
        document_id=1,
        knowledge_base_id=101,
        metadata={"document_title": "文档A"},
    )


class _RecordingRetriever:
    """记录每次 retrieve 的 kwargs；按调用次序给出结果或抛错。

    ``script`` 每一项可以是结果列表（成功）或异常实例（失败）。
    """

    def __init__(self, script=None, results=None, exc=None):
        self.calls: list[dict] = []
        self._script = script
        self._results = results if results is not None else []
        self._exc = exc

    async def retrieve(self, **kwargs):
        self.calls.append(kwargs)
        if self._script is not None:
            item = self._script[len(self.calls) - 1]
            if isinstance(item, Exception):
                raise item
            return _FakeRetrieverResult(item)
        if self._exc is not None:
            raise self._exc
        return _FakeRetrieverResult(self._results)


class _RecordingPlanner:
    def __init__(self):
        self.calls: list[dict] = []

    async def plan(self, *, query, history=None, intent_result=None):
        self.calls.append({"query": query, "history": history})
        return SimpleNamespace(query=f"rewritten::{query}", top_k=7)


class _StubDecomposer:
    def __init__(self, result):
        self._result = result

    async def decompose(self, *, query, intent_result=None, history=None):
        return self._result


@pytest.fixture
def seams(monkeypatch):
    """把规划器换成可记录桩、让压缩直通（本模块只测检索编排）。"""
    planner = _RecordingPlanner()
    monkeypatch.setattr(rp_module, "get_adaptive_retrieval_planner", lambda: planner)

    def use_retriever(retriever):
        monkeypatch.setattr(rp_module, "get_retriever", lambda: retriever)
        return retriever

    monkeypatch.setattr(
        RetrievalPipeline, "safe_compress",
        lambda self, rag_context, target_ratio=None, query=None: _passthrough(rag_context))
    return SimpleNamespace(planner=planner, use_retriever=use_retriever, monkeypatch=monkeypatch)


async def _passthrough(rag_context):
    return rag_context, False, []


def set_decomposition(seams, sub_questions, execution_plan):
    """固定分解产物：本模块不测分解器本身（见 test_query_decomposer.py）。"""
    result = DecompositionResult(
        original_query="原始问题",
        sub_questions=sub_questions,
        execution_plan=execution_plan,
        strategy_used="rule",
        confidence=0.9,
    )
    seams.monkeypatch.setattr(
        rp_module, "get_query_decomposer",
        lambda *a, **k: _StubDecomposer(result))


# ---------------------------------------------------------------------------
# 两条检索入口的口径分叉（第六十批有意原样保留）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retrieve_context_forwards_history_and_applies_top_k_override(seams):
    retriever = seams.use_retriever(_RecordingRetriever(results=[_chunk("第一块内容。", "a#1")]))
    pipeline = RetrievalPipeline(knowledge_base_id=7, retrieval_top_k=3)

    context, sources, kb_id = await pipeline.retrieve_context(
        "问题", history=[{"role": "user", "content": "上文"}])

    kwargs = retriever.calls[0]
    assert kwargs["conversation_history"] == [{"role": "user", "content": "上文"}]
    # retrieval_top_k 覆盖规划值（规划器返回 7）
    assert kwargs["top_k"] == 3
    assert kwargs["query"] == "rewritten::问题"
    assert kwargs["knowledge_base_id"] == 7
    assert context.startswith("[1] (语义匹配, 相似度: 0.80)")
    assert [s["chunk_id"] for s in sources] == ["a#1"]
    assert kb_id == 7


@pytest.mark.asyncio
async def test_retrieve_context_without_top_k_uses_planned_value(seams):
    retriever = seams.use_retriever(_RecordingRetriever(results=[]))
    await RetrievalPipeline(knowledge_base_id=7).retrieve_context("问题")
    assert retriever.calls[0]["top_k"] == 7


@pytest.mark.asyncio
async def test_stream_entry_omits_history_keeps_planned_top_k(seams):
    """run_stream 快路径的历史形态：历史只进规划器，top_k 不被覆盖。"""
    retriever = seams.use_retriever(_RecordingRetriever(results=[_chunk("块。", "a#1")]))
    pipeline = RetrievalPipeline(knowledge_base_id=7, retrieval_top_k=3)

    await pipeline.retrieve_context_for_stream("问题", history=[{"role": "user", "content": "上文"}])

    kwargs = retriever.calls[0]
    assert "conversation_history" not in kwargs
    assert kwargs["top_k"] == 7
    # 规划器仍然收到历史
    assert seams.planner.calls[0]["history"] == [{"role": "user", "content": "上文"}]


@pytest.mark.asyncio
async def test_empty_recall_is_empty_triplet_not_none(seams):
    """检索成功但无结果 ≠ 服务故障：前者返回 ("", [], kb)，后者返回 None。"""
    seams.use_retriever(_RecordingRetriever(results=[]))
    assert await RetrievalPipeline(7).retrieve_context("问题") == ("", [], 7)


@pytest.mark.asyncio
async def test_retrieve_context_degrades_to_none_on_failure(seams):
    """M10：检索服务故障返回 None（调用方发 retrieval_error），不伪装成无证据。"""
    seams.use_retriever(_RecordingRetriever(exc=RuntimeError("milvus down")))
    assert await RetrievalPipeline(7).retrieve_context("问题") is None


@pytest.mark.asyncio
async def test_stream_entry_lets_failure_propagate(seams):
    seams.use_retriever(_RecordingRetriever(exc=RuntimeError("milvus down")))
    with pytest.raises(RuntimeError, match="milvus down"):
        await RetrievalPipeline(7).retrieve_context_for_stream("问题")


# ---------------------------------------------------------------------------
# 压缩入口
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_safe_compress_short_circuits_on_empty_context(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("空上下文不应创建压缩器")

    monkeypatch.setattr(rp_module, "get_compressor", boom)
    context, compressed, visible = await RetrievalPipeline(7).safe_compress("")
    assert (context, compressed, visible) == ("", False, [])


class _StubStrategy:
    def __init__(self, compressed, did_compress, visible, token_counts):
        self._compressed = compressed
        self._did_compress = did_compress
        self._visible = visible
        self._token_counts = token_counts
        self.queries: list = []

    async def compress_numbered_blocks(self, text, config, query=None):
        self.queries.append(query)
        return self._compressed, self._visible, self._did_compress

    def estimate_tokens(self, text):
        return self._token_counts.get(text, 0)

    def list_block_numbers(self, text):
        return [1, 2]


def _stub_compressor(monkeypatch, strategy):
    monkeypatch.setattr(
        rp_module, "get_compressor",
        lambda *a, **k: SimpleNamespace(strategy=strategy))
    return strategy


@pytest.mark.asyncio
async def test_safe_compress_keeps_original_when_strategy_declines(monkeypatch):
    original = "[1] (语义匹配, 相似度: 0.90)\n内容。"
    strategy = _stub_compressor(monkeypatch, _StubStrategy(
        original, False, [1], {original: 100}))

    text, compressed, visible = await RetrievalPipeline(7).safe_compress(
        original, target_ratio=0.8, query="问题")
    assert (text, compressed, visible) == (original, False, [1])
    assert strategy.queries == ["问题"]


@pytest.mark.asyncio
async def test_safe_compress_reverts_over_aggressive_compression(monkeypatch):
    """证据完整性守卫：压缩后 <25% 且原文超 500 token 时回退原文，块号取全集。"""
    original = "原始长上下文"
    crushed = "压缩后只剩一句"
    _stub_compressor(monkeypatch, _StubStrategy(
        crushed, True, [1], {original: 1000, crushed: 100}))

    text, compressed, visible = await RetrievalPipeline(7).safe_compress(
        original, target_ratio=0.8)
    assert (text, compressed, visible) == (original, False, [1, 2])


@pytest.mark.asyncio
async def test_safe_compress_accepts_moderate_compression(monkeypatch):
    original = "原始长上下文"
    trimmed = "适度压缩后"
    _stub_compressor(monkeypatch, _StubStrategy(
        trimmed, True, [1], {original: 1000, trimmed: 800}))

    text, compressed, visible = await RetrievalPipeline(7).safe_compress(
        original, target_ratio=0.8)
    assert (text, compressed, visible) == (trimmed, True, [1])


# ---------------------------------------------------------------------------
# 分解检索：依赖分层并行 + 合并去重
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_decompose_returns_none_when_single_sub_question(seams):
    """needs_decomposition 为假时交回调用方走单路检索。"""
    seams.use_retriever(_RecordingRetriever(results=[]))
    q1 = SubQuestion(id="q1", content="唯一子问题")
    set_decomposition(seams, [q1], [[q1]])

    assert await RetrievalPipeline(7).decompose_retrieve_merge_context(
        "问题", None, None) is None


@pytest.mark.asyncio
async def test_decompose_executes_dependency_layers_in_order(seams):
    """层间串行、层内并行：依赖子问题的检索排在其依赖之后。"""
    q1 = SubQuestion(id="q1", content="A 的优缺点")
    q2 = SubQuestion(id="q2", content="B 的优缺点")
    q3 = SubQuestion(id="q3", content="综合对比", dependencies=["q1", "q2"])
    set_decomposition(seams, [q1, q2, q3], [[q1, q2], [q3]])

    retriever = seams.use_retriever(_RecordingRetriever(script=[
        [_chunk("A 内容。", "a#1")],
        [_chunk("B 内容。", "b#2")],
        [_chunk("对比内容。", "c#3")],
    ]))
    pipeline = RetrievalPipeline(7, retrieval_top_k=4)

    raw_context, sources, rag_context, was_compressed, visible, meta = \
        await pipeline.decompose_retrieve_merge_context("A 和 B 各有什么优缺点？", None, None)

    assert [c["query"] for c in retriever.calls] == [
        "rewritten::A 的优缺点", "rewritten::B 的优缺点", "rewritten::综合对比"]
    # 分解路径吃 retrieval_top_k，并把历史透传给检索器
    assert all(c["top_k"] == 4 for c in retriever.calls)
    assert all("conversation_history" in c for c in retriever.calls)
    # 合并后是单一编号空间：三块按执行次序连续编号
    assert "[3] " in raw_context and "[1] " in raw_context
    assert [s["chunk_id"] for s in sources] == ["a#1", "b#2", "c#3"]
    assert was_compressed is False and visible == []
    assert meta["original_query"] == "原始问题"


@pytest.mark.asyncio
async def test_decompose_dedupes_identical_content_across_sub_questions(seams):
    """同一块被多个子问题召回时只进上下文一次（避免重复计数与预算浪费）。"""
    q1 = SubQuestion(id="q1", content="A")
    q2 = SubQuestion(id="q2", content="B")
    set_decomposition(seams, [q1, q2], [[q1, q2]])

    shared = _chunk("同一块内容。", "same#1")
    retriever = seams.use_retriever(_RecordingRetriever(script=[
        [shared, _chunk("独有块。", "only#2")],
        [shared],
    ]))

    _, sources, _, _, _, _ = await RetrievalPipeline(7).decompose_retrieve_merge_context(
        "问题", None, None)
    assert [s["chunk_id"] for s in sources] == ["same#1", "only#2"]
    assert len(retriever.calls) == 2


@pytest.mark.asyncio
async def test_decompose_skips_sub_question_whose_dependency_is_unplanned(seams):
    """层内 can_execute 为假的子问题被跳过，但不阻塞后续层。"""
    q1 = SubQuestion(id="q1", content="A")
    blocked = SubQuestion(id="q2", content="B", dependencies=["never-planned"])
    q3 = SubQuestion(id="q3", content="C")
    set_decomposition(seams, [q1, blocked, q3], [[q1, blocked], [q3]])

    retriever = seams.use_retriever(_RecordingRetriever(script=[
        [_chunk("A。", "a#1")],
        [_chunk("C。", "c#3")],
    ]))
    _, sources, _, _, _, _ = await RetrievalPipeline(7).decompose_retrieve_merge_context(
        "问题", None, None)
    # q2 已在 execution_plan 中（不触发兜底分支），依赖缺失故整条路径都不检索它
    assert [c["query"] for c in retriever.calls] == ["rewritten::A", "rewritten::C"]
    assert [s["chunk_id"] for s in sources] == ["a#1", "c#3"]


@pytest.mark.asyncio
async def test_decompose_falls_back_for_questions_missing_from_plan(seams):
    """防御分支：execution_plan 漏掉的子问题仍被兜底检索，保证覆盖总量。"""
    q1 = SubQuestion(id="q1", content="A")
    q2 = SubQuestion(id="q2", content="B")
    set_decomposition(seams, [q1, q2], [[q1]])

    retriever = seams.use_retriever(_RecordingRetriever(script=[
        [_chunk("A。", "a#1")],
        [_chunk("B。", "b#2")],
    ]))
    _, sources, _, _, _, _ = await RetrievalPipeline(7).decompose_retrieve_merge_context(
        "问题", None, None)
    assert sorted(c["query"] for c in retriever.calls) == ["rewritten::A", "rewritten::B"]
    assert sorted(s["chunk_id"] for s in sources) == ["a#1", "b#2"]


# ---------------------------------------------------------------------------
# 分解检索的失败口径（M10）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_decompose_raises_when_all_sub_questions_fail(seams):
    q1 = SubQuestion(id="q1", content="A")
    q2 = SubQuestion(id="q2", content="B")
    set_decomposition(seams, [q1, q2], [[q1, q2]])
    seams.use_retriever(_RecordingRetriever(script=[
        RuntimeError("milvus down"),
        RuntimeError("milvus down"),
    ]))

    with pytest.raises(RuntimeError, match="all sub-question retrievals failed") as excinfo:
        await RetrievalPipeline(7).decompose_retrieve_merge_context("问题", None, None)
    assert isinstance(excinfo.value.__cause__, RuntimeError)


@pytest.mark.asyncio
async def test_decompose_degrades_when_only_some_sub_questions_fail(seams):
    """单个子问题失败按空结果降级，不拖垮整批。"""
    q1 = SubQuestion(id="q1", content="A")
    q2 = SubQuestion(id="q2", content="B")
    set_decomposition(seams, [q1, q2], [[q1, q2]])
    seams.use_retriever(_RecordingRetriever(script=[
        RuntimeError("keyword channel down"),
        [_chunk("B 的内容。", "b#2")],
    ]))

    raw_context, sources, _, _, _, _ = await RetrievalPipeline(7).decompose_retrieve_merge_context(
        "问题", None, None)
    assert [s["chunk_id"] for s in sources] == ["b#2"]
    assert "B 的内容。" in raw_context


# ---------------------------------------------------------------------------
# 空上下文文案分流
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_context_reply_distinguishes_empty_kb_from_no_recall(monkeypatch):
    import app.core.vectorstore.milvus_store as milvus_module

    monkeypatch.setattr(
        milvus_module, "_get_store",
        lambda: SimpleNamespace(all_chunks=lambda knowledge_base_id: []))
    reply = await RetrievalPipeline(7).empty_context_reply()
    assert "还没有可检索的内容" in reply

    monkeypatch.setattr(
        milvus_module, "_get_store",
        lambda: SimpleNamespace(all_chunks=lambda knowledge_base_id: [{"id": 1}]))
    assert await RetrievalPipeline(7).empty_context_reply() == NO_SUFFICIENT_EVIDENCE_REPLY


@pytest.mark.asyncio
async def test_empty_context_reply_is_conservative_when_store_unreachable(monkeypatch):
    """无法确认语料规模时按"有内容但证据不足"处理，避免误报"库是空的"。"""
    import app.core.vectorstore.milvus_store as milvus_module

    def boom():
        raise RuntimeError("milvus unreachable")

    monkeypatch.setattr(milvus_module, "_get_store", boom)
    assert await RetrievalPipeline(7).empty_context_reply() == NO_SUFFICIENT_EVIDENCE_REPLY
