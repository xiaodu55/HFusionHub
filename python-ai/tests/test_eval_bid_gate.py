"""标书撰写/自检工作流评测门禁单元测试（P1-4）。

锁定 ``app/core/bid/eval_gate.py`` 的密闭度量：撰写需求覆盖/分节路由/
引用忠实，自检废标点召回/合规草稿零误报。门槛默认 1.0（确定性规则）。
"""

from __future__ import annotations

from app.core.bid.eval_gate import (
    COMPLIANT_SECTIONS,
    GATE_THRESHOLDS,
    RISKY_SECTIONS,
    _run_check_scenario,
    _run_write_scenario,
    check_gates,
    run_all,
)


def test_write_scenario_all_metrics_full():
    metrics = _run_write_scenario()
    # 全部分节产出 + 需求被路由到预期分节 + 证据全部指向真实语料
    for key in (
        "requirement_coverage",
        "section_routing_accuracy",
        "section_completeness",
        "citation_faithfulness",
    ):
        assert metrics[key] == 1.0, f"{key} = {metrics[key]}"


def test_check_scenario_catches_all_planted_risks():
    metrics = _run_check_scenario()
    assert metrics["bond_recall"] == 1.0
    assert metrics["deadline_recall"] == 1.0
    assert metrics["disqualification_recall"] == 1.0
    assert metrics["substantive_recall"] == 1.0


def test_compliant_draft_has_no_false_positive_critical():
    assert _run_check_scenario()["false_positive_free"] == 1.0
    # 合规草稿确实覆盖了全部废标点（保证度量非空洞）
    compliant_text = "\n".join(s["content"] for s in COMPLIANT_SECTIONS)
    assert "保证金" in compliant_text and "截止" in compliant_text
    assert "密封" in compliant_text and "★" in compliant_text


def test_risky_draft_is_actually_risky():
    # 植入风险的草稿确实缺失各废标点（保证召回度量有意义）
    risky_text = "\n".join(s["content"] for s in RISKY_SECTIONS)
    for keyword in ("保证金", "截止", "密封", "★"):
        assert keyword not in risky_text, f"{keyword} 不应出现在风险草稿中"


def test_run_all_passes_full_thresholds():
    metrics = run_all()
    assert check_gates(metrics, GATE_THRESHOLDS) == []
    assert set(GATE_THRESHOLDS) <= set(metrics)


def test_check_gates_flags_regression():
    fails = check_gates({"bond_recall": 0.0}, GATE_THRESHOLDS)
    assert any("bond_recall" in f for f in fails)
