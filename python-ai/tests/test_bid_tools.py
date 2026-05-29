"""招投标领域内建工具单元测试（B2 垂直化）。

覆盖：
  1. bid_calc_scoring —— 综合分/加权分/得分率；缺失得分标注
  2. bid_list_requirements —— 按类别分组 + 置信度过滤
  3. bid_render_template —— {{var}} 替换 + 缺失变量标注
  4. 工具经 ToolRegistry 注册与执行（非 V1 白名单可见性）
"""

from __future__ import annotations

import pytest

from app.core.bid.tools import (
    BID_CALC_SCORING_SPEC,
    BID_LIST_REQUIREMENTS_SPEC,
    BID_RENDER_TEMPLATE_SPEC,
    BidCalcScoringTool,
    BidListRequirementsTool,
    BidRenderTemplateTool,
)
from app.core.tools.registry import ToolRegistry
from app.core.tools.spec import RiskLevel


@pytest.mark.asyncio
async def test_calc_scoring_computes_weighted_total():
    tool = BidCalcScoringTool()
    result = await tool.execute(
        points=[
            {"name": "技术分", "max_score": 50},
            {"name": "商务分", "max_score": 30, "weight": 0.4},
            {"name": "价格分", "max_score": 20, "weight": 0.6},
        ],
        scores=[
            {"name": "技术分", "score": 45},
            {"name": "商务分", "score": 27},
            {"name": "价格分", "score": 18},
        ],
    )

    assert "error" not in result
    assert result["total_score"] == 90.0
    assert result["max_total"] == 100.0
    assert result["score_percent"] == 90.0
    # 加权分 = 27*0.4 + 18*0.6 = 10.8 + 10.8 = 21.6
    assert result["weighted_total"] == 21.6
    assert len(result["items"]) == 3


@pytest.mark.asyncio
async def test_calc_scoring_marks_missing_score():
    tool = BidCalcScoringTool()
    result = await tool.execute(
        points=[{"name": "技术分", "max_score": 50}],
        scores=[{"name": "价格分", "score": 10}],  # 未提供技术分
    )
    assert result["items"][0]["score"] is None
    assert "未提供该项得分" in result["items"][0]["note"]


@pytest.mark.asyncio
async def test_list_requirements_groups_by_category_and_filters_confidence():
    tool = BidListRequirementsTool()
    result = await tool.execute(
        requirements=[
            {"category": "qualification", "requirement": "资质A", "confidence": 0.9},
            {"category": "qualification", "requirement": "资质B", "confidence": 0.4},
            {"category": "technical", "requirement": "技术C", "confidence": 0.8},
            {"category": "unknown_cat", "requirement": "未分类", "confidence": 0.7},
        ],
        min_confidence=0.5,
    )

    assert result["total"] == 3  # 0.4 被过滤
    assert len(result["grouped"]["qualification"]) == 1
    assert len(result["grouped"]["technical"]) == 1
    assert result["grouped"]["performance"] == []
    assert len(result["unclassified"]) == 1


@pytest.mark.asyncio
async def test_render_template_substitutes_and_reports_missing():
    tool = BidRenderTemplateTool()
    result = await tool.execute(
        template="致：{{buyer}}\n本公司{{company}}承诺按期交付。",
        data={"buyer": "某采购中心", "company": "示例公司"},
    )
    assert result["rendered"] == "致：某采购中心\n本公司示例公司承诺按期交付。"
    assert result["missing_variables"] == []

    result2 = await tool.execute(
        template="编号{{tender_number}} 未提供变量",
        data={},
    )
    assert "{{tender_number}}" in result2["rendered"]
    assert result2["missing_variables"] == ["tender_number"]


def test_bid_tools_registered_and_visible_to_non_v1():
    registry = ToolRegistry(knowledge_base_id=1)

    # 非 V1 可见（MCP / 内部调用方）
    tools = registry.get_tools(v1_only=False)
    names = {t["name"] for t in tools}
    assert {"bid_calc_scoring", "bid_list_requirements", "bid_render_template"} <= names

    # V1 白名单不可见（不改变既有 Agent 行为）
    v1_names = {t["name"] for t in registry.get_tools()}
    assert "bid_calc_scoring" not in v1_names

    # 风险分级：渲染 = READ_WRITE，其余 = READ_ONLY
    assert BID_RENDER_TEMPLATE_SPEC.risk_level == RiskLevel.READ_WRITE
    assert BID_CALC_SCORING_SPEC.risk_level == RiskLevel.READ_ONLY
    assert BID_LIST_REQUIREMENTS_SPEC.risk_level == RiskLevel.READ_ONLY


@pytest.mark.asyncio
async def test_bid_tools_executable_through_registry():
    # 非 V1 工具经 agent_version="0.0" registry（MCP/内部调用方路径）执行
    registry = ToolRegistry(knowledge_base_id=1, agent_version="0.0")

    result = await registry.execute(
        "bid_calc_scoring",
        {"points": [{"name": "技术分", "max_score": 50}], "scores": [{"name": "技术分", "score": 40}]},
    )
    assert result.ok
    assert result.data["total_score"] == 40.0

    render = await registry.execute(
        "bid_render_template",
        {"template": "供应商：{{company}}", "data": {"company": "X公司"}},
    )
    assert result.ok
    assert render.ok
    assert "X公司" in render.data["rendered"]

    # V1 registry 拒绝执行非白名单工具
    v1_registry = ToolRegistry(knowledge_base_id=1)
    denied = await v1_registry.execute(
        "bid_calc_scoring",
        {"points": [{"name": "技术分", "max_score": 50}]},
    )
    assert not denied.ok
    assert denied.error_code == "knowledge_base_scope_denied"
