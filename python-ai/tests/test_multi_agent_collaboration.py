import asyncio

import pytest

from app.core.agent.collaboration import (
    CallableExpertAgent,
    CollaborationTask,
    ExpertContribution,
    ExpertRole,
    MultiAgentCoordinator,
)


@pytest.mark.asyncio
async def test_experts_run_concurrently_and_are_synthesized():
    started = []

    async def retrieval(task):
        started.append("retrieval")
        await asyncio.sleep(0.01)
        return ExpertContribution(ExpertRole.RETRIEVAL, "检索结果")

    async def analysis(task):
        started.append("analysis")
        await asyncio.sleep(0.01)
        return ExpertContribution(ExpertRole.ANALYSIS, "分析结论")

    coordinator = MultiAgentCoordinator([
        CallableExpertAgent(ExpertRole.RETRIEVAL, retrieval),
        CallableExpertAgent(ExpertRole.ANALYSIS, analysis),
    ])
    result = await coordinator.collaborate(CollaborationTask(query="测试问题"))

    assert set(started) == {"retrieval", "analysis"}
    assert result.successful_roles == [ExpertRole.RETRIEVAL, ExpertRole.ANALYSIS]
    assert "检索结果" in result.answer
    assert "分析结论" in result.answer


@pytest.mark.asyncio
async def test_failed_expert_does_not_cancel_other_experts():
    async def fail(task):
        raise RuntimeError("temporary failure")

    async def critic(task):
        return ExpertContribution(ExpertRole.CRITIC, "质量通过")

    coordinator = MultiAgentCoordinator([
        CallableExpertAgent(ExpertRole.RETRIEVAL, fail),
        CallableExpertAgent(ExpertRole.CRITIC, critic),
    ])
    result = await coordinator.collaborate(CollaborationTask(query="测试问题"))

    assert result.errors[ExpertRole.RETRIEVAL] == "temporary failure"
    assert result.successful_roles == [ExpertRole.CRITIC]
    assert result.answer == "[critic] 质量通过"
