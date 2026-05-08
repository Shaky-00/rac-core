from datetime import datetime

from rac_core.action_semantics.registry import ActionSemanticsRegistry
from rac_core.action_semantics.taxonomy import default_semantics_yaml_path
from rac_core.checker import RACPreCommitChecker
from rac_core.models import (
    DecisionType,
    GrantConditions,
    GrantEnvelope,
    GrantSubject,
    InputAnchorRef,
    ResourceScope,
    TypedAuthorizationEvent,
    TypedEventConditions,
    TypedEventDelegation,
    TypedEventResourceScope,
    TypedEventSubject,
    VerifiedStructuredOutputAnchor,
)
from rac_core.store import InMemoryBasisStore, InMemoryCausalLineageStore
from rac_core.validation import ControlledTrace, TraceRunner, TraceStep


def build_grant(
    *,
    session_id: str = "sess_1",
    allowed_actions: set[str] | None = None,
    allowed_tools: set[str] | None = None,
    allowed_ids: set[str] | None = None,
    purpose_scope: set[str] | None = None,
    allow_delegation: bool = False,
) -> GrantEnvelope:
    return GrantEnvelope(
        grant_id="grant_1",
        session_id=session_id,
        subject=GrantSubject(user_id="user_1", effective_subject="user_1"),
        allowed_actions=allowed_actions or {"read", "summarize"},
        allowed_tools=allowed_tools or {"read_file", "summarize_file"},
        resource_scope=ResourceScope(type="file", allowed_ids=allowed_ids or {"file_A"}),
        purpose_scope=purpose_scope or {"internal_summarization"},
        delegation={"allow_delegation": allow_delegation},
        conditions=GrantConditions(
            environment="trusted_workspace",
            tenant="tenant_X",
            runtime_labels={"internal"},
        ),
    )


def build_event(
    *,
    event_id: str,
    step_id: str,
    step_seq: int,
    action: str,
    tool_name: str,
    resource_ids: set[str],
    purpose: str = "internal_summarization",
    input_anchors: list[InputAnchorRef] | None = None,
    environment: str = "trusted_workspace",
    delegated: bool = False,
    session_id: str = "sess_1",
    advisory_hints: list[str] | None = None,
) -> TypedAuthorizationEvent:
    return TypedAuthorizationEvent(
        event_id=event_id,
        session_id=session_id,
        step_id=step_id,
        step_seq=step_seq,
        subject=TypedEventSubject(user_id="user_1", effective_subject="user_1"),
        tool_name=tool_name,
        action=action,
        resource_scope=TypedEventResourceScope(type="file", ids=resource_ids),
        purpose=purpose,
        conditions=TypedEventConditions(
            time=datetime(2026, 4, 26, 12, 0, 0),
            environment=environment,
            tenant="tenant_X",
            runtime_labels={"internal"},
        ),
        delegation=TypedEventDelegation(
            delegated=delegated, delegatee="agent_sub", delegator="user_1", delegation_depth=1
        ),
        input_anchors=input_anchors or [],
        advisory_predecessor_hints=advisory_hints or [],
    )


def build_verified_anchor(
    *,
    anchor_id: str,
    producer_event_id: str,
    resource_ids: set[str],
    session_id: str = "sess_1",
) -> VerifiedStructuredOutputAnchor:
    return VerifiedStructuredOutputAnchor(
        anchor_id=anchor_id,
        producer_event_id=producer_event_id,
        content_hash=f"hash:{anchor_id}",
        resource_ids=resource_ids,
        verified_by_controller=True,
        session_id=session_id,
    )


def build_runner() -> tuple[TraceRunner, InMemoryCausalLineageStore, InMemoryBasisStore]:
    lineage_store = InMemoryCausalLineageStore()
    basis_store = InMemoryBasisStore()
    checker = RACPreCommitChecker(
        lineage_store=lineage_store,
        basis_store=basis_store,
        action_semantics_registry=ActionSemanticsRegistry.load_from_yaml(
            default_semantics_yaml_path()
        ),
    )
    return TraceRunner(checker), lineage_store, basis_store


