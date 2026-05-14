from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from rac_core.models import DecisionType, PendingToolCall

from .models import DemoRunResult


class LLMPlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)


class LLMPlanFixture(BaseModel):
    """Normalized deterministic planner-style fixture (replay-only; no live model calls)."""

    model_config = ConfigDict(extra="ignore")

    scenario_name: str = Field(min_length=1)
    task: str = Field(min_length=1)
    planner: str = "replay"
    expected_decision: DecisionType | None = None
    expected_rule: str | None = None
    steps: list[LLMPlanStep] = Field(default_factory=list)

    @field_validator("expected_decision", mode="before")
    @classmethod
    def _coerce_expected_decision(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, DecisionType):
            return v
        if isinstance(v, str):
            return DecisionType(v)
        return v


class ReplayLLMPlanner:
    """Replays normalized planner-style tool plans from JSON fixtures; no live model calls."""

    def __init__(self, fixture_dir: str | Path) -> None:
        self.fixture_dir = Path(fixture_dir)

    def load_fixture(self, scenario_name: str) -> LLMPlanFixture:
        path = self.fixture_dir / f"{scenario_name}.json"
        if not path.is_file():
            raise ValueError(f"No LLM plan fixture for scenario: {scenario_name} ({path})")
        return LLMPlanFixture.model_validate_json(path.read_text(encoding="utf-8"))

    def plan(self, scenario_name: str) -> list[PendingToolCall]:
        fixture = self.load_fixture(scenario_name)
        return [
            PendingToolCall(tool_name=step.tool_name, arguments=dict(step.arguments))
            for step in fixture.steps
        ]

    def task_text(self, scenario_name: str) -> str:
        return self.load_fixture(scenario_name).task

    def expected_decision(self, scenario_name: str) -> DecisionType | None:
        return self.load_fixture(scenario_name).expected_decision

    def expected_rule(self, scenario_name: str) -> str | None:
        return self.load_fixture(scenario_name).expected_rule

    def list_scenarios(self) -> list[str]:
        if not self.fixture_dir.is_dir():
            return []
        return sorted(p.stem for p in self.fixture_dir.glob("*.json") if p.is_file())


def run_replay_llm_scenario(scenario_name: str, fixture_dir: str | Path) -> DemoRunResult:
    """Run one replayed planner-style plan through LocalRACController (same grants as Stage 7 demo)."""
    from rac_core.demo.reporting import make_demo_controller_for_scenario

    planner = ReplayLLMPlanner(fixture_dir)
    ctrl = make_demo_controller_for_scenario(scenario_name, planner=planner)
    return ctrl.run_scenario(scenario_name)
