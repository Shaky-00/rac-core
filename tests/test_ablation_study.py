from collections.abc import Callable
from datetime import datetime

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
from rac_core.validation import (
    AblationMode,
    AblationRunner,
    ControlledTrace,
    TraceStep,
)


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


def build_checker_factory() -> Callable[[], RACPreCommitChecker]:
    def _factory() -> RACPreCommitChecker:
        lineage_store = InMemoryCausalLineageStore()
        basis_store = InMemoryBasisStore()
        return RACPreCommitChecker(lineage_store=lineage_store, basis_store=basis_store)

    return _factory


def build_ablation_runner() -> AblationRunner:
    return AblationRunner(checker_factory=build_checker_factory())


def benign_read_summarize_trace() -> ControlledTrace:
    grant = build_grant()
    return ControlledTrace(
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


def action_escalation_trace() -> ControlledTrace:
    grant = build_grant()
    return ControlledTrace(
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


def forged_predecessor_trace() -> ControlledTrace:
    grant = build_grant()
    return ControlledTrace(
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


def resource_expansion_trace() -> ControlledTrace:
    grant = build_grant()
    return ControlledTrace(
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


def test_full_rac_matches_oracle_on_benign_read_summarize() -> None:
    runner = build_ablation_runner()
    trace = benign_read_summarize_trace()
    result = runner.run_trace(trace, AblationMode.FULL_RAC)
    assert result.blocked_at_step is None
    assert len(result.step_results) == 2
    for sr in result.step_results:
        assert sr.false_positive is False
        assert sr.false_negative is False
        assert sr.observed_decision == sr.oracle_decision


def test_full_rac_blocks_action_escalation() -> None:
    runner = build_ablation_runner()
    trace = action_escalation_trace()
    result = runner.run_trace(trace, AblationMode.FULL_RAC)
    assert result.blocked_at_step == "step_external"
    step2 = result.step_results[1]
    assert step2.observed_decision == DecisionType.BLOCK
    assert "ACTION_ESCALATION" in step2.observed_rules
    assert step2.false_negative is False


def test_no_rac_misses_action_escalation() -> None:
    runner = build_ablation_runner()
    trace = action_escalation_trace()
    result = runner.run_trace(trace, AblationMode.NO_RAC)
    assert result.blocked_at_step is None
    assert len(result.step_results) == 2
    assert result.step_results[0].observed_decision == DecisionType.ALLOW
    s2 = result.step_results[1]
    assert s2.observed_decision == DecisionType.ALLOW
    assert s2.oracle_decision == DecisionType.BLOCK
    assert s2.false_negative is True


def test_entry_only_check_misses_second_step_drift() -> None:
    runner = build_ablation_runner()
    trace = action_escalation_trace()
    result = runner.run_trace(trace, AblationMode.ENTRY_ONLY_CHECK)
    assert result.blocked_at_step is None
    assert result.step_results[0].observed_decision == DecisionType.ALLOW
    s2 = result.step_results[1]
    assert s2.observed_decision == DecisionType.ALLOW
    assert s2.oracle_decision == DecisionType.BLOCK
    assert s2.false_negative is True


def test_rac_without_lineage_misses_forged_predecessor() -> None:
    runner = build_ablation_runner()
    trace = forged_predecessor_trace()
    full = runner.run_trace(trace, AblationMode.FULL_RAC)
    assert full.blocked_at_step == "step_forged"
    assert full.step_results[1].observed_decision == DecisionType.BLOCK

    no_lin = runner.run_trace(trace, AblationMode.RAC_WITHOUT_LINEAGE)
    assert no_lin.blocked_at_step is None
    assert no_lin.step_results[1].observed_decision == DecisionType.ALLOW
    assert no_lin.step_results[1].false_negative is True


def test_rac_without_resource_origin_disables_origin_failure() -> None:
    runner = build_ablation_runner()
    trace = resource_expansion_trace()
    full = runner.run_trace(trace, AblationMode.FULL_RAC)
    assert full.blocked_at_step == "step_bad_resource"
    full_s2 = full.step_results[1]
    assert full_s2.observed_decision == DecisionType.BLOCK
    assert "RESOURCE_ORIGIN_UNVERIFIABLE" in full_s2.observed_rules

    ablated = runner.run_trace(trace, AblationMode.RAC_WITHOUT_RESOURCE_ORIGIN)
    s2 = ablated.step_results[1]
    assert "RESOURCE_ORIGIN_UNVERIFIABLE" not in s2.observed_rules
    if s2.observed_decision == DecisionType.BLOCK:
        assert "RESOURCE_EXPANSION" in s2.observed_rules
    else:
        assert s2.observed_decision == DecisionType.ALLOW
        assert s2.false_negative is True


def test_summarize_ablation_counts_false_negatives() -> None:
    runner = build_ablation_runner()
    traces = [benign_read_summarize_trace(), action_escalation_trace()]
    results = runner.run_suite(traces, [AblationMode.FULL_RAC, AblationMode.NO_RAC])
    full_summary = runner.summarize(results, AblationMode.FULL_RAC)
    no_summary = runner.summarize(results, AblationMode.NO_RAC)
    assert full_summary.false_negative_count == 0
    assert no_summary.false_negative_count >= 1
    assert no_summary.drift_blocking_rate < full_summary.drift_blocking_rate
