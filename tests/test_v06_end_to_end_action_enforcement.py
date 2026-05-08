"""Minimal v0.6 E2E: expander → basis → sample manifest → EventAdapter → PreCommitChecker."""

from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path

from rac_core.action_semantics import (
    ActionSemanticsRegistry,
    GrantProfileExpander,
    default_grant_templates_yaml_path,
    default_semantics_yaml_path,
)
from rac_core.adapter import EventAdapter, load_tool_manifests_from_yaml, sample_tool_manifests_yaml_path
from rac_core.checker import RACPreCommitChecker
from rac_core.models import (
    AuthorizationBasis,
    AuthorizationProfile,
    BasisResourceScope,
    CausalLineageRecord,
    EffectProfile,
    InputAnchorRef,
    PendingToolCall,
    ResourceMapping,
    ResourceMetadata,
    RuntimeTraceContext,
    SessionContext,
    ToolManifest,
    TypedAuthorizationEvent,
    TypedEventResourceScope,
    TypedEventSubject,
    VerifiedStructuredOutputAnchor,
)
from rac_core.registry import InMemoryResourceRegistry, InMemoryToolManifestRegistry
from rac_core.store import InMemoryBasisStore, InMemoryCausalLineageStore

_spec = importlib.util.spec_from_file_location(
    "test_precommit_checker", Path(__file__).with_name("test_precommit_checker.py")
)
assert _spec and _spec.loader
_tpc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_tpc)
build_grant = _tpc.build_grant


def _sem() -> ActionSemanticsRegistry:
    return ActionSemanticsRegistry.load_from_yaml(default_semantics_yaml_path())


def _exp() -> GrantProfileExpander:
    return GrantProfileExpander.load_from_yaml(default_grant_templates_yaml_path(), _sem())


def _basis(templates: list[str]) -> AuthorizationBasis:
    p = _exp().expand_templates(templates)
    b = AuthorizationBasis.from_compiled_grant_profile(
        p,
        basis_id="basis_v06",
        subjects={"user_1"},
        resource_scope=BasisResourceScope(type="file", ids={"file_A"}),
        legacy_actions={"read", "summarize", "external_disclosure"},
    )
    return b.model_copy(update={"purpose_scope": b.purpose_scope | {"internal_summarization"}})


def _session() -> SessionContext:
    return SessionContext(
        session_id="sess_1",
        user_id="user_1",
        agent_id="agent_main",
        tenant="tenant_X",
        roles={"analyst"},
        effective_subject="user_1",
    )


def _sample_registry() -> InMemoryToolManifestRegistry:
    reg = InMemoryToolManifestRegistry()
    for _name, m in load_tool_manifests_from_yaml(sample_tool_manifests_yaml_path()).items():
        reg.register(m)
    reg.register(
        ToolManifest(
            tool_name="mutate_create_only",
            operation="summarize",
            resource_arg="file_id",
            resource_type="file",
            resource_pattern="file:*",
            output_anchor_fields=["output_id", "content_hash", "resource_ids"],
            authorization_effect="write_local",
            commit_type="write_internal",
            authorization_profile=AuthorizationProfile(
                required_actions=["mutate.create_object"],
                resource_mappings=[
                    ResourceMapping(
                        arg="file_id",
                        resource_role="target",
                        resource_type="file",
                        resource_pattern="file:*",
                    )
                ],
                effects=EffectProfile(
                    state_mutation=True,
                    external_disclosure=False,
                    authority_change=False,
                    real_world_effect=False,
                    consumes_anchor=False,
                    produces_anchor=True,
                    effect_boundary="internal",
                ),
                output_anchor_fields=["output_id"],
                commit_type="write_internal",
            ),
        )
    )
    return reg


def _resources() -> InMemoryResourceRegistry:
    r = InMemoryResourceRegistry()
    r.register(ResourceMetadata(resource_id="file_A", resource_type="file"))
    r.register(
        ResourceMetadata(resource_id="external@example.com", resource_type="external_channel")
    )
    return r


def _adapter() -> tuple[EventAdapter, InMemoryCausalLineageStore]:
    ls = InMemoryCausalLineageStore()
    return (
        EventAdapter(
            manifest_registry=_sample_registry(),
            resource_registry=_resources(),
            lineage_store=ls,
            action_semantics_registry=_sem(),
        ),
        ls,
    )


def _trace(
    *,
    step_id: str,
    step_seq: int,
    anchors: list | None = None,
    purpose: str | None = None,
) -> RuntimeTraceContext:
    return RuntimeTraceContext(
        session_id="sess_1",
        step_id=step_id,
        step_seq=step_seq,
        input_anchors=anchors or [],
        selected_purpose=purpose or "internal_summarization",
        observed_time=datetime(2026, 4, 26, 12, 0, 0),
        environment="trusted_workspace",
        tenant="tenant_X",
        runtime_labels={"internal"},
    )


