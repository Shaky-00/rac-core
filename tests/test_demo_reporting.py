from __future__ import annotations

from pathlib import Path

from rac_core.demo.reporting import (
    DemoReportRow,
    abbreviate_demo_rule,
    build_demo_report_rows,
    default_demo_expected,
    generate_demo_controller_results,
    make_demo_controller_for_scenario,
    run_default_demo_scenarios,
    to_csv,
    to_latex_tabular,
    to_markdown_table,
)
from rac_core.models import DecisionType


def test_abbreviate_demo_rule() -> None:
    assert abbreviate_demo_rule("ACTION_ESCALATION") == "ACT"
    assert abbreviate_demo_rule("EVENT_CONSTRUCTION_ERROR") == "ECE"
    assert abbreviate_demo_rule(None) == "—"
    assert abbreviate_demo_rule("UNKNOWN_RULE_XYZ") == "UNKNOWN_RULE_XYZ"


def test_build_demo_report_rows_benign() -> None:
    ctrl = make_demo_controller_for_scenario("benign_read_summarize")
    result = ctrl.run_scenario("benign_read_summarize")
    rows = build_demo_report_rows(
        [result],
        expected={"benign_read_summarize": DecisionType.ALLOW},
    )
    assert len(rows) == 1
    r = rows[0]
    assert r.scenario == "Benign"
    assert r.observed == "ALLOW"
    assert r.expected == "ALLOW"
    assert r.result == "✓"
    assert r.rule == "—"
    assert r.blocked_at == "—"


def test_build_demo_report_rows_action_escalation() -> None:
    ctrl = make_demo_controller_for_scenario("action_escalation_external_email")
    result = ctrl.run_scenario("action_escalation_external_email")
    rows = build_demo_report_rows(
        [result],
        expected={"action_escalation_external_email": DecisionType.BLOCK},
    )
    assert len(rows) == 1
    r = rows[0]
    assert r.observed == "BLOCK"
    assert r.expected == "BLOCK"
    assert r.result == "✓"
    assert r.rule == "ACT"
    assert r.side_effect in ("no external commit", "staged only")
    assert r.blocked_at == "step_1"


def test_build_demo_report_rows_purpose_drift() -> None:
    ctrl = make_demo_controller_for_scenario("purpose_drift")
    result = ctrl.run_scenario("purpose_drift")
    rows = build_demo_report_rows(
        [result],
        expected={"purpose_drift": DecisionType.BLOCK},
    )
    assert len(rows) == 1
    r = rows[0]
    assert r.rule in ("ECE", "PUR")
    assert r.result == "✓"


def test_serialization_markdown_csv_latex() -> None:
    ctrl = make_demo_controller_for_scenario("benign_read_summarize")
    benign = ctrl.run_scenario("benign_read_summarize")
    ctrl2 = make_demo_controller_for_scenario("purpose_drift")
    drift = ctrl2.run_scenario("purpose_drift")
    rows = build_demo_report_rows(
        [benign, drift],
        expected={
            "benign_read_summarize": DecisionType.ALLOW,
            "purpose_drift": DecisionType.BLOCK,
        },
    )
    md = to_markdown_table(rows)
    assert md
    assert "Scenario" in md
    assert "Tool chain" in md
    csv_text = to_csv(rows)
    assert csv_text
    lines = csv_text.strip().splitlines()
    assert "Scenario" in lines[0]
    tex = to_latex_tabular(rows)
    assert tex
    assert "\\begin{tabular}" in tex


def test_generate_demo_controller_results_writes_files(tmp_path: Path) -> None:
    paths = generate_demo_controller_results(tmp_path)
    assert len(paths) == 3
    by_name = {p.name: p for p in paths}
    for name in (
        "demo_controller_results.md",
        "demo_controller_results.csv",
        "demo_controller_results.tex",
    ):
        p = by_name[name]
        assert p.is_file()
        assert p.read_text(encoding="utf-8").strip()


def test_run_default_demo_scenarios_matches_expected() -> None:
    results = run_default_demo_scenarios()
    exp = default_demo_expected()
    rows = build_demo_report_rows(results, expected=exp)
    assert all(r.result == "✓" for r in rows)
    assert len(rows) == 5


def test_demo_report_row_roundtrip_dict() -> None:
    row = DemoReportRow(
        scenario="S",
        tool_chain="a → b",
        expected="ALLOW",
        observed="BLOCK",
        blocked_at="step_1",
        rule="ACT",
        side_effect="none",
        result="✗",
    )
    d = row.model_dump(by_alias=True)
    assert d["Scenario"] == "S"
    assert d["Tool chain"] == "a → b"
