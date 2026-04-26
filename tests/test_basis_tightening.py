from datetime import datetime

from rac_core.checker import BasisTightener
from rac_core.models import (
    AuthorizationBasis,
    BasisConditions,
    BasisDelegation,
    BasisResourceScope,
    TimeWindow,
    TypedAuthorizationEvent,
    TypedEventConditions,
    TypedEventDelegation,
    TypedEventResourceScope,
    TypedEventSubject,
)


def build_basis() -> AuthorizationBasis:
    return AuthorizationBasis(
        basis_id="basis_inherited",
        subjects={"user_1"},
        actions={"read", "summarize"},
        resource_scope=BasisResourceScope(type="file", ids={"file_A"}),
        purpose_scope={"internal_summarization"},
        delegation=BasisDelegation(allow_delegation=False),
        conditions=BasisConditions(
            time_window=TimeWindow(
                start=datetime(2026, 4, 26, 0, 0, 0),
                end=datetime(2026, 4, 26, 23, 59, 59),
            ),
            environment="trusted_workspace",
            tenant="tenant_X",
            runtime_labels={"internal", "confidential"},
        ),
    )


def build_event(
    *,
    action: str = "read",
    resource_ids: set[str] | None = None,
    purpose: str = "internal_summarization",
    environment: str = "trusted_workspace",
    delegated: bool = False,
) -> TypedAuthorizationEvent:
    return TypedAuthorizationEvent(
        event_id="evt_1",
        session_id="sess_1",
        step_id="step_1",
        step_seq=1,
        subject=TypedEventSubject(user_id="user_1", effective_subject="user_1"),
        tool_name="read_file",
        action=action,
        resource_scope=TypedEventResourceScope(type="file", ids=resource_ids or {"file_A"}),
        purpose=purpose,
        conditions=TypedEventConditions(
            time=datetime(2026, 4, 26, 12, 0, 0),
            environment=environment,
            tenant="tenant_X",
            runtime_labels={"internal"},
        ),
        delegation=TypedEventDelegation(delegated=delegated, delegatee="agent_sub"),
    )


def test_read_event_tightens_basis_successfully() -> None:
    tightener = BasisTightener()
    result = tightener.tighten_basis(build_basis(), build_event(action="read"), "basis_new")
    assert result.valid
    assert result.basis is not None
    assert result.basis.basis_id == "basis_new"
    assert result.basis.resource_scope.ids == {"file_A"}


def test_summarize_after_read_remains_allowed() -> None:
    tightener = BasisTightener()
    result = tightener.tighten_basis(
        build_basis(), build_event(action="summarize"), "basis_new"
    )
    assert result.valid
    assert result.basis is not None
    assert "summarize" in result.basis.actions


def test_resource_intersection_empty_returns_basis_empty_after_update() -> None:
    tightener = BasisTightener()
    result = tightener.tighten_basis(
        build_basis(), build_event(resource_ids={"file_B"}), "basis_new"
    )
    assert not result.valid
    assert result.rule == "BASIS_EMPTY_AFTER_UPDATE"


def test_purpose_intersection_empty_returns_basis_empty_after_update() -> None:
    tightener = BasisTightener()
    result = tightener.tighten_basis(
        build_basis(), build_event(purpose="external_sharing"), "basis_new"
    )
    assert not result.valid
    assert result.rule == "BASIS_EMPTY_AFTER_UPDATE"


def test_action_escalation_returns_action_escalation() -> None:
    tightener = BasisTightener()
    result = tightener.tighten_basis(
        build_basis(), build_event(action="external_disclosure"), "basis_new"
    )
    assert not result.valid
    assert result.rule == "ACTION_ESCALATION"


def test_condition_mismatch_returns_condition_weakening() -> None:
    tightener = BasisTightener()
    result = tightener.tighten_basis(
        build_basis(), build_event(environment="external_workspace"), "basis_new"
    )
    assert not result.valid
    assert result.rule == "CONDITION_WEAKENING"


def test_delegation_amplification_returns_delegation_amplification() -> None:
    tightener = BasisTightener()
    result = tightener.tighten_basis(
        build_basis(), build_event(delegated=True), "basis_new"
    )
    assert not result.valid
    assert result.rule == "DELEGATION_AMPLIFICATION"
