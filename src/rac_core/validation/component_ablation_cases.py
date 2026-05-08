"""Single-component attack traces for component-specific ablation evaluation."""

from __future__ import annotations

from datetime import datetime

from rac_core.models import (
    DecisionType,
    GrantEnvelope,
    InputAnchorRef,
    TypedAuthorizationEvent,
    TypedEventConditions,
    TypedEventDelegation,
    TypedEventResourceScope,
    TypedEventSubject,
    VerifiedStructuredOutputAnchor,
)

from rac_core.validation.taxonomy_traces import (
    EXTERNAL_EMAIL,
    FILE_A,
    FILE_B,
    INTERNAL_EMAIL,
    TAX_SESS,
    _anchor,
    _evt,
    _make_grant,
    _read_step,
    _sum_step,
)

from .trace import ControlledTrace, TraceStep

T0 = datetime(2026, 4, 27, 12, 0, 0)


def _grant_o1() -> GrantEnvelope:
    return _make_grant(
        allowed_ids={FILE_A},
        purpose_scope={"internal_summarization", "analytics"},
        allowed_tools={"read_file", "summarize_file", "create_email_draft"},
        allowed_actions={"read", "summarize", "external_disclosure"},
    )


def _grant_p1() -> GrantEnvelope:
    return _make_grant(
        allowed_ids={FILE_A},
        purpose_scope={"internal_summarization", "analytics"},
        allowed_tools={"read_file", "summarize_file"},
        allowed_actions={"read", "summarize"},
    )


def _grant_a1() -> GrantEnvelope:
    return _make_grant(
        allowed_ids={FILE_A, EXTERNAL_EMAIL},
        purpose_scope={"internal_summarization"},
        allowed_tools={"read_file", "summarize_file", "create_email_draft"},
        allowed_actions={"read", "summarize", "external_disclosure"},
    )


def _grant_c1() -> GrantEnvelope:
    return _make_grant(
        allowed_ids={FILE_A, FILE_B},
        tenant="tenant_t1",
        purpose_scope={"internal_summarization"},
        allowed_tools={"read_file", "summarize_file"},
        allowed_actions={"read", "summarize"},
    )


def _grant_d1() -> GrantEnvelope:
    return _make_grant(
        allow_delegation=False,
        allowed_ids={FILE_A},
        purpose_scope={"internal_summarization"},
        allowed_tools={"read_file", "summarize_file"},
        allowed_actions={"read", "summarize"},
    )