def assert_trace_expectations(result, blocked_step: str | None = None) -> None:
    assert result.passed is True
    for step_result in result.step_results:
        assert step_result.decision.decision == step_result.expected_decision
        if step_result.expected_rule is not None:
            assert step_result.expected_rule in step_result.observed_rules
    assert result.blocked_at_step == blocked_step


def test_benign_read_summarize_passes() -> None:
    runner, lineage_store, basis_store = build_runner()
    grant = build_grant()
    trace = ControlledTrace(
        name="benign-read-summarize",
        steps=[
            TraceStep(
                name="step_read",
                event=build_event(
                    event_id="evt_read",
                    step_id="step_read",
                    step_seq=0,
                    action="read",
                    tool_name="read_file",
                    resource_ids={"file_A"},
                ),
                grant=grant,
                output_anchor=build_verified_anchor(
                    anchor_id="out_read",
                    producer_event_id="evt_read",
                    resource_ids={"file_A"},
                ),
                expected_decision=DecisionType.ALLOW,
            ),
            TraceStep(
                name="step_summarize",
                event=build_event(
                    event_id="evt_sum",
                    step_id="step_sum",
                    step_seq=1,
                    action="summarize",
                    tool_name="summarize_file",
                    resource_ids={"file_A"},
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_read",
                            producer_event_id="evt_read",
                            content_hash="hash:out_read",
                        )
                    ],
                ),
                grant=grant,
                expected_decision=DecisionType.ALLOW,
            ),
        ],
        expected_final_decision=DecisionType.ALLOW,
    )
    result = runner.run(trace)
    assert_trace_expectations(result)
    assert lineage_store.get_step("step_read", "sess_1") is not None
    assert lineage_store.get_step("step_sum", "sess_1") is not None
    assert basis_store.load_finalized_basis("sess_1", "step_read") is not None
    assert basis_store.load_finalized_basis("sess_1", "step_sum") is not None


def test_action_escalation_read_to_external_disclosure_blocked() -> None:
    runner, _, _ = build_runner()
    grant = build_grant()
    trace = ControlledTrace(
        name="action-escalation",
        steps=[
            TraceStep(
                name="step_read",
                event=build_event(
                    event_id="evt_read",
                    step_id="step_read",
                    step_seq=0,
                    action="read",
                    tool_name="read_file",
                    resource_ids={"file_A"},
                ),
                grant=grant,
                output_anchor=build_verified_anchor(
                    anchor_id="out_read", producer_event_id="evt_read", resource_ids={"file_A"}
                ),
                expected_decision=DecisionType.ALLOW,
            ),
            TraceStep(
                name="step_external",
                event=build_event(
                    event_id="evt_external",
                    step_id="step_external",
                    step_seq=1,
                    action="external_disclosure",
                    tool_name="create_email_draft",
                    resource_ids={"file_A"},
                    input_anchors=[InputAnchorRef(anchor_id="out_read")],
                ),
                grant=grant,
                expected_decision=DecisionType.BLOCK,
                expected_rule="ACTION_ESCALATION",
            ),
        ],
        expected_final_decision=DecisionType.BLOCK,
    )
    result = runner.run(trace)
    assert_trace_expectations(result, blocked_step="step_external")


def test_resource_expansion_file_a_to_file_b_blocked() -> None:
    runner, _, _ = build_runner()
    grant = build_grant()
    trace = ControlledTrace(
        name="resource-expansion",
        steps=[
            TraceStep(
                name="step_read",
                event=build_event(
                    event_id="evt_read",
                    step_id="step_read",
                    step_seq=0,
                    action="read",
                    tool_name="read_file",
                    resource_ids={"file_A"},
                ),
                grant=grant,
                output_anchor=build_verified_anchor(
                    anchor_id="out_read", producer_event_id="evt_read", resource_ids={"file_A"}
                ),
                expected_decision=DecisionType.ALLOW,
            ),
            TraceStep(
                name="step_bad_resource",
                event=build_event(
                    event_id="evt_bad",
                    step_id="step_bad",
                    step_seq=1,
                    action="summarize",
                    tool_name="summarize_file",
                    resource_ids={"file_B"},
                    input_anchors=[InputAnchorRef(anchor_id="out_read")],
                ),
                grant=grant,
                expected_decision=DecisionType.BLOCK,
                expected_rule="RESOURCE_ORIGIN_UNVERIFIABLE",
            ),
        ],
        expected_final_decision=DecisionType.BLOCK,
    )
    result = runner.run(trace)
    assert_trace_expectations(result, blocked_step="step_bad_resource")


