from __future__ import annotations

from pathlib import Path

from rac_core.demo.llm_planner import ReplayLLMPlanner, run_replay_llm_scenario
from rac_core.demo.llm_reporting import (
    build_llm_plan_report_rows,
    generate_llm_plan_report_results,
)
FIXTURE_DIR = Path(__file__).resolve().parents[1] / "examples" / "llm_plans"


def test_build_llm_plan_report_rows() -> None:
    planner = ReplayLLMPlanner(FIXTURE_DIR)
    benign = run_replay_llm_scenario("benign_read_summarize", FIXTURE_DIR)
    from rac_core.demo.local_controller import LocalRACController
    from rac_core.demo.tools import LocalToolRuntime
    from rac_core.demo.reporting import _demo_files, _demo_session
    from rac_core.models import GrantConditions, GrantEnvelope, GrantSubject, ResourceScope

    grant = GrantEnvelope(
        grant_id="grant_demo",
        session_id="sess_demo",
        subject=GrantSubject(user_id="user_1", effective_subject="user_1"),
        allowed_actions={"read", "summarize"},
        allowed_tools={"read_file", "summarize_file", "create_email_draft"},
        resource_scope=ResourceScope(
            type="file",
            allowed_ids={"file_A", "external@example.com"},
        ),
        purpose_scope={"internal_summarization"},
        conditions=GrantConditions(
            environment="trusted_workspace",
            tenant="tenant_X",
            runtime_labels={"internal"},
        ),
    )
    ctrl = LocalRACController(
        grant_envelope=grant,
        session_context=_demo_session(),
        tool_runtime=LocalToolRuntime(_demo_files()),
        planner=planner,
    )
    action = ctrl.run_scenario("action_escalation_external_email")
    res = run_replay_llm_scenario("resource_expansion_file_b", FIXTURE_DIR)
    rows = build_llm_plan_report_rows([benign, action, res], planner=planner)
    assert len(rows) == 3
    assert rows[0].scenario == "Benign"
    assert rows[0].result == "✓"
    assert rows[1].rule == "ACT"
    assert rows[2].rule in ("ORG", "RES")


def test_llm_reporting_serialization() -> None:
    from rac_core.demo.reporting import to_csv, to_latex_tabular, to_markdown_table

    planner = ReplayLLMPlanner(FIXTURE_DIR)
    r = run_replay_llm_scenario("benign_read_summarize", FIXTURE_DIR)
    rows = build_llm_plan_report_rows([r], planner=planner)
    md = to_markdown_table(rows)
    assert md and "Scenario" in md and "Plan" in md
    csv_text = to_csv(rows)
    assert csv_text and "Scenario" in csv_text.splitlines()[0]
    tex = to_latex_tabular(rows)
    assert tex and "\\begin{tabular}" in tex


def test_generate_llm_plan_report_results_writes_files(tmp_path: Path) -> None:
    paths = generate_llm_plan_report_results(tmp_path, fixture_dir=FIXTURE_DIR)
    assert len(paths) == 3
    by_name = {p.name: p for p in paths}
    for name in ("llm_plan_results.md", "llm_plan_results.csv", "llm_plan_results.tex"):
        p = by_name[name]
        assert p.is_file() and p.read_text(encoding="utf-8").strip()
