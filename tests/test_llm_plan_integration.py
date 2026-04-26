from __future__ import annotations

from pathlib import Path

from rac_core.demo.llm_planner import ReplayLLMPlanner, run_replay_llm_scenario
from rac_core.demo.reporting import make_demo_controller_for_scenario
from rac_core.models import DecisionType, GrantConditions, GrantEnvelope, GrantSubject, ResourceScope

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "examples" / "llm_plans"


def _rules_for_result(result) -> list[str]:
    rules: list[str] = []
    for step in result.steps:
        for v in step.decision.violations:
            rules.append(v.rule)
    return rules


def test_benign_replayed_llm_plan_allows() -> None:
    planner = ReplayLLMPlanner(FIXTURE_DIR)
    ctrl = make_demo_controller_for_scenario("benign_read_summarize", planner=planner)
    result = ctrl.run_scenario("benign_read_summarize")
    assert result.final_decision == DecisionType.ALLOW
    assert planner.expected_decision("benign_read_summarize") == DecisionType.ALLOW
    assert len(result.steps) == 2
    assert all(s.decision.decision == DecisionType.ALLOW for s in result.steps)


def test_action_escalation_replayed_llm_plan_blocked() -> None:
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
    planner = ReplayLLMPlanner(FIXTURE_DIR)
    from rac_core.demo.local_controller import LocalRACController
    from rac_core.demo.tools import LocalToolRuntime
    from rac_core.demo.reporting import _demo_files, _demo_session

    ctrl = LocalRACController(
        grant_envelope=grant,
        session_context=_demo_session(),
        tool_runtime=LocalToolRuntime(_demo_files()),
        planner=planner,
    )
    result = ctrl.run_scenario("action_escalation_external_email")
    assert planner.expected_decision("action_escalation_external_email") == DecisionType.BLOCK
    assert result.final_decision == DecisionType.BLOCK
    assert "ACTION_ESCALATION" in _rules_for_result(result)
    email_step = next(
        s
        for s in result.steps
        if s.pending_tool_call.tool_name == "create_email_draft"
    )
    assert email_step.metadata.get("blocked_before_external_commit") is True
    assert email_step.metadata.get("draft_staged_only") is True


def test_resource_expansion_replayed_llm_plan_blocked() -> None:
    result = run_replay_llm_scenario("resource_expansion_file_b", FIXTURE_DIR)
    assert result.final_decision == DecisionType.BLOCK
    rs = set(_rules_for_result(result))
    assert "RESOURCE_ORIGIN_UNVERIFIABLE" in rs or "RESOURCE_EXPANSION" in rs
    blocked = result.steps[-1]
    mo = blocked.metadata.get("malicious_resource_override")
    if mo is not None:
        assert "file_B" in mo


def test_forged_predecessor_replayed_llm_plan_blocked() -> None:
    result = run_replay_llm_scenario("forged_predecessor", FIXTURE_DIR)
    assert result.final_decision == DecisionType.BLOCK
    rs = set(_rules_for_result(result))
    assert "EVENT_CONSTRUCTION_ERROR" in rs or "LINEAGE_INVALID" in rs


def test_purpose_drift_replayed_llm_plan_blocked() -> None:
    result = run_replay_llm_scenario("purpose_drift", FIXTURE_DIR)
    assert result.final_decision == DecisionType.BLOCK
    rs = set(_rules_for_result(result))
    assert "EVENT_CONSTRUCTION_ERROR" in rs or "PURPOSE_DRIFT" in rs