def test_purpose_drift_blocked() -> None:
    runner, _, _ = build_runner()
    grant = build_grant()
    trace = ControlledTrace(
        name="purpose-drift",
        steps=[
            TraceStep(
                name="step_read",
                event=build_event(
                    event_id="evt_read",
                    step_id="step_read",
                    step_seq=0,
                    action="read",
                    tool_name="read_file",
                    resource_ids={"file_A"},
                ),
                grant=grant,
                output_anchor=build_verified_anchor(
                    anchor_id="out_read", producer_event_id="evt_read", resource_ids={"file_A"}
                ),
                expected_decision=DecisionType.ALLOW,
            ),
            TraceStep(
                name="step_purpose_drift",
                event=build_event(
                    event_id="evt_pd",
                    step_id="step_pd",
                    step_seq=1,
                    action="summarize",
                    tool_name="summarize_file",
                    resource_ids={"file_A"},
                    purpose="external_sharing",
                    input_anchors=[InputAnchorRef(anchor_id="out_read")],
                ),
                grant=grant,
                expected_decision=DecisionType.BLOCK,
                expected_rule="PURPOSE_DRIFT",
            ),
        ],
        expected_final_decision=DecisionType.BLOCK,
    )
    result = runner.run(trace)
    assert_trace_expectations(result, blocked_step="step_purpose_drift")


def test_delegation_amplification_blocked() -> None:
    runner, _, _ = build_runner()
    grant = build_grant(allow_delegation=False)
    trace = ControlledTrace(
        name="delegation-amplification",
        steps=[
            TraceStep(
                name="step_delegate",
                event=build_event(
                    event_id="evt_delegate",
                    step_id="step_delegate",
                    step_seq=0,
                    action="read",
                    tool_name="read_file",
                    resource_ids={"file_A"},
                    delegated=True,
                ),
                grant=grant,
                expected_decision=DecisionType.BLOCK,
                expected_rule="DELEGATION_AMPLIFICATION",
            )
        ],
        expected_final_decision=DecisionType.BLOCK,
    )
    result = runner.run(trace)
    assert_trace_expectations(result, blocked_step="step_delegate")


def test_condition_weakening_blocked() -> None:
    runner, _, _ = build_runner()
    grant = build_grant()
    trace = ControlledTrace(
        name="condition-weakening",
        steps=[
            TraceStep(
                name="step_read",
                event=build_event(
                    event_id="evt_read",
                    step_id="step_read",
                    step_seq=0,
                    action="read",
                    tool_name="read_file",
                    resource_ids={"file_A"},
                ),
                grant=grant,
                output_anchor=build_verified_anchor(
                    anchor_id="out_read", producer_event_id="evt_read", resource_ids={"file_A"}
                ),
                expected_decision=DecisionType.ALLOW,
            ),
            TraceStep(
                name="step_bad_env",
                event=build_event(
                    event_id="evt_bad_env",
                    step_id="step_bad_env",
                    step_seq=1,
                    action="summarize",
                    tool_name="summarize_file",
                    resource_ids={"file_A"},
                    environment="external_workspace",
                    input_anchors=[InputAnchorRef(anchor_id="out_read")],
                ),
                grant=grant,
                expected_decision=DecisionType.BLOCK,
                expected_rule="CONDITION_WEAKENING",
            ),
        ],
        expected_final_decision=DecisionType.BLOCK,
    )
    result = runner.run(trace)
    assert_trace_expectations(result, blocked_step="step_bad_env")


