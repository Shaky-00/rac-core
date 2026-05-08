"""RACPreCommitChecker v0.6 action coverage (leaf required_actions vs basis.allowed_action_labels)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from rac_core.action_semantics import (
    ActionSemanticsRegistry,
    GrantProfileExpander,
    default_grant_templates_yaml_path,
    default_semantics_yaml_path,
)
from rac_core.checker import RACPreCommitChecker
from rac_core.models import (
    AuthorizationBasis,
    BasisResourceScope,
    CausalLineageRecord,
    DecisionType,
    InputAnchorRef,
    TypedAuthorizationEvent,
    VerifiedStructuredOutputAnchor,
)
from rac_core.store import InMemoryBasisStore, InMemoryCausalLineageStore

_spec = importlib.util.spec_from_file_location(
    "test_precommit_checker", Path(__file__).with_name("test_precommit_checker.py")
)
assert _spec and _spec.loader
_tpc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_tpc)
build_event = _tpc.build_event
build_grant = _tpc.build_grant


def _semantics() -> ActionSemanticsRegistry:
    return ActionSemanticsRegistry.load_from_yaml(default_semantics_yaml_path())


def _expander() -> GrantProfileExpander:
    return GrantProfileExpander.load_from_yaml(default_grant_templates_yaml_path(), _semantics())


def _basis_from_templates(template_ids: list[str]) -> AuthorizationBasis:
    profile = _expander().expand_templates(template_ids)
    b = AuthorizationBasis.from_compiled_grant_profile(
        profile,
        basis_id="basis_v06",
        subjects={"user_1"},
        resource_scope=BasisResourceScope(type="file", ids={"file_A"}),
        legacy_actions={"read", "summarize"},
    )
    # Align with default build_grant() purpose_scope so legacy purpose checks pass.
    return b.model_copy(
        update={"purpose_scope": b.purpose_scope | {"internal_summarization"}}
    )


def _checker() -> tuple[RACPreCommitChecker, InMemoryCausalLineageStore, InMemoryBasisStore]:
    ls = InMemoryCausalLineageStore()
    bs = InMemoryBasisStore()
    return (
        RACPreCommitChecker(
            lineage_store=ls,
            basis_store=bs,
            action_semantics_registry=_semantics(),
        ),
        ls,
        bs,
    )


def _append_prev(
    lineage: InMemoryCausalLineageStore,
    basis_store: InMemoryBasisStore,
    basis: AuthorizationBasis,
) -> None:
    rec = CausalLineageRecord(
        session_id="sess_1",
        step_seq=0,
        step_id="step_prev",
        event_id="evt_prev",
        tool_name="read_file",
        action="read",
        resource_ids={"file_A"},
        resource_type="file",
        purpose="internal_summarization",
        basis_id="basis_prev",
        output_anchor=VerifiedStructuredOutputAnchor(
            anchor_id="out_prev",
            producer_event_id="evt_prev",
            content_hash="h",
            resource_ids={"file_A"},
            verified_by_controller=True,
            session_id="sess_1",
        ),
    )
    lineage.append_step(rec)
    basis_store.save_basis("sess_1", "step_prev", basis)


def _summarize_event_v06(required: list[str]) -> TypedAuthorizationEvent:
    return build_event(
        event_id="evt_sum",
        step_id="step_sum",
        step_seq=1,
        action="summarize",
        tool_name="summarize_file",
        resource_ids={"file_A"},
        input_anchors=[
            InputAnchorRef(anchor_id="out_prev", producer_event_id="evt_prev", content_hash="h")
        ],
    ).model_copy(update={"required_actions": required})


def test_v06_exact_leaf_allow() -> None:
    checker, lineage, basis_store = _checker()
    _append_prev(lineage, basis_store, _basis_from_templates(["internal_analysis"]))
    ev = _summarize_event_v06(["transform.summarize"])
    assert checker.check(ev, build_grant()).decision == DecisionType.ALLOW


def test_v06_order_coverage_allow() -> None:
    checker, lineage, basis_store = _checker()
    _append_prev(lineage, basis_store, _basis_from_templates(["internal_analysis"]))
    ev = _summarize_event_v06(["transform.extract_field"])
    assert checker.check(ev, build_grant()).decision == DecisionType.ALLOW


def test_v06_reverse_order_blocks() -> None:
    checker, lineage, basis_store = _checker()
    basis = _basis_from_templates(["internal_analysis"]).model_copy(
        update={"allowed_action_labels": ["transform.extract_field"]}
    )
    _append_prev(lineage, basis_store, basis)
    ev = _summarize_event_v06(["transform.summarize"])
    decision = checker.check(ev, build_grant())
    assert decision.decision == DecisionType.BLOCK
    assert any(v.rule == "ACTION_ESCALATION" for v in decision.violations)


def test_internal_analysis_basis_covers_summarize() -> None:
    checker, lineage, basis_store = _checker()
    _append_prev(lineage, basis_store, _basis_from_templates(["internal_analysis"]))
    assert checker.check(_summarize_event_v06(["transform.summarize"]), build_grant()).decision == DecisionType.ALLOW


def test_read_only_basis_blocks_summarize() -> None:
    checker, lineage, basis_store = _checker()
    _append_prev(lineage, basis_store, _basis_from_templates(["read_only_retrieval"]))
    assert checker.check(_summarize_event_v06(["transform.summarize"]), build_grant()).decision == DecisionType.BLOCK


def test_internal_analysis_cannot_cover_disclose_send() -> None:
    checker, lineage, basis_store = _checker()
    _append_prev(lineage, basis_store, _basis_from_templates(["internal_analysis"]))
    ev = build_event(
        event_id="evt_ext",
        step_id="step_ext",
        step_seq=1,
        action="external_disclosure",
        tool_name="create_email_draft",
        resource_ids={"file_A"},
        input_anchors=[
            InputAnchorRef(anchor_id="out_prev", producer_event_id="evt_prev", content_hash="h")
        ],
    ).model_copy(update={"required_actions": ["disclose.send_message"]})
    assert checker.check(ev, build_grant()).decision == DecisionType.BLOCK


def test_multi_required_all_covered_allow() -> None:
    checker, lineage, basis_store = _checker()
    _append_prev(lineage, basis_store, _basis_from_templates(["internal_analysis_full"]))
    ev = build_event(
        event_id="evt_cmp",
        step_id="step_cmp",
        step_seq=1,
        action="read",
        tool_name="compare_reports",
        resource_ids={"file_A"},
        input_anchors=[
            InputAnchorRef(anchor_id="out_prev", producer_event_id="evt_prev", content_hash="h")
        ],
    ).model_copy(
        update={
            "required_actions": [
                "acquire.query_collection",
                "transform.aggregate_compare",
            ]
        }
    )
    assert checker.check(ev, build_grant()).decision == DecisionType.ALLOW


def test_multi_required_one_missing_blocks() -> None:
    checker, lineage, basis_store = _checker()
    _append_prev(lineage, basis_store, _basis_from_templates(["read_only_retrieval"]))
    ev = build_event(
        event_id="evt_cmp",
        step_id="step_cmp",
        step_seq=1,
        action="read",
        tool_name="compare_reports",
        resource_ids={"file_A"},
        input_anchors=[
            InputAnchorRef(anchor_id="out_prev", producer_event_id="evt_prev", content_hash="h")
        ],
    ).model_copy(
        update={
            "required_actions": [
                "acquire.query_collection",
                "transform.aggregate_compare",
            ]
        }
    )
    decision = checker.check(ev, build_grant())
    assert decision.decision == DecisionType.BLOCK


def test_required_actions_without_basis_labels_blocks() -> None:
    checker, lineage, basis_store = _checker()
    grant = build_grant()
    _append_prev(lineage, basis_store, AuthorizationBasis.from_grant_envelope(grant, basis_id="basis_prev"))
    ev = _summarize_event_v06(["transform.summarize"])
    decision = checker.check(ev, grant)
    assert decision.decision == DecisionType.BLOCK
    assert any(v.rule == "ACTION_BASIS_MISSING" for v in decision.violations)


def test_unknown_required_action_blocked() -> None:
    checker, lineage, basis_store = _checker()
    _append_prev(lineage, basis_store, _basis_from_templates(["internal_analysis"]))
    decision = checker.check(_summarize_event_v06(["not.a.registered.leaf"]), build_grant())
    assert decision.decision == DecisionType.BLOCK
    assert any("Unknown or non-leaf" in v.reason for v in decision.violations)


def test_category_required_action_blocked() -> None:
    checker, lineage, basis_store = _checker()
    _append_prev(lineage, basis_store, _basis_from_templates(["internal_analysis"]))
    assert checker.check(_summarize_event_v06(["meta"]), build_grant()).decision == DecisionType.BLOCK


def test_tighten_preserves_allowed_labels_in_persisted_basis() -> None:
    checker, lineage, basis_store = _checker()
    _append_prev(lineage, basis_store, _basis_from_templates(["internal_analysis"]))
    assert checker.check(_summarize_event_v06(["transform.summarize"]), build_grant()).decision == DecisionType.ALLOW
    b1 = basis_store.load_finalized_basis("sess_1", "step_sum")
    assert b1 is not None
    assert "transform.summarize" in b1.allowed_action_labels
    assert "transform.extract_field" in b1.allowed_action_labels
