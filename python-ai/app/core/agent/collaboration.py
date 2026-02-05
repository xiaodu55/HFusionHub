"""可组合的多 Agent 专家协作协调器。"""

import asyncio
import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Union


class ExpertRole(str, Enum):
    """内置专家角色；业务可按需扩展。"""

    RETRIEVAL = "retrieval"
    ANALYSIS = "analysis"
    CRITIC = "critic"
    SYNTHESIS = "synthesis"


@dataclass
class CollaborationTask:
    query: str
    context: Dict[str, Any] = field(default_factory=dict)
    required_roles: Optional[List[ExpertRole]] = None


@dataclass
class ExpertContribution:
    role: ExpertRole
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return self.error is None


@dataclass
class CollaborationResult:
    answer: str
    contributions: List[ExpertContribution]
    errors: Dict[ExpertRole, str] = field(default_factory=dict)

    @property
    def successful_roles(self) -> List[ExpertRole]:
        return [item.role for item in self.contributions if item.succeeded]


class ExpertAgent(ABC):
    """专家 Agent 的稳定接口。"""

    role: ExpertRole

    @abstractmethod
    async def execute(self, task: CollaborationTask) -> ExpertContribution:
        pass


ExpertCallable = Union[
    Callable[[CollaborationTask], ExpertContribution],
    Callable[[CollaborationTask], Awaitable[ExpertContribution]],
]


class CallableExpertAgent(ExpertAgent):
    """将现有检索、分析或评估函数适配为专家 Agent。"""

    def __init__(self, role: ExpertRole, handler: ExpertCallable):
        self.role = role
        self.handler = handler

    async def execute(self, task: CollaborationTask) -> ExpertContribution:
        result = self.handler(task)
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, ExpertContribution):
            raise TypeError("expert handler must return ExpertContribution")
        if result.role != self.role:
            raise ValueError("expert contribution role does not match expert role")
        return result


class MultiAgentCoordinator:
    """并发执行专家、隔离单个失败，并在最后汇总成功贡献。"""

    def __init__(
        self,
        experts: Iterable[ExpertAgent],
        synthesizer: Optional[ExpertCallable] = None,
        max_concurrency: int = 4,
    ):
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        self._experts = {expert.role: expert for expert in experts}
        self._synthesizer = synthesizer
        self._max_concurrency = max_concurrency

    async def collaborate(self, task: CollaborationTask) -> CollaborationResult:
        roles = task.required_roles or list(self._experts)
        selected = [self._experts[role] for role in roles if role in self._experts]
        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def run_expert(expert: ExpertAgent) -> ExpertContribution:
            try:
                async with semaphore:
                    return await expert.execute(task)
            except Exception as exc:  # 一个专家失败不应中断其他专家
                return ExpertContribution(role=expert.role, error=str(exc))

        contributions = await asyncio.gather(*(run_expert(expert) for expert in selected))
        errors = {item.role: item.error for item in contributions if item.error}
        successful = [item for item in contributions if item.succeeded]
        answer = await self._synthesize(task, successful)
        return CollaborationResult(answer=answer, contributions=contributions, errors=errors)

    async def _synthesize(
        self, task: CollaborationTask, contributions: List[ExpertContribution]
    ) -> str:
        if self._synthesizer:
            synthesis_task = CollaborationTask(
                query=task.query,
                context={**task.context, "contributions": contributions},
                required_roles=[ExpertRole.SYNTHESIS],
            )
            result = self._synthesizer(synthesis_task)
            if inspect.isawaitable(result):
                result = await result
            if not isinstance(result, ExpertContribution):
                raise TypeError("synthesizer must return ExpertContribution")
            return result.content

        if not contributions:
            return "没有专家成功完成该任务。"
        return "\n\n".join(f"[{item.role.value}] {item.content}" for item in contributions)
