"""招投标领域内建工具（B2）。

P0 阶段插件沙箱被 TLS 阻塞（见 PLUGIN_RUNNER_TLS.md），领域工具全部做成
Python 内建工具——确定性、无副作用，便于评测与回归：

  - ``bid_calc_scoring``      评分点计算（综合分/加权分/百分比），供撰写、
                              自检 Agent 校验评分数学是否正确
  - ``bid_list_requirements`` 需求清单按类别/置信度过滤分组，供撰写 Agent
                              按"资质/业绩/技术/商务/格式"逐节取用
  - ``bid_render_template``   标书分节模板渲染（``{{var}}`` 替换），产出草稿
                              片段；READ_WRITE —— 经审批流放行（写草稿）

P0 工具数据一律以入参 JSON 传入（不直连 bid 库），保持确定性可评测。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.core.tools.base import BaseTool
from app.core.tools.spec import Permissions, RiskLevel, ToolSpec

# 需求类别（与 Java 侧 bid_requirement.category 保持一致）
REQUIREMENT_CATEGORIES: tuple = (
    "qualification",
    "performance",
    "technical",
    "commercial",
    "format",
    "disqualification_risk",
)


def _to_number(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class BidCalcScoringTool(BaseTool):
    """评分点计算：综合分/加权分/百分比。"""

    async def execute(self, points=None, scores=None, **kwargs) -> Dict[str, Any]:
        if not isinstance(points, list) or not points:
            return {"error": "points 必须为非空数组"}
        if not isinstance(scores, list):
            return {"error": "scores 必须为数组"}

        score_by_name = {}
        for item in scores:
            if not isinstance(item, dict) or "name" not in item:
                continue
            val = _to_number(item.get("score"))
            if val is not None:
                score_by_name[str(item["name"])] = val

        items: List[Dict[str, Any]] = []
        total = 0.0
        max_total = 0.0
        weighted = 0.0
        weight_sum = 0.0
        for point in points:
            if not isinstance(point, dict):
                continue
            name = str(point.get("name") or "")
            max_score = _to_number(point.get("max_score")) or 0.0
            weight = _to_number(point.get("weight")) or 0.0
            actual = score_by_name.get(name)
            if actual is None:
                items.append({
                    "name": name,
                    "max_score": max_score,
                    "score": None,
                    "percent": None,
                    "note": "未提供该项得分",
                })
                max_total += max_score
                weight_sum += weight
                continue
            items.append({
                "name": name,
                "max_score": max_score,
                "score": actual,
                "percent": round(actual / max_score * 100, 2) if max_score else None,
                "weight": weight or None,
            })
            total += actual
            max_total += max_score
            weighted += actual * weight
            weight_sum += weight

        if not items:
            return {"error": "points 数组为空或不合法"}

        return {
            "items": items,
            "total_score": round(total, 2),
            "max_total": round(max_total, 2),
            "score_percent": round(total / max_total * 100, 2) if max_total else None,
            "weighted_total": round(weighted, 2) if weight_sum else None,
        }


class BidListRequirementsTool(BaseTool):
    """需求清单过滤/分组：按类别与最低置信度。"""

    async def execute(self, requirements=None, category=None, min_confidence=None, **kwargs) -> Dict[str, Any]:
        if not isinstance(requirements, list):
            return {"error": "requirements 必须为数组"}

        threshold = _to_number(min_confidence) if min_confidence is not None else None
        filtered: List[Dict[str, Any]] = []
        for req in requirements:
            if not isinstance(req, dict):
                continue
            if category and req.get("category") != category:
                continue
            conf = _to_number(req.get("confidence"))
            if threshold is not None and conf is not None and conf < threshold:
                continue
            filtered.append(req)

        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for cat in REQUIREMENT_CATEGORIES:
            grouped[cat] = [r for r in filtered if r.get("category") == cat]
        unclassified = [r for r in filtered if r.get("category") not in REQUIREMENT_CATEGORIES]

        return {
            "total": len(filtered),
            "grouped": grouped,
            "unclassified": unclassified,
        }


class BidRenderTemplateTool(BaseTool):
    """标书分节模板渲染：``{{var}}`` 替换为数据。READ_WRITE——产出草稿片段。"""

    _PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9_\.]+)\s*\}\}")

    async def execute(self, template=None, data=None, **kwargs) -> Dict[str, Any]:
        if not isinstance(template, str) or not template.strip():
            return {"error": "template 必须为非空字符串"}
        data = data if isinstance(data, dict) else {}

        missing: List[str] = []
        unknown: List[str] = []

        def repl(match: re.Match) -> str:
            key = match.group(1)
            if key not in data:
                missing.append(key)
                return f"{{{{{key}}}}}"
            value = data[key]
            if value is None:
                missing.append(key)
                return f"{{{{{key}}}}}"
            if not isinstance(value, (str, int, float)):
                unknown.append(key)
                return str(value)
            return str(value)

        rendered = self._PLACEHOLDER.sub(repl, template)
        return {
            "rendered": rendered,
            "missing_variables": sorted(set(missing)),
            "unknown_type_variables": sorted(set(unknown)),
        }


# ── 工具规格（注册到 ToolRegistry）────────────────────────────────────

BID_CALC_SCORING_SPEC = ToolSpec(
    name="bid_calc_scoring",
    description=(
        "计算招投标评分点得分：给定评分点（name/max_score/可选 weight）与实得分"
        "（name/score），输出逐项得分、总分、得分率与加权分。撰写/自检时校验评分数学。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "points": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "max_score": {"type": "number"},
                        "weight": {"type": "number"},
                    },
                    "required": ["name", "max_score"],
                },
            },
            "scores": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "score": {"type": "number"},
                    },
                    "required": ["name", "score"],
                },
            },
        },
        "required": ["points"],
    },
    output_schema={"type": "object"},
    risk_level=RiskLevel.READ_ONLY,
    timeout_seconds=5.0,
    required_permissions=[],
    agent_version="0.0",
)

BID_LIST_REQUIREMENTS_SPEC = ToolSpec(
    name="bid_list_requirements",
    description=(
        "按类别/置信度过滤投标需求清单。给定需求数组（category/requirement/"
        "confidence），返回按资质/业绩/技术/商务/格式/废标风险分组的清单。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "requirements": {
                "type": "array",
                "items": {"type": "object"},
            },
            "category": {"type": "string"},
            "min_confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["requirements"],
    },
    output_schema={"type": "object"},
    risk_level=RiskLevel.READ_ONLY,
    timeout_seconds=5.0,
    required_permissions=[],
    agent_version="0.0",
)

BID_RENDER_TEMPLATE_SPEC = ToolSpec(
    name="bid_render_template",
    description=(
        "渲染标书分节草稿：将模板中的 {{变量}} 替换为数据。产出草稿片段，"
        "属于写操作，须经人工审批放行。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "template": {"type": "string"},
            "data": {"type": "object"},
        },
        "required": ["template", "data"],
    },
    output_schema={"type": "object"},
    risk_level=RiskLevel.READ_WRITE,
    timeout_seconds=5.0,
    required_permissions=[Permissions.KB_WRITE],
    agent_version="0.0",
)

BID_TOOL_SPECS: List[ToolSpec] = [
    BID_CALC_SCORING_SPEC,
    BID_LIST_REQUIREMENTS_SPEC,
    BID_RENDER_TEMPLATE_SPEC,
]
