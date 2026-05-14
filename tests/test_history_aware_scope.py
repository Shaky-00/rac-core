"""Unit tests for HISTORY_AWARE_SCOPE TraceBench baseline (validation-only)."""

from __future__ import annotations

from datetime import datetime

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
    VerifiedStructuredOutputAnchor,
)
from rac_core.validation import AblationMode, AblationRunner, ControlledTrace, TraceStep
from rac_core.validation.history_aware_scope import (
    HistoryAwareState,
    grant_bound_resource_ids_for_trace,
    history_aware_scope_step,
    static_history_aware_step,
)
from rac_core.validation.rac_tracebench_experiment import default_variant_plan


def _grant(*, allowed_ids: set[str]) -> GrantEnvelope:
    return GrantEnvelope(
        grant_id="g1",
        session_id="sess_1",
        subject=GrantSubject(user_id="u1", effective_subject="u1"),
        allowed_actions={"read", "summarize"},
        allowed_tools={"read_file", "summarize_file"},
        resource_scope=ResourceScope(type="file", allowed_ids=allowed_ids),
        purpose_scope={"internal_summarization"},
        delegation={"allow_delegation": False},
        conditions=GrantConditions(
            environment="trusted_workspace",
            tenant="t1",
            runtime_labels={"internal"},
        ),
    )


def _event(*, eid: str, sid: str, resource_ids: set[str], step_id: str = "s1", step_seq: int = 0) -> TypedAuthorizationEvent:
    return TypedAuthorizationEvent(
        event_id=eid,
        session_id=sid,
        step_id=step_id,
        step_seq=step_seq,
        subject=TypedEventSubject(user_id="u1", effective_subject="u1"),
        tool_name="read_file",
        action="read",
        resource_scope=TypedEventResourceScope(type="file", ids=resource_ids),
        purpose="internal_summarization",
        conditions=TypedEventConditions(
            time=datetime(2026, 4, 26, 12, 0, 0),
            environment="trusted_workspace",
            tenant="t1",
            runtime_labels={"internal"},
        ),
        delegation=TypedEventDelegation(),
        input_anchors=[],
        advisory_predecessor_hints=[],
    )


def _event_tool(
    *,
    eid: str,
    sid: str,
    resource_ids: set[str],
    tool_name: str,
    action: str,
    step_id: str = "s1",
    step_seq: int = 0,
) -> TypedAuthorizationEvent:
    return TypedAuthorizationEvent(
        event_id=eid,
        session_id=sid,
        step_id=step_id,
        step_seq=step_seq,
        subject=TypedEventSubject(user_id="u1", effective_subject="u1"),
        tool_name=tool_name,
        action=action,
        resource_scope=TypedEventResourceScope(type="file", ids=resource_ids),
        purpose="internal_summarization",
        conditions=TypedEventConditions(
            time=datetime(2026, 4, 26, 12, 0, 0),
            environment="trusted_workspace",
            tenant="t1",
            runtime_labels={"internal"},
        ),
        delegation=TypedEventDelegation(),
        input_anchors=[],
        advisory_predecessor_hints=[],
    )


def _runner() -> AblationRunner:
    from rac_core.action_semantics.registry import ActionSemanticsRegistry
    from rac_core.action_semantics.taxonomy import default_semantics_yaml_path
    from rac_core.checker import RACPreCommitChecker
    from rac_core.store import InMemoryBasisStore, InMemoryCausalLineageStore

    def factory() -> RACPreCommitChecker:
        return RACPreCommitChecker(
            lineage_store=InMemoryCausalLineageStore(),
            basis_store=InMemoryBasisStore(),
            action_semantics_registry=ActionSemanticsRegistry.load_from_yaml(default_semantics_yaml_path()),
        )

    return AblationRunner(checker_factory=factory)


def test_history_aware_grant_scope_allows_in_scope_resource() -> None:
    g = _grant(allowed_ids={"file_A"})
    st = TraceStep(
        name="s1",
        event=_event(eid="e1", sid="sess_1", resource_ids={"file_A"}),
        grant=g,
        expected_decision=DecisionType.ALLOW,
    )
    trace = ControlledTrace(name="t1", steps=[st])
    state = HistoryAwareState(grant_resource_ids=grant_bound_resource_ids_for_trace(trace))
    d = history_aware_scope_step(st, state)
    assert d.decision == DecisionType.ALLOW
    assert "file_A" in state.accepted_resource_ids


def test_history_aware_accepts_resource_introduced_by_prior_anchor() -> None:
    g = _grant(allowed_ids={"file_A"})
    anchor = VerifiedStructuredOutputAnchor(
        anchor_id="anc1",
        producer_event_id="e1",
        content_hash="hash:1",
        resource_ids={"file_B"},
        verified_by_controller=True,
        session_id="sess_1",
    )
    step1 = TraceStep(
        name="s1",
        event=_event(eid="e1", sid="sess_1", resource_ids={"file_A"}, step_id="s1", step_seq=0),
        grant=g,
        output_anchor=anchor,
        expected_decision=DecisionType.ALLOW,
    )
    step2 = TraceStep(
        name="s2",
        event=_event(eid="e2", sid="sess_1", resource_ids={"file_B"}, step_id="s2", step_seq=1),
        grant=g,
        expected_decision=DecisionType.ALLOW,
    )
    trace = ControlledTrace(name="t1", steps=[step1, step2])
    state = HistoryAwareState(grant_resource_ids=grant_bound_resource_ids_for_trace(trace))
    assert history_aware_scope_step(step1, state).decision == DecisionType.ALLOW
    assert "file_B" in state.accepted_resource_ids
    assert history_aware_scope_step(step2, state).decision == DecisionType.ALLOW


