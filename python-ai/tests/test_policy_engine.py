"""Policy engine tri-state governance tests."""


from app.core.policy import (
    MODE_READ_ONLY,
    MODE_READ_WRITE,
    PolicyAction,
    PolicyContext,
    PolicyEngine,
)
from app.core.tools.spec import RiskLevel


def _ctx(**overrides) -> PolicyContext:
    base = dict(
        user_id=1,
        knowledge_base_id=10,
        role="user",
        environment="development",
        mode=MODE_READ_ONLY,
        capability_profile=None,
        flags={},
        permissions=frozenset({"knowledge_base:read"}),
    )
    base.update(overrides)
    return PolicyContext(**base)


ENGINE = PolicyEngine()


def test_read_tool_allowed_in_read_only():
    v = ENGINE.evaluate(
        tool_name="search_knowledge_base",
        risk_level=RiskLevel.READ_ONLY,
        required_permissions=frozenset({"knowledge_base:read"}),
        ctx=_ctx(),
    )
    assert v.action == PolicyAction.ALLOW


def test_write_tool_needs_approval_in_read_only():
    v = ENGINE.evaluate(
        tool_name="write_note",
        risk_level=RiskLevel.READ_WRITE,
        required_permissions=frozenset({"knowledge_base:write"}),
        ctx=_ctx(),
    )
    assert v.action == PolicyAction.NEEDS_APPROVAL


def test_read_write_mode_allows_write_tool():
    v = ENGINE.evaluate(
        tool_name="write_note",
        risk_level=RiskLevel.READ_WRITE,
        required_permissions=frozenset({"knowledge_base:write"}),
        ctx=_ctx(mode=MODE_READ_WRITE),
    )
    assert v.action == PolicyAction.ALLOW


def test_admin_bypasses_approval_when_flag_enabled():
    v = ENGINE.evaluate(
        tool_name="write_note",
        risk_level=RiskLevel.READ_WRITE,
        required_permissions=frozenset({"knowledge_base:write"}),
        ctx=_ctx(role="admin", flags={"policy.admin_bypass_approval": True}),
    )
    assert v.action == PolicyAction.ALLOW
    assert v.rule == "role:admin:bypass"


def test_write_flag_off_denies_even_admin():
    v = ENGINE.evaluate(
        tool_name="write_note",
        risk_level=RiskLevel.READ_WRITE,
        required_permissions=frozenset({"knowledge_base:write"}),
        ctx=_ctx(role="admin", flags={"agent.write_tools.enabled": False}),
    )
    assert v.action == PolicyAction.DENY
    assert v.rule == "flag:agent.write_tools.enabled"


def test_approval_not_required_allow():
    v = ENGINE.evaluate(
        tool_name="write_note",
        risk_level=RiskLevel.READ_WRITE,
        required_permissions=frozenset({"knowledge_base:write"}),
        ctx=_ctx(flags={"approval.required_for_write": False}),
    )
    assert v.action == PolicyAction.ALLOW
    assert v.rule == "flag:approval.required_for_write"


def test_production_denies_external_tool():
    v = ENGINE.evaluate(
        tool_name="web_search",
        risk_level=RiskLevel.EXTERNAL,
        required_permissions=frozenset({"external:http"}),
        ctx=_ctx(environment="production", flags={"agent.web_search.enabled": True}),
    )
    assert v.action == PolicyAction.DENY
    assert v.rule == "env:production:external"


def test_web_search_flag_off_denies():
    v = ENGINE.evaluate(
        tool_name="web_search",
        risk_level=RiskLevel.EXTERNAL,
        required_permissions=frozenset({"external:http"}),
        ctx=_ctx(environment="development", flags={"agent.web_search.enabled": False}),
    )
    assert v.action == PolicyAction.DENY
    assert v.rule == "flag:agent.web_search.enabled"


def test_kb_scoping_does_not_change_deny_precedence():
    # A kb-scoped deny must not be bypassed by role upgrade.
    v = ENGINE.evaluate(
        tool_name="write_note",
        risk_level=RiskLevel.READ_WRITE,
        required_permissions=frozenset({"knowledge_base:write"}),
        ctx=_ctx(role="admin", flags={"policy.admin_bypass_approval": True}),
    )
    assert v.action == PolicyAction.ALLOW
