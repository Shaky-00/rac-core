"""Audit helpers for controlled-trace grant / required_actions inference (v0.6 validation)."""

from __future__ import annotations

from datetime import datetime

from rac_core.demo.local_controller import demo_initial_basis_from_grant
from rac_core.models import (
    DecisionType,
    GrantConditions,
    GrantEnvelope,
    GrantSubject,
    ResourceScope,
    TypedAuthorizationEvent,
    TypedEventConditions,
    TypedEventDelegation,
    TypedEventResourceScope,
    TypedEventSubject,
)
from rac_core.validation.trace import (
    ControlledTrace,
    TraceStep,
    build_trace_inference_report,
    describe_trace_grant_inference,
    initial_basis_from_grant_templates,
    infer_grant_templates_for_trace,
)


def _minimal_grant(*, session_id: str = "sess_audit") -> GrantEnvelope:
    return GrantEnvelope(
        grant_id="g1",
        session_id=session_id,
        subject=GrantSubject(user_id="u1", effective_subject="u1"),
        allowed_actions={"read", "summarize"},
        resource_scope=ResourceScope(type="file", allowed_ids={"file_A"}),
        purpose_scope={"internal_summarization"},
        conditions=GrantConditions(
            environment="trusted_workspace",
            tenant="tenant_X",
            runtime_labels={"internal"},
        ),
    )


def _read_event(*, eid: str, step_id: str, step_seq: int) -> TypedAuthorizationEvent:
    return TypedAuthorizationEvent(
        event_id=eid,
        session_id="sess_audit",
        step_id=step_id,
        step_seq=step_seq,
        subject=TypedEventSubject(user_id="u1", effective_subject="u1"),
        tool_name="read_file",
        action="read",
        resource_scope=TypedEventResourceScope(type="file", ids={"file_A"}),
        purpose="internal_summarization",
        conditions=TypedEventConditions(
            time=datetime(2026, 4, 26, 12, 0, 0),
            environment="trusted_workspace",
            tenant="tenant_X",
            runtime_labels={"internal"},
        ),
        delegation=TypedEventDelegation(),
    )


def test_explicit_grant_templates_take_precedence() -> None:
    g = _minimal_grant()
    t = ControlledTrace(
        name="t_explicit",
        grant_templates=["internal_analysis"],
        steps=[
            TraceStep(
                name="s0",
                event=_read_event(eid="e0", step_id="s0", step_seq=0),
                grant=g,
                expected_decision=DecisionType.ALLOW,
            )
        ],
    )
    assert infer_grant_templates_for_trace(t) == ["internal_analysis"]
    row = describe_trace_grant_inference(t)
    assert row["explicit_grant_templates"] == ["internal_analysis"]
    assert row["whether_grant_templates_inferred"] is False
    assert row["final_grant_templates"] == ["internal_analysis"]


def test_heuristic_infers_when_no_explicit_templates() -> None:
    g = _minimal_grant()
    t = ControlledTrace(
        name="t_heuristic",
        steps=[
            TraceStep(
                name="s0",
                event=_read_event(eid="e0", step_id="s0", step_seq=0),
                grant=g,
                expected_decision=DecisionType.ALLOW,
            )
        ],
    )
    assert infer_grant_templates_for_trace(t) == ["internal_analysis"]
    row = describe_trace_grant_inference(t)
    assert row["explicit_grant_templates"] is None
    assert row["whether_grant_templates_inferred"] is True
    assert row["final_grant_templates"] == ["internal_analysis"]


def test_audit_marks_whether_inferred() -> None:
    g = _minimal_grant()
    explicit = ControlledTrace(
        name="e",
        grant_templates=["internal_analysis"],
        steps=[
            TraceStep(
                name="s0",
                event=_read_event(eid="a", step_id="s0", step_seq=0),
                grant=g,
                expected_decision=DecisionType.ALLOW,
            )
        ],
    )
    inferred = ControlledTrace(
        name="i",
        steps=[
            TraceStep(
                name="s0",
                event=_read_event(eid="b", step_id="s0", step_seq=0),
                grant=g,
                expected_decision=DecisionType.ALLOW,
            )
        ],
    )
    rep = build_trace_inference_report([explicit, inferred])
    assert rep["count"] == 2
    assert rep["count_grant_templates_inferred"] == 1
    by_name = {r["trace_name"]: r for r in rep["traces"]}
    assert by_name["e"]["whether_grant_templates_inferred"] is False
    assert by_name["i"]["whether_grant_templates_inferred"] is True


def test_report_counts_required_actions_sources() -> None:
    g = _minimal_grant()
    ev_with = _read_event(eid="e1", step_id="s0", step_seq=0).model_copy(
        update={"required_actions": ["acquire.read_object"]}
    )
    t = ControlledTrace(
        name="ra_mix",
        grant_templates=["internal_analysis"],
        steps=[
            TraceStep(
                name="s0",
                event=ev_with,
                grant=g,
                expected_decision=DecisionType.ALLOW,
            ),
            TraceStep(
                name="s1",
                event=_read_event(eid="e2", step_id="s1", step_seq=1),
                grant=g,
                expected_decision=DecisionType.ALLOW,
                required_actions=["acquire.read_object"],
            ),
        ],
    )
    row = describe_trace_grant_inference(t)
    assert row["number_of_steps"] == 2
    assert row["number_of_steps_with_required_actions"] == 2
    assert row["number_of_steps_using_event_required_actions_only"] == 1
    assert row["number_of_steps_using_explicit_required_actions_on_trace_step"] == 1
    assert row["number_of_steps_using_inferred_required_actions"] == 0


def test_controlled_trace_legacy_rac_trace_field_defaults_false() -> None:
    g = _minimal_grant()
    t = ControlledTrace(
        name="leg",
        steps=[
            TraceStep(
                name="s0",
                event=_read_event(eid="x", step_id="s0", step_seq=0),
                grant=g,
                expected_decision=DecisionType.ALLOW,
            )
        ],
    )
    assert describe_trace_grant_inference(t)["legacy_rac_trace"] is False


def test_demo_initial_basis_matches_validation_semantics() -> None:
    g = _minimal_grant(session_id="sess_cmp")
    demo_b = demo_initial_basis_from_grant(g)
    val_b = initial_basis_from_grant_templates(
        g,
        ["internal_analysis_full"],
        basis_id=f"basis:demo_initial:{g.session_id}",
    )
    assert sorted(demo_b.allowed_action_labels) == sorted(val_b.allowed_action_labels)
    assert demo_b.purpose_scope == val_b.purpose_scope
    assert demo_b.source_templates == val_b.source_templates
    assert demo_b.compiled_grant_conditions == val_b.compiled_grant_conditions
    assert demo_b.compiled_grant_delegation == val_b.compiled_grant_delegation
    assert demo_b.delegation.allow_delegation == val_b.delegation.allow_delegation
    assert demo_b.delegation.allowed_delegatees == val_b.delegation.allowed_delegatees
    assert demo_b.conditions.environment == val_b.conditions.environment
    assert demo_b.conditions.tenant == val_b.conditions.tenant
