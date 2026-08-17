"""演示业务工具集（B3 配套）——20 个沙箱语义的业务操作工具。

与评测套件（evaluation/suite 的 tool 用例）一一对应：每个工具返回确定性的
演示响应，**无真实副作用**（沙箱语义），风险级 read_only 以支持无人值守
评测与前端直接执行。生产部署时可将 execute 替换为对真实业务系统的调用
（declarative HTTP），工具名与入参契约保持不变。
"""

from __future__ import annotations

import time
from typing import Any

from .base import BaseTool
from .spec import ToolSpec, RiskLevel


def _demo_id(prefix: str) -> str:
    return f"{prefix}-{time.time_ns() % 10**10:010d}"


class DemoBusinessTool(BaseTool):
    """沙箱业务工具：按工具名返回确定性演示响应。"""

    def __init__(self, name: str, summary: str, response_builder=None):
        self._name = name
        self._summary = summary
        self._response_builder = response_builder

    async def execute(self, **kwargs) -> dict[str, Any]:
        response: dict[str, Any] = {
            "status": "success",
            "sandbox": True,
            "message": f"{self._summary}（演示环境，无真实副作用）",
        }
        if self._response_builder:
            response.update(self._response_builder(kwargs))
        return response


def _ticket(prefix: str, kwargs: dict) -> dict:
    return {"ticket_id": _demo_id(prefix)}


def _order(prefix: str, kwargs: dict) -> dict:
    return {"order_id": kwargs.get("order_id") or _demo_id("SO")}


# 名称 → (中文摘要, 响应构造器)。与评测套件 tool 用例一一对应。
_DEMO_TOOLS: dict[str, tuple[str, Any]] = {
    "query_order_logistics": ("查询订单物流", lambda kw: {
        "order_id": kw.get("order_id") or _demo_id("SO"),
        "logistics_status": "运输中",
        "carrier": "顺丰速运",
        "eta": "预计 24 小时内送达",
    }),
    "subscribe_plan": ("开通订阅套餐", lambda kw: {
        "plan": kw.get("plan") or "专业版",
        "effective_at": "立即生效",
    } | _ticket("SUB")),
    "cancel_auto_renew": ("取消自动续费", lambda kw: {
        "auto_renew": False,
    } | _ticket("CAN")),
    "submit_expense": ("提交差旅报销", lambda kw: {
        "amount": kw.get("amount") or "按提交单据核定",
    } | _ticket("EXP")),
    "apply_annual_leave": ("申请年假", lambda kw: {
        "days": kw.get("days") or 1,
    } | _ticket("LA")),
    "apply_sick_leave": ("申请病假", lambda kw: {
        "days": kw.get("days") or 1,
    } | _ticket("SL")),
    "submit_warranty_claim": ("提交质保申请", lambda kw: {
        "warranty_type": "整机质保",
    } | _ticket("WTY")),
    "submit_refund": ("申请退货退款", lambda kw: {
        "refund_channel": "原路退回",
    } | _ticket("RFD")),
    "add_device": ("添加设备绑定", lambda kw: {
        "device": kw.get("device") or "S1 智能音箱",
    } | _ticket("DEV")),
    "create_incident": ("创建故障工单", lambda kw: _ticket("INC")),
    "export_finance_report": ("导出财务报表", lambda kw: {
        "report_url": "/demo/finance-report（演示下载链接）",
    } | _ticket("FIN")),
    "get_cloud_footage": ("获取云录像片段", lambda kw: {
        "footage_url": "/demo/cloud-footage（演示播放链接）",
        "retention_days": 30,
    }),
    "query_credits": ("查询积分余额", lambda kw: {
        "credits": 500,
        "expiring_soon": 0,
    }),
    "redeem_gift_card": ("核销礼品卡", lambda kw: {
        "gift_card": kw.get("gift_card") or "已核销",
    } | _ticket("GFT")),
    "request_access": ("申请数据访问权限", lambda kw: {
        "approval_required": True,
        "approver": "数据负责人",
    } | _ticket("ACC")),
    "run_database_backup": ("触发数据库备份", lambda kw: {
        "backup_type": "全量",
    } | _ticket("BAK")),
    "schedule_service": ("预约上门服务", lambda kw: {
        "service_window": kw.get("window") or "明日 9:00-12:00",
    } | _ticket("SVC")),
    "send_coupon": ("发放优惠券", lambda kw: {
        "coupon": kw.get("coupon") or "满 100 减 20",
    } | _ticket("CPN")),
    "switch_backup_link": ("切换备用链路", lambda kw: {
        "active_link": "备用链路 B",
    } | _ticket("SWT")),
    "upgrade_firmware": ("升级设备固件", lambda kw: {
        "firmware_version": kw.get("version") or "latest",
        "estimated_minutes": 10,
    } | _ticket("FWU")),
}