def _checker(ls: InMemoryCausalLineageStore, bs: InMemoryBasisStore) -> RACPreCommitChecker:
    return RACPreCommitChecker(
        lineage_store=ls,
        basis_store=bs,
        action_semantics_registry=_sem(),
    )


def test_internal_analysis_read_file_allow_e2e() -> None:
    adapter, lineage = _adapter()
    basis_ia = _basis(["internal_analysis"])
    grant = build_grant()
    event = adapter.construct_event(
        session_context=_session(),
        grant_envelope=grant,
        pending_tool_call=PendingToolCall(tool_name="read_file", arguments={"file_id": "file_A"}),
        runtime_trace_context=_trace(step_id="step_read", step_seq=0),
    )
    assert event.required_actions == ["acquire.read_object"]
    assert event.action == "read"

    bs = InMemoryBasisStore()
    ch = _checker(lineage, bs)
    dec = ch.check(
        event,
        grant,
        initial_basis=basis_ia,
        output_anchor=VerifiedStructuredOutputAnchor(
            anchor_id="out_read",
            producer_event_id=event.event_id,
            content_hash="h1",
            resource_ids={"file_A"},
            verified_by_controller=True,
            session_id="sess_1",
        ),
    )
    assert dec.decision.value == "ALLOW"


def test_internal_analysis_summarize_file_allow_e2e() -> None:
    adapter, lineage = _adapter()
    basis_ia = _basis(["internal_analysis"])
    grant = build_grant()
    read_ev = adapter.construct_event(
        session_context=_session(),
        grant_envelope=grant,
        pending_tool_call=PendingToolCall(tool_name="read_file", arguments={"file_id": "file_A"}),
        runtime_trace_context=_trace(step_id="step_read", step_seq=0),
    )
    bs = InMemoryBasisStore()
    ch = _checker(lineage, bs)
    assert (
        ch.check(
            read_ev,
            grant,
            initial_basis=basis_ia,
            output_anchor=VerifiedStructuredOutputAnchor(
                anchor_id="out_read",
                producer_event_id=read_ev.event_id,
                content_hash="h1",
                resource_ids={"file_A"},
                verified_by_controller=True,
                session_id="sess_1",
            ),
        ).decision.value
        == "ALLOW"
    )

    sum_ev = adapter.construct_event(
        session_context=_session(),
        grant_envelope=grant,
        pending_tool_call=PendingToolCall(
            tool_name="summarize_file", arguments={"input_anchor": "x"}
        ),
        runtime_trace_context=_trace(
            step_id="step_sum",
            step_seq=1,
            anchors=[
                InputAnchorRef(
                    anchor_id="out_read",
                    producer_event_id=read_ev.event_id,
                    content_hash="h1",
                )
            ],
        ),
    )
    assert sum_ev.required_actions == ["transform.summarize"]
    assert ch.check(sum_ev, grant).decision.value == "ALLOW"


def test_read_only_summarize_blocked_e2e() -> None:
    adapter, lineage = _adapter()
    basis_ro = _basis(["read_only_retrieval"])
    grant = build_grant()
    read_ev = adapter.construct_event(
        session_context=_session(),
        grant_envelope=grant,
        pending_tool_call=PendingToolCall(tool_name="read_file", arguments={"file_id": "file_A"}),
        runtime_trace_context=_trace(step_id="step_r0", step_seq=0),
    )
    bs = InMemoryBasisStore()
    ch = _checker(lineage, bs)
    ch.check(
        read_ev,
        grant,
        initial_basis=basis_ro,
        output_anchor=VerifiedStructuredOutputAnchor(
            anchor_id="out_r0",
            producer_event_id=read_ev.event_id,
            content_hash="h0",
            resource_ids={"file_A"},
            verified_by_controller=True,
            session_id="sess_1",
        ),
    )
    sum_ev = adapter.construct_event(
        session_context=_session(),
        grant_envelope=grant,
        pending_tool_call=PendingToolCall(
            tool_name="summarize_file", arguments={"input_anchor": "x"}
        ),
        runtime_trace_context=_trace(
            step_id="step_s1",
            step_seq=1,
            anchors=[
                InputAnchorRef(
                    anchor_id="out_r0",
                    producer_event_id=read_ev.event_id,
                    content_hash="h0",
                )
            ],
        ),
    )
    dec = ch.check(sum_ev, grant)
    assert dec.decision.value == "BLOCK"
    assert any(v.rule == "ACTION_ESCALATION" for v in dec.violations)