def test_forged_predecessor_blocked() -> None:
    runner, _, _ = build_runner()
    grant = build_grant()
    trace = ControlledTrace(
        name="forged-predecessor",
        steps=[
            TraceStep(
                name="step_read",
                event=build_event(
                    event_id="evt_read",
                    step_id="step_read",
                    step_seq=0,
                    action="read",
                    tool_name="read_file",
                    resource_ids={"file_A"},
                ),
                grant=grant,
                output_anchor=build_verified_anchor(
                    anchor_id="out_read", producer_event_id="evt_read", resource_ids={"file_A"}
                ),
                expected_decision=DecisionType.ALLOW,
            ),
            TraceStep(
                name="step_forged",
                event=build_event(
                    event_id="evt_forged",
                    step_id="step_forged",
                    step_seq=1,
                    action="summarize",
                    tool_name="summarize_file",
                    resource_ids={"file_A"},
                    input_anchors=[InputAnchorRef(anchor_id="out_fake")],
                ),
                grant=grant,
                expected_decision=DecisionType.BLOCK,
                expected_rule="LINEAGE_INVALID",
            ),
        ],
        expected_final_decision=DecisionType.BLOCK,
    )
    result = runner.run(trace)
    assert_trace_expectations(result, blocked_step="step_forged")


def test_advisory_hint_conflict_does_not_override_runtime_lineage() -> None:
    runner, _, _ = build_runner()
    grant = build_grant()
    trace = ControlledTrace(
        name="advisory-conflict-runtime-wins",
        steps=[
            TraceStep(
                name="step_read",
                event=build_event(
                    event_id="evt_read",
                    step_id="step_read",
                    step_seq=0,
                    action="read",
                    tool_name="read_file",
                    resource_ids={"file_A"},
                ),
                grant=grant,
                output_anchor=build_verified_anchor(
                    anchor_id="out_read", producer_event_id="evt_read", resource_ids={"file_A"}
                ),
                expected_decision=DecisionType.ALLOW,
            ),
            TraceStep(
                name="step_sum",
                event=build_event(
                    event_id="evt_sum",
                    step_id="step_sum",
                    step_seq=1,
                    action="summarize",
                    tool_name="summarize_file",
                    resource_ids={"file_A"},
                    input_anchors=[InputAnchorRef(anchor_id="out_read")],
                    advisory_hints=["evt_fake"],
                ),
                grant=grant,
                expected_decision=DecisionType.ALLOW,
            ),
        ],
        expected_final_decision=DecisionType.ALLOW,
    )
    result = runner.run(trace)
    assert_trace_expectations(result)


def test_multi_predecessor_unsupported_blocked() -> None:
    runner, _, _ = build_runner()
    grant = build_grant(
        allowed_ids={"file_A", "file_B"},
        allowed_actions={"read", "summarize"},
    )
    trace = ControlledTrace(
        name="multi-predecessor-unsupported",
        steps=[
            TraceStep(
                name="step_read_a",
                event=build_event(
                    event_id="evt_read_a",
                    step_id="step_read_a",
                    step_seq=0,
                    action="read",
                    tool_name="read_file",
                    resource_ids={"file_A"},
                ),
                grant=grant,
                output_anchor=build_verified_anchor(
                    anchor_id="out_A", producer_event_id="evt_read_a", resource_ids={"file_A"}
                ),
                expected_decision=DecisionType.ALLOW,
            ),
            TraceStep(
                name="step_read_b",
                event=build_event(
                    event_id="evt_read_b",
                    step_id="step_read_b",
                    step_seq=1,
                    action="read",
                    tool_name="read_file",
                    resource_ids={"file_B"},
                ),
                grant=grant,
                output_anchor=build_verified_anchor(
                    anchor_id="out_B", producer_event_id="evt_read_b", resource_ids={"file_B"}
                ),
                expected_decision=DecisionType.ALLOW,
            ),
            TraceStep(
                name="step_join",
                event=build_event(
                    event_id="evt_join",
                    step_id="step_join",
                    step_seq=2,
                    action="summarize",
                    tool_name="summarize_file",
                    resource_ids={"file_A", "file_B"},
                    input_anchors=[InputAnchorRef(anchor_id="out_A"), InputAnchorRef(anchor_id="out_B")],
                ),
                grant=grant,
                expected_decision=DecisionType.BLOCK,
                expected_rule="MULTI_PREDECESSOR_UNSUPPORTED",
            ),
        ],
        expected_final_decision=DecisionType.BLOCK,
    )
    result = runner.run(trace)
    assert_trace_expectations(result, blocked_step="step_join")
