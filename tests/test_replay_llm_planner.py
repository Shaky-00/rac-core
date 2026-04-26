from __future__ import annotations

import json
from pathlib import Path

from rac_core.demo.llm_planner import LLMPlanFixture, ReplayLLMPlanner
from rac_core.models import DecisionType

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "examples" / "llm_plans"


def test_load_fixture_success() -> None:
    planner = ReplayLLMPlanner(FIXTURE_DIR)
    fx = planner.load_fixture("benign_read_summarize")
    assert isinstance(fx, LLMPlanFixture)
    assert fx.task.strip()
    assert len(fx.steps) == 2


def test_plan_returns_pending_tool_calls() -> None:
    planner = ReplayLLMPlanner(FIXTURE_DIR)
    calls = planner.plan("benign_read_summarize")
    assert len(calls) == 2
    assert calls[0].tool_name == "read_file"
    assert calls[1].tool_name == "summarize_file"


def test_fixture_does_not_expose_security_fields() -> None:
    path = FIXTURE_DIR / "benign_read_summarize.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    forbidden = {
        "action",
        "purpose_scope",
        "verified_anchor",
        "basis",
        "decision",
        "resource_origin",
    }
    for key in forbidden:
        assert key not in data
    for step in data["steps"]:
        assert set(step.keys()) <= {"tool_name", "arguments"}
        for ak in step.get("arguments", {}):
            assert ak not in forbidden


def test_expected_decision_and_rule() -> None:
    planner = ReplayLLMPlanner(FIXTURE_DIR)
    assert planner.expected_decision("action_escalation_external_email") == DecisionType.BLOCK
    assert planner.expected_rule("action_escalation_external_email") == "ACTION_ESCALATION"


def test_list_scenarios_includes_known() -> None:
    planner = ReplayLLMPlanner(FIXTURE_DIR)
    names = planner.list_scenarios()
    assert "benign_read_summarize" in names
    assert names == sorted(names)
