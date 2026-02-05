import pytest

from app.core.rag.adaptive_retrieval import AdaptiveRetrievalPlanner
from app.core.rag.models import ComplexityLevel, DomainType, IntentResult, IntentType


@pytest.mark.asyncio
async def test_complex_query_uses_deeper_retrieval():
    planner = AdaptiveRetrievalPlanner(max_top_k=10)
    intent = IntentResult(
        intent=IntentType.COMPARISON,
        complexity=ComplexityLevel.COMPLEX,
        domain=DomainType.TECH,
        confidence=0.9,
    )

    plan = await planner.plan("比较向量检索和知识图谱检索的实现、性能与适用场景", intent_result=intent)

    assert plan.top_k == 8
    assert plan.complexity == ComplexityLevel.COMPLEX
    assert plan.selected_channels


@pytest.mark.asyncio
async def test_multi_turn_history_can_increase_retrieval_depth():
    planner = AdaptiveRetrievalPlanner(max_top_k=10)
    history = [
        {"role": "user", "content": "先介绍一下 RAG"},
        {"role": "assistant", "content": "RAG 是检索增强生成。"},
        {"role": "user", "content": "再说说它和知识图谱的关系"},
        {"role": "assistant", "content": "可以结合实体关系。"},
    ]

    plan = await planner.plan("请继续详细解释", history=history)

    assert plan.top_k == 5
    assert plan.metadata["turn_count"] == 5
