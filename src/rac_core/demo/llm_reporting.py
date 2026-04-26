from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from rac_core.models import DecisionType

from .llm_planner import ReplayLLMPlanner, run_replay_llm_scenario
from .models import DemoRunResult
from .reporting import (
    DEFAULT_SCENARIO_LABELS,
    abbreviate_demo_rule,
    to_csv,
    to_latex_tabular,
    to_markdown_table,
)


def _format_decision(d: DecisionType) -> str:
    if d == DecisionType.ALLOW:
        return "ALLOW"
    if d == DecisionType.BLOCK:
        return "BLOCK"
    if d == DecisionType.ALLOW_WITH_ALERT:
        return "ALERT"
    return str(d.value)


def _short_task(text: str, max_len: int = 56) -> str:
    s = text.strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 3].rstrip() + "..."


def _first_rule_from_last_step(result: DemoRunResult) -> str | None:
    if not result.steps:
        return None
    last = result.steps[-1]
    if last.decision.violations:
        return last.decision.violations[0].rule
    return None


class LLMPlanReportRow(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    scenario: str = Field(alias="Scenario")
    task: str = Field(alias="Task")
    plan: str = Field(alias="Plan")
    expected: str = Field(alias="Expected")
    observed: str = Field(alias="Observed")
    rule: str = Field(alias="Rule")
    result: str = Field(alias="Result")


def build_llm_plan_report_rows(
    results: list[DemoRunResult],
    planner: ReplayLLMPlanner,
    scenario_labels: dict[str, tuple[str, str]] | None = None,
) -> list[LLMPlanReportRow]:
    if not isinstance(planner, ReplayLLMPlanner):
        raise TypeError("planner must be ReplayLLMPlanner")

    labels = scenario_labels or DEFAULT_SCENARIO_LABELS
    rows: list[LLMPlanReportRow] = []
    for result in results:
        short, plan_compact = labels.get(
            result.scenario_name, (result.scenario_name, "—")
        )
        task_cell = _short_task(planner.task_text(result.scenario_name))
        exp_dec = planner.expected_decision(result.scenario_name)
        exp_s = _format_decision(exp_dec) if exp_dec is not None else "—"
        obs_s = _format_decision(result.final_decision)
        rule_cell = abbreviate_demo_rule(_first_rule_from_last_step(result))
        ok = "✓" if exp_dec is not None and result.final_decision == exp_dec else "✗"
        rows.append(
            LLMPlanReportRow(
                scenario=short,
                task=task_cell,
                plan=plan_compact,
                expected=exp_s,
                observed=obs_s,
                rule=rule_cell,
                result=ok,
            )
        )
    return rows


def _default_fixture_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "examples" / "llm_plans"


def generate_llm_plan_report_results(
    output_dir: Path | str,
    *,
    fixture_dir: str | Path | None = None,
    caption: str | None = "Replayed LLM tool plans with RAC (Stage 8A).",
    label: str | None = "tab:llm_plan_results",
) -> list[Path]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fd = Path(fixture_dir) if fixture_dir is not None else _default_fixture_dir()
    planner = ReplayLLMPlanner(fd)
    names = [k for k in DEFAULT_SCENARIO_LABELS if k in planner.list_scenarios()]
    results = [run_replay_llm_scenario(n, fd) for n in names]

    rows = build_llm_plan_report_rows(results, planner=planner)
    paths: list[Path] = []
    md_path = out_dir / "llm_plan_results.md"
    csv_path = out_dir / "llm_plan_results.csv"
    tex_path = out_dir / "llm_plan_results.tex"
    md_path.write_text(to_markdown_table(rows) + "\n", encoding="utf-8")
    csv_path.write_text(to_csv(rows), encoding="utf-8")
    tex_path.write_text(
        to_latex_tabular(rows, caption=caption, label=label) + "\n",
        encoding="utf-8",
    )
    paths.extend([md_path, csv_path, tex_path])
    return paths