def test_internal_analysis_disclose_email_blocked_e2e() -> None:
    adapter, lineage = _adapter()
    basis_ia = _basis(["internal_analysis"])
    grant = build_grant(allowed_ids={"file_A", "external@example.com"})
    read_ev = adapter.construct_event(
        session_context=_session(),
        grant_envelope=grant,
        pending_tool_call=PendingToolCall(tool_name="read_file", arguments={"file_id": "file_A"}),
        runtime_trace_context=_trace(step_id="step_r0", step_seq=0),
    )
    bs = InMemoryBasisStore()
    ch = _checker(lineage, bs)
    ch.check(
        read_ev,
        grant,
        initial_basis=basis_ia,
        output_anchor=VerifiedStructuredOutputAnchor(
            anchor_id="out0",
            producer_event_id=read_ev.event_id,
            content_hash="h0",
            resource_ids={"file_A"},
            verified_by_controller=True,
            session_id="sess_1",
        ),
    )
    email_ev = adapter.construct_event(
        session_context=_session(),
        grant_envelope=grant,
        pending_tool_call=PendingToolCall(
            tool_name="create_email_draft",
            arguments={"recipient": "external@example.com", "input_anchor": "x"},
        ),
        runtime_trace_context=_trace(
            step_id="step_m1",
            step_seq=1,
            anchors=[
                InputAnchorRef(
                    anchor_id="out0",
                    producer_event_id=read_ev.event_id,
                    content_hash="h0",
                )
            ],
        ),
    )
    assert "disclose.send_message" in email_ev.required_actions
    dec = ch.check(email_ev, grant)
    assert dec.decision.value == "BLOCK"
    assert any(
        v.rule == "ACTION_ESCALATION" and "disclose.send_message" in v.reason
        for v in dec.violations
    )


def test_internal_analysis_full_mutate_create_allow_e2e() -> None:
    adapter, lineage = _adapter()
    basis_full = _basis(["internal_analysis_full"])
    grant = build_grant()
    read_ev = adapter.construct_event(
        session_context=_session(),
        grant_envelope=grant,
        pending_tool_call=PendingToolCall(tool_name="read_file", arguments={"file_id": "file_A"}),
        runtime_trace_context=_trace(step_id="step_r0", step_seq=0),
    )
    bs = InMemoryBasisStore()
    ch = _checker(lineage, bs)
    ch.check(
        read_ev,
        grant,
        initial_basis=basis_full,
        output_anchor=VerifiedStructuredOutputAnchor(
            anchor_id="outf0",
            producer_event_id=read_ev.event_id,
            content_hash="hf0",
            resource_ids={"file_A"},
            verified_by_controller=True,
            session_id="sess_1",
        ),
    )
    mut_ev = adapter.construct_event(
        session_context=_session(),
        grant_envelope=grant,
        pending_tool_call=PendingToolCall(
            tool_name="mutate_create_only", arguments={"file_id": "file_A"}
        ),
        runtime_trace_context=_trace(
            step_id="step_m1",
            step_seq=1,
            anchors=[
                InputAnchorRef(
                    anchor_id="outf0",
                    producer_event_id=read_ev.event_id,
                    content_hash="hf0",
                )
            ],
        ),
    )
    assert mut_ev.required_actions == ["mutate.create_object"]
    assert ch.check(mut_ev, grant).decision.value == "ALLOW"


def test_v06_event_without_v06_basis_missing_e2e() -> None:
    adapter, lineage = _adapter()
    grant = build_grant()
    read_ev = adapter.construct_event(
        session_context=_session(),
        grant_envelope=grant,
        pending_tool_call=PendingToolCall(tool_name="read_file", arguments={"file_id": "file_A"}),
        runtime_trace_context=_trace(step_id="s0", step_seq=0),
    )
    lineage.append_step(
        CausalLineageRecord(
            session_id="sess_1",
            step_seq=0,
            step_id="s0",
            event_id=read_ev.event_id,
            tool_name="read_file",
            action="read",
            resource_ids={"file_A"},
            resource_type="file",
            purpose="internal_summarization",
            basis_id="b0",
            output_anchor=VerifiedStructuredOutputAnchor(
                anchor_id="outx",
                producer_event_id=read_ev.event_id,
                content_hash="hx",
                resource_ids={"file_A"},
                verified_by_controller=True,
                session_id="sess_1",
            ),
        )
    )
    bs = InMemoryBasisStore()
    bs.save_basis(
        "sess_1", "s0", AuthorizationBasis.from_grant_envelope(grant, basis_id="basis:seed:s0")
    )
    sum_ev = TypedAuthorizationEvent(
        event_id="evt_sum_only",
        session_id="sess_1",
        step_id="step_sum_only",
        step_seq=1,
        subject=read_ev.subject,
        tool_name="summarize_file",
        action="summarize",
        required_actions=["transform.summarize"],
        resource_scope=read_ev.resource_scope,
        purpose="internal_summarization",
        conditions=read_ev.conditions,
        delegation=read_ev.delegation,
        input_anchors=[
            InputAnchorRef(anchor_id="outx", producer_event_id=read_ev.event_id, content_hash="hx")
        ],
    )
    ch = _checker(lineage, bs)
    dec = ch.check(sum_ev, grant)
    assert dec.decision.value == "BLOCK"
    assert any(v.rule == "ACTION_BASIS_MISSING" for v in dec.violations)


