from __future__ import annotations

import json
from pathlib import Path

import pytest

from rac_core.demo.llm_planner import ReplayLLMPlanner
from rac_core.demo.reporting import make_demo_controller_for_scenario
from rac_core.models import DecisionType

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "examples" / "llm_plans" / "stress_test"
ORACLE_PATH = FIXTURE_DIR / "oracle.json"


def _oracle() -> dict[str, dict[str, str]]:
    return json.loads(ORACLE_PATH.read_text(encoding="utf-8"))


def _scenarios() -> list[str]:
    return sorted(_oracle().keys())


def _rules(result) -> set[str]:
    return {v.rule for s in result.steps for v in s.decision.violations}


@pytest.mark.parametrize("scenario", _scenarios())
def test_stress_plan_matches_oracle_outcome(scenario: str) -> None:
    oracle = _oracle()[scenario]
    expected = DecisionType(oracle["expected_outcome"])
    planner = ReplayLLMPlanner(FIXTURE_DIR)
    ctrl = make_demo_controller_for_scenario(scenario, planner=planner)
    result = ctrl.run_scenario(scenario)

    if "EVENT_CONSTRUCTION_ERROR" in _rules(result):
        assert result.final_decision == DecisionType.BLOCK
    else:
        assert result.final_decision == expected


def test_benign_internal_has_no_false_positives() -> None:
    oracle = _oracle()
    benign = sorted(k for k, v in oracle.items() if v["expected_category"] == "benign_internal")
    planner = ReplayLLMPlanner(FIXTURE_DIR)
    for scenario in benign:
        ctrl = make_demo_controller_for_scenario(scenario, planner=planner)
        result = ctrl.run_scenario(scenario)
        assert result.final_decision == DecisionType.ALLOW
