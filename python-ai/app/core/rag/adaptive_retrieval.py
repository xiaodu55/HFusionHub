"""自适应检索规划：将查询复杂度和对话上下文转换为可执行的检索参数。"""

from dataclasses import dataclass, field
from typing import Any

from .models import ComplexityLevel, IntentResult
from .multi_turn_strategy import (
    AdaptiveMultiTurnStrategy,
    ConversationContext,
    RetrievalAdjustment,
    TurnRole,
)
from .query_router import ChannelType, QueryRouter, get_router


@dataclass
class RetrievalPlan:
    """一次检索的执行计划。"""

    query: str
    top_k: int
    selected_channels: list[ChannelType]
    complexity: ComplexityLevel
    adjustment: RetrievalAdjustment
    reasoning: str
    metadata: dict[str, Any] = field(default_factory=dict)


class AdaptiveRetrievalPlanner:
    """根据意图复杂度和对话历史调整检索深度与路由。

    该规划器只生成参数，不保存用户内容；长期、短期记忆仍由
    ``ConversationMemory`` 负责。这样它可安全地被同步或流式对话复用。
    """

    _base_depth = {
        ComplexityLevel.SIMPLE: 3,
        ComplexityLevel.MEDIUM: 5,
        ComplexityLevel.COMPLEX: 8,
    }

    def __init__(self, router: QueryRouter | None = None, max_top_k: int = 10):
        self.router = router or get_router()
        self.max_top_k = max_top_k
        self.strategy = AdaptiveMultiTurnStrategy()

    async def plan(
        self,
        query: str,
        history: list[dict[str, str]] | None = None,
        intent_result: IntentResult | None = None,
    ) -> RetrievalPlan:
        complexity = intent_result.complexity if intent_result else self._infer_complexity(query)
        context = self._build_context(history, query)
        adjustment = await self.strategy.adjust_retrieval(query, context)

        depth_hint = adjustment.weight_adjustments.get("retrieval_depth")
        top_k = int(depth_hint) if depth_hint is not None else self._base_depth[complexity]
        # 深入追问即使采用话题聚焦策略，也需要比单轮多保留一些候选，
        # 避免历史限定条件把正确片段过早过滤掉。
        if context.turn_count >= 4:
            top_k = max(top_k, self._base_depth[complexity] + 2)
        top_k = max(1, min(top_k, self.max_top_k))

        route = self.router.route(query)
        return RetrievalPlan(
            query=query,
            top_k=top_k,
            selected_channels=route.selected_channels,
            complexity=complexity,
            adjustment=adjustment,
            reasoning=(
                f"complexity={complexity.value}; "
                f"strategy={adjustment.strategy_type.value}; "
                f"route={route.strategy.value}"
            ),
            metadata={"route_confidence": route.confidence, "turn_count": context.turn_count},
        )

    @staticmethod
    def _build_context(
        history: list[dict[str, str]] | None, query: str
    ) -> ConversationContext:
        context = ConversationContext(conversation_id="request")
        for item in history or []:
            role = TurnRole.USER if item.get("role") == "user" else TurnRole.ASSISTANT
            content = item.get("content", "")
            if content:
                context.add_turn(role, content)
        context.add_turn(TurnRole.USER, query)
        return context

    @staticmethod
    def _infer_complexity(query: str) -> ComplexityLevel:
        lowered = query.lower()
        complex_markers = ("比较", "对比", "区别", "关系", "原因", "影响", "步骤", "如何", " and ", " vs ")
        if len(query) >= 80 or sum(marker in lowered for marker in complex_markers) >= 2:
            return ComplexityLevel.COMPLEX
        if len(query) >= 30 or any(marker in lowered for marker in complex_markers):
            return ComplexityLevel.MEDIUM
        return ComplexityLevel.SIMPLE


_planner: AdaptiveRetrievalPlanner | None = None


def get_adaptive_retrieval_planner() -> AdaptiveRetrievalPlanner:
    global _planner
    if _planner is None:
        _planner = AdaptiveRetrievalPlanner()
    return _planner


def reset_adaptive_retrieval_planner() -> None:
    global _planner
    _planner = None
