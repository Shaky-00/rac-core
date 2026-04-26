from __future__ import annotations

from rac_core.demo import (
    DemoRunResult,
    LocalRACController,
    LocalToolRuntime,
    ScriptedPlanner,
)
from rac_core.models import (
    DecisionType,
    GrantConditions,
    GrantEnvelope,
    GrantSubject,
    ResourceScope,
    SessionContext,
)


def _demo_grant(*, purpose_scope: set[str] | None = None) -> GrantEnvelope:
    return GrantEnvelope(
        grant_id="grant_demo",
        session_id="sess_demo",
        subject=GrantSubject(user_id="user_1", effective_subject="user_1"),
        allowed_actions={"read", "summarize"},
        allowed_tools={"read_file", "summarize_file", "create_email_draft"},
        resource_scope=ResourceScope(type="file", allowed_ids={"file_A"}),
        purpose_scope=purpose_scope or {"internal_summarization"},
        conditions=GrantConditions(
            environment="trusted_workspace",
            tenant="tenant_X",
            runtime_labels={"internal"},
        ),
    )


def _demo_session() -> SessionContext:
    return SessionContext(
        session_id="sess_demo",
        user_id="user_1",
        agent_id="agent_demo",
        tenant="tenant_X",
        roles={"analyst"},
        effective_subject="user_1",
    )


def _demo_files() -> dict[str, str]:
    return {"file_A": "alpha content for internal report", "file_B": "secret other file"}


def _make_controller(
    *,
    grant: GrantEnvelope | None = None,
    files: dict[str, str] | None = None,
) -> LocalRACController:
    return LocalRACController(
        grant_envelope=grant or _demo_grant(),
        session_context=_demo_session(),
        tool_runtime=LocalToolRuntime(files or _demo_files()),
        planner=ScriptedPlanner(),
    )


def _rules(result: DemoRunResult) -> list[str]:
    rules: list[str] = []
    for step in result.steps:
        for v in step.decision.violations:
            rules.append(v.rule)
    return rules


def test_benign_read_summarize_allows() -> None:
    ctrl = _make_controller()
    result = ctrl.run_scenario("benign_read_summarize")
    assert result.final_decision == DecisionType.ALLOW
    assert len(result.steps) == 2
    assert all(s.decision.decision == DecisionType.ALLOW for s in result.steps)
    assert ctrl.lineage_store.next_step_seq("sess_demo") == 2
    assert all(
        s.metadata.get("output_anchor_verified_by_controller") is True for s in result.steps
    )


def test_action_escalation_external_email_blocked() -> None:
    # Recipient must appear in grant scope so RAC reaches action lattice (ACTION_ESCALATION)
    # rather than failing earlier on RESOURCE_ORIGIN_UNVERIFIABLE.
    grant = _demo_grant().model_copy(
        update={
            "resource_scope": ResourceScope(
                type="file",
                allowed_ids={"file_A", "external@example.com"},
            )
        }
    )
    ctrl = _make_controller(grant=grant)
    result = ctrl.run_scenario("action_escalation_external_email")
    assert result.final_decision == DecisionType.BLOCK
    assert result.blocked_at_step == "step_1"
    assert "ACTION_ESCALATION" in _rules(result)
    step1 = result.steps[1]
    assert step1.metadata.get("blocked_before_external_commit") is True
    assert step1.metadata.get("draft_staged_only") is True


def test_resource_expansion_file_b_blocked() -> None:
    ctrl = _make_controller()
    result = ctrl.run_scenario("resource_expansion_file_b")
    assert result.final_decision == DecisionType.BLOCK
    rs = set(_rules(result))
    assert "RESOURCE_ORIGIN_UNVERIFIABLE" in rs or "RESOURCE_EXPANSION" in rs
    blocked = result.steps[1]
    assert blocked.step_name == "step_1"
    assert blocked.metadata.get("malicious_resource_override") == ["file_B"]
    assert (
        blocked.metadata.get("attack_injection_level")
        == "event_and_tool_observed_resource"
    )
    assert blocked.metadata.get("output_anchor_verified_by_controller") is True
    tool_meta = blocked.metadata.get("tool_metadata")
    assert isinstance(tool_meta, dict)
    assert tool_meta.get("source_resource_ids") == ["file_B"]


def test_forged_predecessor_blocked() -> None:
    ctrl = _make_controller()
    result = ctrl.run_scenario("forged_predecessor")
    assert result.final_decision == DecisionType.BLOCK
    rs = set(_rules(result))
    assert "LINEAGE_INVALID" in rs or "EVENT_CONSTRUCTION_ERROR" in rs


def test_event_construction_value_error_maps_to_block() -> None:
    ctrl = _make_controller()

    def _boom(*_a, **_kw):
        raise ValueError("Unknown resource: out:fake")

    ctrl.event_adapter.construct_event = _boom  # type: ignore[method-assign]
    result = ctrl.run_scenario("benign_read_summarize")
    assert result.final_decision == DecisionType.BLOCK
    assert "EVENT_CONSTRUCTION_ERROR" in _rules(result)


def test_purpose_drift_blocked() -> None:
    ctrl = _make_controller()
    result = ctrl.run_scenario("purpose_drift")
    assert result.final_decision == DecisionType.BLOCK
    rs = set(_rules(result))
    assert "EVENT_CONSTRUCTION_ERROR" in rs or "PURPOSE_DRIFT" in rs


def test_controller_uses_event_adapter_and_checker() -> None:
    ctrl = _make_controller()
    result = ctrl.run_scenario("benign_read_summarize")
    assert result.final_decision == DecisionType.ALLOW
    for step in result.steps:
        comps = step.metadata.get("rac_components")
        assert isinstance(comps, list)
        assert "event_adapter" in comps
        assert "rac_precommit_checker" in comps
        assert "output_anchor_verifier" in comps
    assert ctrl.basis_store.load_finalized_basis("sess_demo", "step_1") is not None
    read_rec = ctrl.lineage_store.get_step("step_0", "sess_demo")
    summ_rec = ctrl.lineage_store.get_step("step_1", "sess_demo")
    assert read_rec is not None and summ_rec is not None
    assert read_rec.output_anchor is not None
    assert read_rec.output_anchor.verified_by_controller is True
    assert summ_rec.output_anchor is not None
    assert summ_rec.output_anchor.verified_by_controller is True
