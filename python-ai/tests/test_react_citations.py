"""A3 引用溯源纯函数测试：编号上下文格式化与答案 [n] 标注解析。

覆盖 react 管线中"答案实际标注的引用"链路的确定性部分：
- ``_format_numbered_context``：块编号与 sources 序号一一对应；
- ``ReactAgent._parse_cited_chunk_ids``：[n] → chunk_id，越界/不可见标注忽略。
"""

from types import SimpleNamespace

from app.core.agent.react import ReactAgent, _format_numbered_context


def _result(source="vector", score=0.9, content="第一块内容。", chunk_id="a#1", title="文档A"):
    return SimpleNamespace(
        source=source,
        score=score,
        content=content,
        chunk_id=chunk_id,
        document_id=1,
        knowledge_base_id=101,
        metadata={"document_title": title},
    )


def test_format_numbered_context_pairs_numbers_with_sources():
    text, sources = _format_numbered_context([
        _result(),
        _result(source="keyword", score=0.5, content="第二块内容。", chunk_id="b#2", title="文档B"),
    ])
    assert text.startswith("[1] (语义匹配, 相似度: 0.90)\n第一块内容。")
    assert "[2] (关键词匹配, 相似度: 0.50)\n第二块内容。" in text
    # 编号 n ↔ sources[n-1]：答案 [n] 标注映射的基础
    assert [s["chunk_id"] for s in sources] == ["a#1", "b#2"]


def test_parse_cited_chunk_ids_maps_and_dedupes():
    sources = [{"chunk_id": "a#1"}, {"chunk_id": "b#2"}, {"chunk_id": "c#3"}]
    answer = "第一个论断 [1]。第二个论断 [3][3]，另一个 [2]。"
    assert ReactAgent._parse_cited_chunk_ids(answer, sources) == ["a#1", "c#3", "b#2"]


def test_parse_cited_chunk_ids_ignores_out_of_range_and_invisible():
    sources = [{"chunk_id": "a#1"}, {"chunk_id": "b#2"}]
    answer = "引用 [1] 与 [9]（越界）和 [0]（非法）。"
    assert ReactAgent._parse_cited_chunk_ids(answer, sources) == ["a#1"]
    # 不可见块（已被压缩掉）：标注无效
    answer_visible = "引用 [1] 与 [2]。"
    assert ReactAgent._parse_cited_chunk_ids(
        answer_visible, sources, visible_numbers=[1]) == ["a#1"]


def test_parse_cited_chunk_ids_empty_inputs():
    assert ReactAgent._parse_cited_chunk_ids("", [{"chunk_id": "a#1"}]) == []
    assert ReactAgent._parse_cited_chunk_ids("无标注回答", []) == []
    assert ReactAgent._parse_cited_chunk_ids("无标注回答", [{"chunk_id": "a#1"}]) == []