def test_history_aware_blocks_resource_not_in_grant_or_history() -> None:
    g = _grant(allowed_ids={"file_A"})
    st = TraceStep(
        name="s1",
        event=_event(eid="e1", sid="sess_1", resource_ids={"file_ZZZ"}),
        grant=g,
        expected_decision=DecisionType.BLOCK,
    )
    trace = ControlledTrace(name="t1", steps=[st])
    state = HistoryAwareState(grant_resource_ids=grant_bound_resource_ids_for_trace(trace))
    d = history_aware_scope_step(st, state)
    assert d.decision == DecisionType.BLOCK
    assert any(v.rule == "HISTORY_AWARE_SCOPE_DENY" for v in d.violations)


def test_ablation_runner_history_aware_matches_unit_semantics() -> None:
    g = _grant(allowed_ids={"file_A"})
    step1 = TraceStep(
        name="s1",
        event=_event(eid="e1", sid="sess_1", resource_ids={"file_ZZZ"}),
        grant=g,
        expected_decision=DecisionType.BLOCK,
    )
    trace = ControlledTrace(name="t1", steps=[step1])
    r = _runner().run_trace(trace, AblationMode.HISTORY_AWARE_SCOPE)
    assert r.step_results[0].observed_decision == DecisionType.BLOCK
    assert "HISTORY_AWARE_SCOPE_DENY" in r.step_results[0].observed_rules


def test_default_variant_plan_includes_history_aware() -> None:
    plan = default_variant_plan()
    pairs = [(lab, m.value) for lab, m in plan]
    assert ("HistoryAware", "HISTORY_AWARE_SCOPE") in pairs
    assert ("Static+History", "STATIC_HISTORY_AWARE") in pairs


def test_static_history_allows_grant_scope_and_allowlisted_tool() -> None:
    g = _grant(allowed_ids={"file_A"})
    st = TraceStep(
        name="s1",
        event=_event(eid="e1", sid="sess_1", resource_ids={"file_A"}),
        grant=g,
        expected_decision=DecisionType.ALLOW,
    )
    trace = ControlledTrace(name="t1", steps=[st])
    state = HistoryAwareState(grant_resource_ids=grant_bound_resource_ids_for_trace(trace))
    d = static_history_aware_step(st, state)
    assert d.decision == DecisionType.ALLOW
    assert "file_A" in state.accepted_resource_ids


def test_static_history_blocks_disallowed_tool_even_when_resource_in_history() -> None:
    g = _grant(allowed_ids={"file_A"})
    anchor = VerifiedStructuredOutputAnchor(
        anchor_id="anc1",
        producer_event_id="e1",
        content_hash="hash:1",
        resource_ids={"file_B"},
        verified_by_controller=True,
        session_id="sess_1",
    )
    step1 = TraceStep(
        name="s1",
        event=_event(eid="e1", sid="sess_1", resource_ids={"file_A"}, step_id="s1", step_seq=0),
        grant=g,
        output_anchor=anchor,
        expected_decision=DecisionType.ALLOW,
    )
    step2 = TraceStep(
        name="s2",
        event=_event_tool(
            eid="e2",
            sid="sess_1",
            resource_ids={"file_B"},
            tool_name="create_email_draft",
            action="external_disclosure",
            step_id="s2",
            step_seq=1,
        ),
        grant=g,
        expected_decision=DecisionType.BLOCK,
    )
    trace = ControlledTrace(name="t1", steps=[step1, step2])
    state = HistoryAwareState(grant_resource_ids=grant_bound_resource_ids_for_trace(trace))
    assert static_history_aware_step(step1, state).decision == DecisionType.ALLOW
    assert "file_B" in state.accepted_resource_ids
    d2 = static_history_aware_step(step2, state)
    assert d2.decision == DecisionType.BLOCK
    assert any(v.rule == "STATIC_TOOL_ALLOWLIST_DENY" for v in d2.violations)


def test_static_history_blocks_resource_out_of_scope_even_with_allowlisted_tool() -> None:
    g = _grant(allowed_ids={"file_A"})
    st = TraceStep(
        name="s1",
        event=_event(eid="e1", sid="sess_1", resource_ids={"file_ZZZ"}),
        grant=g,
        expected_decision=DecisionType.BLOCK,
    )
    trace = ControlledTrace(name="t1", steps=[st])
    state = HistoryAwareState(grant_resource_ids=grant_bound_resource_ids_for_trace(trace))
    d = static_history_aware_step(st, state)
    assert d.decision == DecisionType.BLOCK
    assert any(v.rule == "STATIC_HISTORY_SCOPE_DENY" for v in d.violations)


def test_ablation_runner_static_history_aware() -> None:
    g = _grant(allowed_ids={"file_A"})
    step1 = TraceStep(
        name="s1",
        event=_event(eid="e1", sid="sess_1", resource_ids={"file_A"}),
        grant=g,
        expected_decision=DecisionType.ALLOW,
    )
    trace = ControlledTrace(name="t1", steps=[step1])
    r = _runner().run_trace(trace, AblationMode.STATIC_HISTORY_AWARE)
    assert r.step_results[0].observed_decision == DecisionType.ALLOW
    assert r.step_results[0].metadata.get("baseline") == "static_history_aware"