def build_component_ablation_cases() -> list[ControlledTrace]:
    sid = TAX_SESS
    traces: list[ControlledTrace] = []

    g_o1 = _grant_o1()
    traces.append(
        ControlledTrace(
            name="o1_origin_only_unverifiable_text",
            description="O1: file_B in summarize without grant or anchor origin",
            metadata={"component": "origin", "miss_mode": "RAC_WITHOUT_RESOURCE_ORIGIN"},
            steps=[
                _read_step(
                    event_id="e_o1_0",
                    step_id="s0",
                    step_seq=0,
                    session_id=sid,
                    file_id=FILE_A,
                    grant=g_o1,
                    output_anchor=_anchor(
                        anchor_id="out_o1_0", producer_event_id="e_o1_0", resource_ids={FILE_A}
                    ),
                ),
                _sum_step(
                    event_id="e_o1_1",
                    step_id="s1",
                    step_seq=1,
                    session_id=sid,
                    resource_ids={FILE_B},
                    grant=g_o1,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_o1_0",
                            producer_event_id="e_o1_0",
                            content_hash="hash:out_o1_0",
                        )
                    ],
                    output_anchor=None,
                    expected=DecisionType.BLOCK,
                    rule="RESOURCE_ORIGIN_UNVERIFIABLE",
                ),
            ],
            expected_final_decision=DecisionType.BLOCK,
        )
    )

    g_l1 = _grant_o1()
    traces.append(
        ControlledTrace(
            name="l1_lineage_only_forged_hash",
            description="L1: content_hash mismatch on valid anchor id",
            metadata={"component": "lineage", "miss_mode": "RAC_WITHOUT_LINEAGE"},
            steps=[
                _read_step(
                    event_id="e_l1_0",
                    step_id="s0",
                    step_seq=0,
                    session_id=sid,
                    file_id=FILE_A,
                    grant=g_l1,
                    output_anchor=_anchor(
                        anchor_id="out_l1_0", producer_event_id="e_l1_0", resource_ids={FILE_A}
                    ),
                ),
                _sum_step(
                    event_id="e_l1_1",
                    step_id="s1",
                    step_seq=1,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g_l1,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_l1_0",
                            producer_event_id="e_l1_0",
                            content_hash="wrong_hash_for_l1",
                        )
                    ],
                    output_anchor=None,
                    expected=DecisionType.BLOCK,
                    rule="LINEAGE_INVALID",
                ),
            ],
            expected_final_decision=DecisionType.BLOCK,
        )
    )

    g_p1 = _grant_p1()
    traces.append(
        ControlledTrace(
            name="p1_purpose_only_external",
            description="P1: analytics purpose not in tightened basis",
            metadata={"component": "purpose", "miss_mode": "RAC_WITHOUT_PURPOSE"},
            steps=[
                _read_step(
                    event_id="e_p1_0",
                    step_id="s0",
                    step_seq=0,
                    session_id=sid,
                    file_id=FILE_A,
                    grant=g_p1,
                    output_anchor=_anchor(
                        anchor_id="out_p1_0", producer_event_id="e_p1_0", resource_ids={FILE_A}
                    ),
                ),
                _sum_step(
                    event_id="e_p1_1",
                    step_id="s1",
                    step_seq=1,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g_p1,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_p1_0",
                            producer_event_id="e_p1_0",
                            content_hash="hash:out_p1_0",
                        )
                    ],
                    purpose="analytics",
                    output_anchor=None,
                    expected=DecisionType.BLOCK,
                    rule="PURPOSE_DRIFT",
                ),
            ],
            expected_final_decision=DecisionType.BLOCK,
        )
    )

    g_a1 = _grant_a1()
    traces.append(
        ControlledTrace(
            name="a1_action_only_external_email",
            description="A1: summarize tool emits external_disclosure action on same file resource",
            metadata={"component": "action", "miss_mode": "RAC_WITHOUT_ACTION"},
            steps=[
                _read_step(
                    event_id="e_a1_0",
                    step_id="s0",
                    step_seq=0,
                    session_id=sid,
                    file_id=FILE_A,
                    grant=g_a1,
                    output_anchor=_anchor(
                        anchor_id="out_a1_0", producer_event_id="e_a1_0", resource_ids={FILE_A}
                    ),
                ),
                TraceStep(
                    name="s1",
                    event=_evt(
                        event_id="e_a1_1",
                        session_id=sid,
                        step_id="s1",
                        step_seq=1,
                        tool_name="summarize_file",
                        action="external_disclosure",
                        resource_type="file",
                        resource_ids={FILE_A},
                        purpose="internal_summarization",
                        input_anchors=[
                            InputAnchorRef(
                                anchor_id="out_a1_0",
                                producer_event_id="e_a1_0",
                                content_hash="hash:out_a1_0",
                            )
                        ],
                    ),
                    grant=g_a1,
                    output_anchor=None,
                    expected_decision=DecisionType.BLOCK,
                    expected_rule="ACTION_ESCALATION",
                    required_actions=["disclose.send_message"],
                ),
            ],
            expected_final_decision=DecisionType.BLOCK,
        )
    )

    traces.append(
        ControlledTrace(
            name="c1_condition_only_tenant_change",
            description="C1: tenant drift after chained read",
            metadata={"component": "condition", "miss_mode": "RAC_WITHOUT_CONDITIONS"},
            steps=[
                _read_step(
                    event_id="e_c1_0",
                    step_id="s0",
                    step_seq=0,
                    session_id=sid,
                    file_id=FILE_A,
                    grant=_grant_c1(),
                    output_anchor=_anchor(
                        anchor_id="out_c1_0", producer_event_id="e_c1_0", resource_ids={FILE_A}
                    ),
                ),
                TraceStep(
                    name="s1",
                    event=TypedAuthorizationEvent(
                        event_id="e_c1_1",
                        session_id=sid,
                        step_id="s1",
                        step_seq=1,
                        subject=TypedEventSubject(user_id="user_1", effective_subject="user_1"),
                        tool_name="read_file",
                        action="read",
                        resource_scope=TypedEventResourceScope(type="file", ids={FILE_A}),
                        purpose="internal_summarization",
                        conditions=TypedEventConditions(
                            time=T0,
                            environment="trusted_network",
                            tenant="tenant_t2",
                            runtime_labels={"internal"},
                        ),
                        delegation=TypedEventDelegation(),
                        input_anchors=[
                            InputAnchorRef(
                                anchor_id="out_c1_0",
                                producer_event_id="e_c1_0",
                                content_hash="hash:out_c1_0",
                            )
                        ],
                    ),
                    grant=_grant_c1(),
                    output_anchor=None,
                    expected_decision=DecisionType.BLOCK,
                    expected_rule="CONDITION_WEAKENING",
                ),
            ],
            expected_final_decision=DecisionType.BLOCK,
        )
    )

    g_d1 = _grant_d1()
    traces.append(
        ControlledTrace(
            name="d1_delegation_only_introduced",
            description="D1: delegated summarize when grant disallows delegation",
            metadata={"component": "delegation", "miss_mode": "RAC_WITHOUT_DELEGATION"},
            steps=[
                _read_step(
                    event_id="e_d1_0",
                    step_id="s0",
                    step_seq=0,
                    session_id=sid,
                    file_id=FILE_A,
                    grant=g_d1,
                    output_anchor=_anchor(
                        anchor_id="out_d1_0", producer_event_id="e_d1_0", resource_ids={FILE_A}
                    ),
                ),
                _sum_step(
                    event_id="e_d1_1",
                    step_id="s1",
                    step_seq=1,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g_d1,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_d1_0",
                            producer_event_id="e_d1_0",
                            content_hash="hash:out_d1_0",
                        )
                    ],
                    purpose="internal_summarization",
                    output_anchor=None,
                    expected=DecisionType.BLOCK,
                    rule="DELEGATION_AMPLIFICATION",
                    delegated=True,
                    delegatee="agent_sub",
                    depth=1,
                ),
            ],
            expected_final_decision=DecisionType.BLOCK,
        )
    )

    traces.append(
        ControlledTrace(
            name="an1_anchor_only_unverified_output",
            description="AN1: read with controller-unverified output anchor claim",
            metadata={"component": "anchor", "miss_mode": "RAC_WITHOUT_ANCHOR"},
            steps=[
                TraceStep(
                    name="s0",
                    event=TypedAuthorizationEvent(
                        event_id="e_an1_0",
                        session_id=sid,
                        step_id="s0",
                        step_seq=0,
                        subject=TypedEventSubject(user_id="user_1", effective_subject="user_1"),
                        tool_name="read_file",
                        action="read",
                        resource_scope=TypedEventResourceScope(type="file", ids={FILE_A}),
                        purpose="internal_summarization",
                        conditions=TypedEventConditions(
                            time=T0,
                            environment="trusted_network",
                            tenant="tenant_t1",
                            runtime_labels={"internal"},
                        ),
                        delegation=TypedEventDelegation(),
                    ),
                    grant=_grant_o1(),
                    output_anchor=VerifiedStructuredOutputAnchor(
                        anchor_id="out_an1_0",
                        producer_event_id="e_an1_0",
                        content_hash="hash:out_an1_0",
                        resource_ids={FILE_A},
                        verified_by_controller=False,
                        session_id=sid,
                    ),
                    expected_decision=DecisionType.BLOCK,
                    expected_rule="OUTPUT_ANCHOR_INVALID",
                ),
            ],
            expected_final_decision=DecisionType.BLOCK,
        )
    )

    g_ctrl = _make_grant(
        allowed_ids={FILE_A},
        purpose_scope={"internal_summarization"},
        allowed_tools={"read_file"},
        allowed_actions={"read"},
    )
    traces.append(
        ControlledTrace(
            name="benign_control_single_read",
            description="Benign control: single read (all ablation modes should ALLOW)",
            metadata={"component": "control", "miss_mode": None},
            steps=[
                _read_step(
                    event_id="e_ctrl_0",
                    step_id="s0",
                    step_seq=0,
                    session_id=sid,
                    file_id=FILE_A,
                    grant=g_ctrl,
                    output_anchor=_anchor(
                        anchor_id="out_ctrl_0", producer_event_id="e_ctrl_0", resource_ids={FILE_A}
                    ),
                ),
            ],
            expected_final_decision=DecisionType.ALLOW,
        )
    )

    return traces


def component_attack_checker_factory():
    """Checker for component attack suite (enforces verified output anchors)."""
    from rac_core.action_semantics.registry import ActionSemanticsRegistry
    from rac_core.action_semantics.taxonomy import default_semantics_yaml_path
    from rac_core.checker.action_lattice import ActionLattice
    from rac_core.checker.basis_tightening import BasisTightener
    from rac_core.checker.precommit import RACPreCommitChecker
    from rac_core.store import InMemoryBasisStore, InMemoryCausalLineageStore

    ls = InMemoryCausalLineageStore()
    bs = InMemoryBasisStore()
    lat = ActionLattice()
    reg = ActionSemanticsRegistry.load_from_yaml(default_semantics_yaml_path())
    return RACPreCommitChecker(
        lineage_store=ls,
        basis_store=bs,
        action_lattice=lat,
        basis_tightener=BasisTightener(action_lattice=lat),
        require_verified_output_anchor=True,
        action_semantics_registry=reg,
    )