_INPUT_SCHEMA = {
    "type": "object",
    "properties": {},  # 沙箱工具参数宽松：模型可自由提取，缺省由演示响应兜底
    "required": [],
}


def demo_business_tool_specs() -> list[tuple[ToolSpec, BaseTool]]:
    """构造全部演示业务工具的 (spec, tool) 列表，供注册表批量注册。"""
    result: list[tuple[ToolSpec, BaseTool]] = []
    for name, (summary, _builder) in _DEMO_TOOLS.items():
        spec = ToolSpec(
            name=name,
            description=f"{summary}（演示业务工具，返回沙箱响应，无真实副作用）",
            input_schema=_INPUT_SCHEMA,
            output_schema={"type": "object"},
            risk_level=RiskLevel.READ_ONLY,
            timeout_seconds=10.0,
            agent_version="1.0",
        )
        result.append((spec, DemoBusinessTool(name, summary, _builder)))
    return result


# ── 工具路由（双条件：动作动词 + 领域词）────────────────────────
# 单靠领域词会把"云录像保留多久"这类 QA 查询误路由到工具（丢检索上下文）；
# 加上动作动词后仅命中真正的操作请求。
_TOOL_KEYWORDS: dict[str, list[str]] = {
    "query_order_logistics": ["物流"],
    "subscribe_plan": ["开通专业版", "开通订阅", "订阅套餐"],
    "cancel_auto_renew": ["取消自动续费", "取消续费"],
    "submit_expense": ["差旅报销", "提交报销"],
    "apply_annual_leave": ["年假"],
    "apply_sick_leave": ["病假"],
    "submit_warranty_claim": ["质保申请", "售后质保"],
    "submit_refund": ["退货退款", "申请退货"],
    "add_device": ["添加一台智能音箱", "添加设备", "添加智能音箱"],
    "get_cloud_footage": ["云录像"],
    "upgrade_firmware": ["固件"],
    "create_incident": ["故障工单"],
    "switch_backup_link": ["备用线路", "备用链路"],
    "run_database_backup": ["数据库全量备份", "数据库备份"],
    "request_access": ["申请访问", "访问权限", "申请权限"],
    "export_finance_report": ["销售对账单", "财务报表"],
    "send_coupon": ["发放一张优惠券", "发放优惠券"],
    "redeem_gift_card": ["兑换一张礼品卡", "兑换礼品卡", "礼品卡"],
    "query_credits": ["积分余额", "查询我的积分"],
    "schedule_service": ["上门服务", "预约一次售后", "预约售后"],
}

_ACTION_VERBS = ("帮我", "我要", "我想", "请帮我", "给我", "提交", "申请", "开通",
                 "取消", "升级", "执行", "发放", "兑换", "预约", "切换", "添加",
                 "查询", "查看", "办理", "发送", "创建", "跑")


def match_demo_tool(query: str) -> str | None:
    """业务操作路由：动作动词 + 领域词双条件命中 → 返回工具名（否则 None）。"""
    if not query:
        return None
    if not any(verb in query for verb in _ACTION_VERBS):
        return None
    for name, keywords in _TOOL_KEYWORDS.items():
        if any(kw in query for kw in keywords):
            return name
    return None
