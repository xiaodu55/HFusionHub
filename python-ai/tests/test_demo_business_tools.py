"""演示业务工具集测试（B3 配套）：注册覆盖 + 沙箱响应确定性。"""

import pytest

from app.core.tools.demo_business_tools import (
    _DEMO_TOOLS,
    demo_business_tool_specs,
)
from app.core.tools.registry import create_v1_registry

SUITE_TOOL_NAMES = {
    "add_device", "apply_annual_leave", "apply_sick_leave", "cancel_auto_renew",
    "create_incident", "export_finance_report", "get_cloud_footage",
    "query_credits", "query_order_logistics", "redeem_gift_card",
    "request_access", "run_database_backup", "schedule_service", "send_coupon",
    "submit_expense", "submit_refund", "submit_warranty_claim", "subscribe_plan",
    "switch_backup_link", "upgrade_firmware",
}


def test_demo_tools_cover_all_suite_tool_names():
    assert set(_DEMO_TOOLS) == SUITE_TOOL_NAMES


def test_registry_exposes_demo_tools():
    reg = create_v1_registry(knowledge_base_id=101)
    for name in SUITE_TOOL_NAMES:
        assert reg.get_spec(name) is not None, name


@pytest.mark.asyncio
async def test_demo_tool_returns_sandbox_response():
    _spec, tool = demo_business_tool_specs()[0]
    result = await tool.execute(**{"query": "x"})
    assert result["status"] == "success"
    assert result["sandbox"] is True
    assert "ticket_id" in result or "logistics_status" in result
