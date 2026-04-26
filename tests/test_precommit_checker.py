from datetime import datetime

from rac_core.checker import RACPreCommitChecker
from rac_core.models import (
    AuthorizationBasis,
    CausalLineageRecord,
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


def build_grant(
    *,
    allowed_actions: set[str] | None = None,
    allowed_ids: set[str] | None = None,
    purpose_scope: set[str] | None = None,
) -> GrantEnvelope:
    return GrantEnvelope(
        grant_id="grant_1",
        session_id="sess_1",
        subject=GrantSubject(user_id="user_1", effective_subject="user_1"),
        allowed_actions=allowed_actions or {"read", "summarize"},
        resource_scope=ResourceScope(type="file", allowed_ids=allowed_ids or {"file_A"}),
        purpose_scope=purpose_scope or {"internal_summarization"},
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
    advisory_hints: list[str] | None = None,
    environment: str = "trusted_workspace",
    delegated: bool = False,
) -> TypedAuthorizationEvent:
    return TypedAuthorizationEvent(
        event_id=event_id,
        session_id="sess_1",
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
        delegation=TypedEventDelegation(delegated=delegated, delegatee="agent_sub"),
        input_anchors=input_anchors or [],
        advisory_predecessor_hints=advisory_hints or [],
    )


def build_verified_anchor(
    *, anchor_id: str, producer_event_id: str, resource_ids: set[str]
) -> VerifiedStructuredOutputAnchor:
    return VerifiedStructuredOutputAnchor(
        anchor_id=anchor_id,
        producer_event_id=producer_event_id,
        content_hash=f"hash:{anchor_id}",
        resource_ids=resource_ids,
        verified_by_controller=True,
        session_id="sess_1",
    )


def build_checker() -> tuple[RACPreCommitChecker, InMemoryCausalLineageStore, InMemoryBasisStore]:
    lineage_store = InMemoryCausalLineageStore()
    basis_store = InMemoryBasisStore()
    checker = RACPreCommitChecker(lineage_store=lineage_store, basis_store=basis_store)
    return checker, lineage_store, basis_store


def test_local_allow_false_returns_block_local_deny() -> None:
    checker, _, _ = build_checker()
    decision = checker.check(
        build_event(
            event_id="evt_1",
            step_id="step_1",
            step_seq=0,
            action="read",
            tool_name="read_file",
            resource_ids={"file_A"},
        ),
        build_grant(),
        local_allow=False,
    )
    assert decision.decision == DecisionType.BLOCK
    assert any(v.rule == "LOCAL_DENY" for v in decision.violations)


def test_benign_initial_read_allowed_and_persisted() -> None:
    checker, lineage_store, basis_store = build_checker()
    event = build_event(
        event_id="evt_read",
        step_id="step_read",
        step_seq=0,
        action="read",
        tool_name="read_file",
        resource_ids={"file_A"},
    )
    decision = checker.check(
        event,
        build_grant(),
        output_anchor=build_verified_anchor(
            anchor_id="out_read", producer_event_id="evt_read", resource_ids={"file_A"}
        ),
    )
    assert decision.decision == DecisionType.ALLOW
    assert lineage_store.get_step("step_read", "sess_1") is not None
    assert basis_store.load_finalized_basis("sess_1", "step_read") is not None


def test_benign_read_then_summarize_allowed() -> None:
    checker, _, _ = build_checker()
    grant = build_grant()
    read_event = build_event(
        event_id="evt_read",
        step_id="step_read",
        step_seq=0,
        action="read",
        tool_name="read_file",
        resource_ids={"file_A"},
    )
    read_decision = checker.check(
        read_event,
        grant,
        output_anchor=build_verified_anchor(
            anchor_id="out_read", producer_event_id="evt_read", resource_ids={"file_A"}
        ),
    )
    assert read_decision.decision == DecisionType.ALLOW

    summarize_event = build_event(
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
    )
    summarize_decision = checker.check(summarize_event, grant)
    assert summarize_decision.decision == DecisionType.ALLOW


def test_read_to_external_disclosure_blocked() -> None:
    checker, _, _ = build_checker()
    decision = checker.check(
        build_event(
            event_id="evt_1",
            step_id="step_1",
            step_seq=0,
            action="external_disclosure",
            tool_name="create_email_draft",
            resource_ids={"file_A"},
        ),
        build_grant(allowed_actions={"read", "summarize"}),
    )
    assert decision.decision == DecisionType.BLOCK
    assert any(v.rule == "ACTION_ESCALATION" for v in decision.violations)


def test_file_a_to_file_b_without_verified_origin_blocked() -> None:
    checker, _, _ = build_checker()
    decision = checker.check(
        build_event(
            event_id="evt_1",
            step_id="step_1",
            step_seq=0,
            action="read",
            tool_name="read_file",
            resource_ids={"file_B"},
        ),
        build_grant(allowed_ids={"file_A"}),
    )
    assert decision.decision == DecisionType.BLOCK
    assert any(v.rule == "RESOURCE_ORIGIN_UNVERIFIABLE" for v in decision.violations)


def test_purpose_drift_blocked() -> None:
    checker, _, _ = build_checker()
    decision = checker.check(
        build_event(
            event_id="evt_1",
            step_id="step_1",
            step_seq=0,
            action="read",
            tool_name="read_file",
            resource_ids={"file_A"},
            purpose="external_sharing",
        ),
        build_grant(purpose_scope={"internal_summarization"}),
    )
    assert decision.decision == DecisionType.BLOCK
    assert any(v.rule == "PURPOSE_DRIFT" for v in decision.violations)


def test_condition_weakening_blocked() -> None:
    checker, _, _ = build_checker()
    grant = build_grant()
    read_event = build_event(
        event_id="evt_read",
        step_id="step_read",
        step_seq=0,
        action="read",
        tool_name="read_file",
        resource_ids={"file_A"},
    )
    checker.check(
        read_event,
        grant,
        output_anchor=build_verified_anchor(
            anchor_id="out_read", producer_event_id="evt_read", resource_ids={"file_A"}
        ),
    )
    bad_event = build_event(
        event_id="evt_bad",
        step_id="step_bad",
        step_seq=1,
        action="summarize",
        tool_name="summarize_file",
        resource_ids={"file_A"},
        environment="external_workspace",
        input_anchors=[
            InputAnchorRef(
                anchor_id="out_read",
                producer_event_id="evt_read",
                content_hash="hash:out_read",
            )
        ],
    )
    decision = checker.check(bad_event, grant)
    assert decision.decision == DecisionType.BLOCK
    assert any(v.rule == "CONDITION_WEAKENING" for v in decision.violations)


def test_delegation_amplification_blocked() -> None:
    checker, _, _ = build_checker()
    decision = checker.check(
        build_event(
            event_id="evt_1",
            step_id="step_1",
            step_seq=0,
            action="read",
            tool_name="read_file",
            resource_ids={"file_A"},
            delegated=True,
        ),
        build_grant(),
    )
    assert decision.decision == DecisionType.BLOCK
    assert any(v.rule == "DELEGATION_AMPLIFICATION" for v in decision.violations)


def test_multi_predecessor_unsupported_blocked() -> None:
    checker, lineage_store, basis_store = build_checker()
    grant = build_grant(allowed_ids={"file_A", "file_B"})

    record_a = CausalLineageRecord(
        session_id="sess_1",
        step_seq=0,
        step_id="step_a",
        event_id="evt_a",
        tool_name="read_file",
        action="read",
        resource_ids={"file_A"},
        resource_type="file",
        purpose="internal_summarization",
        basis_id="basis_a",
        output_anchor=build_verified_anchor(
            anchor_id="out_a", producer_event_id="evt_a", resource_ids={"file_A"}
        ),
    )
    lineage_store.append_step(record_a)
    basis_store.save_basis(
        "sess_1",
        "step_a",
        AuthorizationBasis.from_grant_envelope(grant, basis_id="basis_a"),
    )

    record_b = CausalLineageRecord(
        session_id="sess_1",
        step_seq=1,
        step_id="step_b",
        event_id="evt_b",
        parent_hash=record_a.step_hash,
        tool_name="read_file",
        action="read",
        resource_ids={"file_B"},
        resource_type="file",
        purpose="internal_summarization",
        basis_id="basis_b",
        output_anchor=build_verified_anchor(
            anchor_id="out_b", producer_event_id="evt_b", resource_ids={"file_B"}
        ),
    )
    lineage_store.append_step(record_b)
    basis_store.save_basis(
        "sess_1",
        "step_b",
        AuthorizationBasis.from_grant_envelope(grant, basis_id="basis_b"),
    )

    event = build_event(
        event_id="evt_c",
        step_id="step_c",
        step_seq=2,
        action="summarize",
        tool_name="summarize_file",
        resource_ids={"file_A", "file_B"},
        input_anchors=[InputAnchorRef(anchor_id="out_a"), InputAnchorRef(anchor_id="out_b")],
    )
    decision = checker.check(event, grant)
    assert decision.decision == DecisionType.BLOCK
    assert any(v.rule == "MULTI_PREDECESSOR_UNSUPPORTED" for v in decision.violations)


def test_persist_false_does_not_write_stores() -> None:
    checker, lineage_store, basis_store = build_checker()
    event = build_event(
        event_id="evt_1",
        step_id="step_1",
        step_seq=0,
        action="read",
        tool_name="read_file",
        resource_ids={"file_A"},
    )
    decision = checker.check(event, build_grant(), persist=False)
    assert decision.decision == DecisionType.ALLOW
    assert lineage_store.get_step("step_1", "sess_1") is None
    assert basis_store.load_finalized_basis("sess_1", "step_1") is None
