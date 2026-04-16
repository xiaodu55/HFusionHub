from app.core.rag.postprocessor import Postprocessor


def _candidate() -> dict:
    return {
        "content": "虚拟线程由 JVM 管理，适合高并发 I/O 场景，并且创建成本和内存占用都明显低于平台线程。",
        "score": 1.0,
        "document_id": "3",
        "knowledge_base_id": 2,
        "source": "keyword",
        "metadata": {
            "chunk_id": "3_chunk_0007",
            "knowledge_base_id": 2,
            "evidence_score": 0.2,
        },
    }


def test_scoped_summary_keeps_substantive_kb_candidate_when_normal_gate_rejects_it():
    postprocessor = Postprocessor(min_score=0.35)

    results, decisions = postprocessor.process_with_debug(
        [_candidate()],
        query="请总结当前知识库最重要的三条内容并标注来源",
        allow_scoped_summary=True,
    )

    assert [result.document_id for result in results] == ["3"]
    assert decisions[0]["decision"] == "accepted"
    assert decisions[0]["bypass_reason"] == "explicit_knowledge_base_summary"


def test_normal_question_does_not_bypass_the_evidence_threshold():
    postprocessor = Postprocessor(min_score=0.35)

    results, decisions = postprocessor.process_with_debug(
        [_candidate()],
        query="数据库管理员的电话号码是多少",
        allow_scoped_summary=False,
    )

    assert results == []
    assert decisions[0]["decision"] == "filtered_low_evidence"
