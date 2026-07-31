"""QA 对生成（实验特性 RAG_QA_GENERATION_ENABLED）纯逻辑测试。

覆盖：正常生成 / 去重 / 总量上限 / 单分块上限 / LLM 失败软化 /
非 JSON 输出 / 短分块跳过。
"""

import pytest

from app.core.chunker.text_chunker import VectorChunk
from app.core.rag.qa_generator import generate_qa_chunks

LONG_TEXT = "这是一段足够长的资料内容，" * 12  # > 80 字符


def make_chunk(index: int, content: str) -> VectorChunk:
    return VectorChunk(
        chunk_id=f"1_{index}",
        index=index,
        content=content,
        block_type="PARAGRAPH",
        outline_path=["第一章"],
        metadata={},
    )


class FakeLLM:
    """按调用次序返回预设输出；元素为 Exception 时抛出。"""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0

    async def chat(self, messages=None, temperature=None):
        out = self.outputs[min(self.calls, len(self.outputs) - 1)]
        self.calls += 1
        if isinstance(out, Exception):
            raise out

        class _R:
            content = out

        return _R()


@pytest.mark.asyncio
async def test_generates_qa_chunks_with_metadata():
    llm = FakeLLM(['[{"q": "年假有几天？", "a": "五天带薪年假。"}, {"q": "年假怎么申请？", "a": "提前三天在系统申请。"}]'])
    chunks = await generate_qa_chunks(
        [make_chunk(0, LONG_TEXT)], document_id="7", document_title="员工手册", llm=llm
    )
    assert len(chunks) == 2
    assert chunks[0].block_type == "QA"
    assert chunks[0].chunk_id == "7_qa1"
    assert chunks[0].content == "年假有几天？\n五天带薪年假。"
    assert chunks[0].metadata["qa_generated"] is True
    assert chunks[0].metadata["question"] == "年假有几天？"
    assert chunks[0].metadata["document_title"] == "员工手册"


@pytest.mark.asyncio
async def test_dedups_same_question():
    llm = FakeLLM(['[{"q": "年假有几天？", "a": "五天。"}, {"q": "年假有几天", "a": "五天带薪。"}]'])
    chunks = await generate_qa_chunks([make_chunk(0, LONG_TEXT)], document_id="7", document_title="t", llm=llm)
    assert len(chunks) == 1


@pytest.mark.asyncio
async def test_respects_max_total():
    llm = FakeLLM(['[{"q": "Q1", "a": "A1"}, {"q": "Q2", "a": "A2"}, {"q": "Q3", "a": "A3"}]'])
    chunks = await generate_qa_chunks(
        [make_chunk(0, LONG_TEXT)], document_id="7", document_title="t", llm=llm, max_total=1
    )
    assert len(chunks) == 1


@pytest.mark.asyncio
async def test_respects_max_per_chunk():
    llm = FakeLLM(['[{"q": "Q1", "a": "A1"}, {"q": "Q2", "a": "A2"}, {"q": "Q3", "a": "A3"}]'])
    chunks = await generate_qa_chunks(
        [make_chunk(0, LONG_TEXT)], document_id="7", document_title="t", llm=llm, max_per_chunk=2
    )
    assert len(chunks) == 2


@pytest.mark.asyncio
async def test_llm_failure_is_soft():
    llm = FakeLLM([RuntimeError("llm down")])
    chunks = await generate_qa_chunks([make_chunk(0, LONG_TEXT)], document_id="7", document_title="t", llm=llm)
    assert chunks == []


@pytest.mark.asyncio
async def test_non_json_output_is_skipped():
    llm = FakeLLM(["抱歉，我无法基于这段资料生成问答对。"])
    chunks = await generate_qa_chunks([make_chunk(0, LONG_TEXT)], document_id="7", document_title="t", llm=llm)
    assert chunks == []


@pytest.mark.asyncio
async def test_short_chunks_are_skipped_without_llm_call():
    llm = FakeLLM(['[{"q": "Q1", "a": "A1"}]'])
    chunks = await generate_qa_chunks(
        [make_chunk(0, "太短")], document_id="7", document_title="t", llm=llm
    )
    assert chunks == []
    assert llm.calls == 0


@pytest.mark.asyncio
async def test_code_fence_output_is_tolerated():
    llm = FakeLLM(["```json\n[{\"q\": \"Q1\", \"a\": \"A1\"}]\n```"])
    chunks = await generate_qa_chunks([make_chunk(0, LONG_TEXT)], document_id="7", document_title="t", llm=llm)
    assert len(chunks) == 1