def test_skip_action_escalation_skips_v06_coverage_e2e() -> None:
    adapter, lineage = _adapter()
    basis_ro = _basis(["read_only_retrieval"])
    grant = build_grant()
    read_ev = adapter.construct_event(
        session_context=_session(),
        grant_envelope=grant,
        pending_tool_call=PendingToolCall(tool_name="read_file", arguments={"file_id": "file_A"}),
        runtime_trace_context=_trace(step_id="sr0", step_seq=0),
    )
    bs = InMemoryBasisStore()
    ch = RACPreCommitChecker(
        lineage_store=lineage,
        basis_store=bs,
        action_semantics_registry=_sem(),
        skipped_consistency_rules=frozenset({"ACTION_ESCALATION"}),
    )
    ch.check(
        read_ev,
        grant,
        initial_basis=basis_ro,
        output_anchor=VerifiedStructuredOutputAnchor(
            anchor_id="outz",
            producer_event_id=read_ev.event_id,
            content_hash="hz",
            resource_ids={"file_A"},
            verified_by_controller=True,
            session_id="sess_1",
        ),
    )
    sum_ev = adapter.construct_event(
        session_context=_session(),
        grant_envelope=grant,
        pending_tool_call=PendingToolCall(
            tool_name="summarize_file", arguments={"input_anchor": "x"}
        ),
        runtime_trace_context=_trace(
            step_id="sz1",
            step_seq=1,
            anchors=[
                InputAnchorRef(
                    anchor_id="outz",
                    producer_event_id=read_ev.event_id,
                    content_hash="hz",
                )
            ],
        ),
    )
    dec = ch.check(sum_ev, grant)
    assert dec.decision.value == "ALLOW"
    assert not any(v.rule in ("ACTION_ESCALATION", "ACTION_BASIS_MISSING") for v in dec.violations)


def test_basis_tightener_preserves_allowed_labels_e2e() -> None:
    from rac_core.checker import BasisTightener

    basis_ia = _basis(["internal_analysis"])
    event = TypedAuthorizationEvent(
        event_id="evt_t",
        session_id="sess_1",
        step_id="step_t",
        step_seq=1,
        subject=TypedEventSubject(user_id="user_1", effective_subject="user_1"),
        tool_name="summarize_file",
        action="summarize",
        required_actions=["transform.summarize"],
        resource_scope=TypedEventResourceScope(type="file", ids={"file_A"}),
        purpose="internal_summarization",
        input_anchors=[],
    )
    bt = BasisTightener()
    res = bt.tighten_basis(
        basis_ia,
        event,
        new_basis_id="basis:tight",
    )
    assert res.valid and res.basis is not None
    assert "transform.summarize" in res.basis.allowed_action_labels

    lineage2 = InMemoryCausalLineageStore()
    bs2 = InMemoryBasisStore()
    rec0 = CausalLineageRecord(
        session_id="sess_1",
        step_seq=0,
        step_id="step0",
        event_id="evt0",
        tool_name="read_file",
        action="read",
        resource_ids={"file_A"},
        resource_type="file",
        purpose="internal_summarization",
        basis_id=res.basis.basis_id,
        output_anchor=VerifiedStructuredOutputAnchor(
            anchor_id="out_tight",
            producer_event_id="evt0",
            content_hash="ht",
            resource_ids={"file_A"},
            verified_by_controller=True,
            session_id="sess_1",
        ),
    )
    lineage2.append_step(rec0)
    bs2.save_basis("sess_1", "step0", res.basis)
    grant2 = build_grant()
    adapter2 = EventAdapter(
        manifest_registry=_sample_registry(),
        resource_registry=_resources(),
        lineage_store=lineage2,
        action_semantics_registry=_sem(),
    )
    sum2 = adapter2.construct_event(
        session_context=_session(),
        grant_envelope=grant2,
        pending_tool_call=PendingToolCall(
            tool_name="summarize_file", arguments={"input_anchor": "x"}
        ),
        runtime_trace_context=_trace(
            step_id="step1",
            step_seq=1,
            anchors=[
                InputAnchorRef(
                    anchor_id="out_tight",
                    producer_event_id="evt0",
                    content_hash="ht",
                )
            ],
        ),
    )
    assert _checker(lineage2, bs2).check(sum2, grant2).decision.value == "ALLOW"
