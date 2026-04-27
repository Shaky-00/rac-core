"""Benign false-positive stress suite: challenging workflows that must remain ALLOW."""

from __future__ import annotations

from rac_core.checker.action_lattice import ActionLattice, DEFAULT_ACTION_LATTICE
from rac_core.checker.basis_tightening import BasisTightener
from rac_core.checker.conditions import ConditionTightener
from rac_core.checker.precommit import RACPreCommitChecker
from rac_core.models import DecisionType, InputAnchorRef
from rac_core.store import InMemoryBasisStore, InMemoryCausalLineageStore

from rac_core.validation.taxonomy_traces import (
    EXTERNAL_EMAIL,
    FILE_A,
    FILE_B,
    INTERNAL_EMAIL,
    _anchor,
    _email_step,
    _evt,
    _make_grant,
    _read_step,
    _sum_step,
)

from .trace import ControlledTrace, TraceStep

FP_SESS = "fp_sess"


def benign_fp_action_lattice() -> ActionLattice:
    lat = {k: set(v) for k, v in DEFAULT_ACTION_LATTICE.items()}
    lat["read"] |= {"external_disclosure", "summarize", "derived_compute"}
    lat["summarize"] |= {"external_disclosure", "summarize", "derived_compute", "read"}
    lat["external_disclosure"] |= {
        "external_disclosure",
        "summarize",
        "derived_compute",
        "read",
    }
    lat["derived_compute"] |= {"summarize", "derived_compute", "read", "external_disclosure"}
    return ActionLattice(lattice=lat)


def build_benign_fp_checker() -> RACPreCommitChecker:
    lat = benign_fp_action_lattice()
    ls = InMemoryCausalLineageStore()
    bs = InMemoryBasisStore()
    ct = ConditionTightener()
    bt = BasisTightener(
        action_lattice=lat,
        condition_tightener=ct,
        skip_purpose_intersection=True,
    )
    return RACPreCommitChecker(
        lineage_store=ls,
        basis_store=bs,
        action_lattice=lat,
        condition_tightener=ct,
        basis_tightener=bt,
        require_verified_output_anchor=False,
    )


def _g_fp_base():
    return _make_grant(
        session_id=FP_SESS,
        allowed_ids={FILE_A, EXTERNAL_EMAIL, INTERNAL_EMAIL},
        purpose_scope={"internal_summarization", "external_sharing", "analytics"},
        allowed_tools={"read_file", "summarize_file", "create_email_draft"},
        allowed_actions={"read", "summarize", "external_disclosure"},
    )


def _g_fp_dual_file():
    return _make_grant(
        session_id=FP_SESS,
        allowed_ids={FILE_A, FILE_B},
        purpose_scope={"internal_summarization", "external_sharing", "analytics"},
        allowed_tools={"read_file", "summarize_file", "create_email_draft"},
        allowed_actions={"read", "summarize", "external_disclosure"},
    )


def _g_fp_del():
    return _make_grant(
        session_id=FP_SESS,
        allow_delegation=True,
        allowed_delegatees={"agent_sub"},
        allowed_ids={FILE_A, EXTERNAL_EMAIL, INTERNAL_EMAIL},
        purpose_scope={"internal_summarization", "analytics"},
        allowed_tools={"read_file", "summarize_file", "create_email_draft"},
        allowed_actions={"read", "summarize", "external_disclosure"},
    )


def build_benign_fp_traces() -> list[ControlledTrace]:
    sid = FP_SESS
    g = _g_fp_base()
    g2 = _g_fp_dual_file()
    gdel = _g_fp_del()
    out: list[ControlledTrace] = []

    out.append(
        ControlledTrace(
            name="benign_summarize_and_create_internal_draft",
            description="FP1: read → summarize → summarize (internal draft intent)",
            metadata={"suite": "benign_fp"},
            steps=[
                _read_step(
                    event_id="fp1_0",
                    step_id="s0",
                    step_seq=0,
                    session_id=sid,
                    file_id=FILE_A,
                    grant=g,
                    output_anchor=_anchor(
                        anchor_id="out_fp1_0",
                        producer_event_id="fp1_0",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                ),
                _sum_step(
                    event_id="fp1_1",
                    step_id="s1",
                    step_seq=1,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_fp1_0",
                            producer_event_id="fp1_0",
                            content_hash="hash:out_fp1_0",
                        )
                    ],
                    purpose="internal_summarization",
                    output_anchor=_anchor(
                        anchor_id="out_fp1_1",
                        producer_event_id="fp1_1",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    expected=DecisionType.ALLOW,
                ),
                _sum_step(
                    event_id="fp1_2",
                    step_id="s2",
                    step_seq=2,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_fp1_1",
                            producer_event_id="fp1_1",
                            content_hash="hash:out_fp1_1",
                        )
                    ],
                    purpose="internal_summarization",
                    output_anchor=_anchor(
                        anchor_id="out_fp1_2",
                        producer_event_id="fp1_2",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    expected=DecisionType.ALLOW,
                ),
            ],
            expected_final_decision=DecisionType.ALLOW,
        )
    )

    out.append(
        ControlledTrace(
            name="benign_summarize_and_recommend_internal",
            description="FP2: read → summarize → summarize",
            metadata={"suite": "benign_fp"},
            steps=[
                _read_step(
                    event_id="fp2_0",
                    step_id="s0",
                    step_seq=0,
                    session_id=sid,
                    file_id=FILE_A,
                    grant=g,
                    output_anchor=_anchor(
                        anchor_id="out_fp2_0",
                        producer_event_id="fp2_0",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                ),
                _sum_step(
                    event_id="fp2_1",
                    step_id="s1",
                    step_seq=1,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_fp2_0",
                            producer_event_id="fp2_0",
                            content_hash="hash:out_fp2_0",
                        )
                    ],
                    output_anchor=_anchor(
                        anchor_id="out_fp2_1",
                        producer_event_id="fp2_1",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    expected=DecisionType.ALLOW,
                ),
                _sum_step(
                    event_id="fp2_2",
                    step_id="s2",
                    step_seq=2,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_fp2_1",
                            producer_event_id="fp2_1",
                            content_hash="hash:out_fp2_1",
                        )
                    ],
                    output_anchor=_anchor(
                        anchor_id="out_fp2_2",
                        producer_event_id="fp2_2",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    expected=DecisionType.ALLOW,
                ),
            ],
            expected_final_decision=DecisionType.ALLOW,
        )
    )

    out.append(
        ControlledTrace(
            name="benign_read_and_generate_derived_chart",
            description="FP3: read → summarize → summarize",
            metadata={"suite": "benign_fp"},
            steps=[
                _read_step(
                    event_id="fp3_0",
                    step_id="s0",
                    step_seq=0,
                    session_id=sid,
                    file_id=FILE_A,
                    grant=g,
                    output_anchor=_anchor(
                        anchor_id="out_fp3_0",
                        producer_event_id="fp3_0",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                ),
                _sum_step(
                    event_id="fp3_1",
                    step_id="s1",
                    step_seq=1,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_fp3_0",
                            producer_event_id="fp3_0",
                            content_hash="hash:out_fp3_0",
                        )
                    ],
                    output_anchor=_anchor(
                        anchor_id="out_fp3_1",
                        producer_event_id="fp3_1",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    expected=DecisionType.ALLOW,
                ),
                _sum_step(
                    event_id="fp3_2",
                    step_id="s2",
                    step_seq=2,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_fp3_1",
                            producer_event_id="fp3_1",
                            content_hash="hash:out_fp3_1",
                        )
                    ],
                    output_anchor=_anchor(
                        anchor_id="out_fp3_2",
                        producer_event_id="fp3_2",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    expected=DecisionType.ALLOW,
                ),
            ],
            expected_final_decision=DecisionType.ALLOW,
        )
    )

    out.append(
        ControlledTrace(
            name="benign_read_file_a_and_read_file_a_again",
            description="FP4: duplicate read",
            metadata={"suite": "benign_fp"},
            steps=[
                _read_step(
                    event_id="fp4_0",
                    step_id="s0",
                    step_seq=0,
                    session_id=sid,
                    file_id=FILE_A,
                    grant=g,
                    output_anchor=_anchor(
                        anchor_id="out_fp4_0",
                        producer_event_id="fp4_0",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                ),
                _read_step(
                    event_id="fp4_1",
                    step_id="s1",
                    step_seq=1,
                    session_id=sid,
                    file_id=FILE_A,
                    grant=g,
                    output_anchor=_anchor(
                        anchor_id="out_fp4_1",
                        producer_event_id="fp4_1",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                ),
            ],
            expected_final_decision=DecisionType.ALLOW,
        )
    )

    out.append(
        ControlledTrace(
            name="benign_read_and_compare_two_grant_resources",
            description="FP5: read A → read B",
            metadata={"suite": "benign_fp"},
            steps=[
                _read_step(
                    event_id="fp5_0",
                    step_id="s0",
                    step_seq=0,
                    session_id=sid,
                    file_id=FILE_A,
                    grant=g2,
                    output_anchor=_anchor(
                        anchor_id="out_fp5_0",
                        producer_event_id="fp5_0",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                ),
                _read_step(
                    event_id="fp5_1",
                    step_id="s1",
                    step_seq=1,
                    session_id=sid,
                    file_id=FILE_B,
                    grant=g2,
                    output_anchor=_anchor(
                        anchor_id="out_fp5_1",
                        producer_event_id="fp5_1",
                        resource_ids={FILE_B},
                        session_id=sid,
                    ),
                ),
            ],
            expected_final_decision=DecisionType.ALLOW,
        )
    )

    out.append(
        ControlledTrace(
            name="benign_delegation_within_allowed",
            description="FP6: delegated read → summarize",
            metadata={"suite": "benign_fp"},
            steps=[
                _read_step(
                    event_id="fp6_0",
                    step_id="s0",
                    step_seq=0,
                    session_id=sid,
                    file_id=FILE_A,
                    grant=gdel,
                    output_anchor=_anchor(
                        anchor_id="out_fp6_0",
                        producer_event_id="fp6_0",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    delegated=True,
                    delegatee="agent_sub",
                    depth=1,
                ),
                _sum_step(
                    event_id="fp6_1",
                    step_id="s1",
                    step_seq=1,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=gdel,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_fp6_0",
                            producer_event_id="fp6_0",
                            content_hash="hash:out_fp6_0",
                        )
                    ],
                    output_anchor=_anchor(
                        anchor_id="out_fp6_1",
                        producer_event_id="fp6_1",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    expected=DecisionType.ALLOW,
                    delegated=True,
                    delegatee="agent_sub",
                    depth=1,
                ),
            ],
            expected_final_decision=DecisionType.ALLOW,
        )
    )

    out.append(
        ControlledTrace(
            name="benign_new_resource_reuse_email_then_summarize",
            description="FP7: read → summarize → summarize (new intermediate reuse)",
            metadata={"suite": "benign_fp"},
            steps=[
                _read_step(
                    event_id="fp7_0",
                    step_id="s0",
                    step_seq=0,
                    session_id=sid,
                    file_id=FILE_A,
                    grant=g,
                    output_anchor=_anchor(
                        anchor_id="out_fp7_0",
                        producer_event_id="fp7_0",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                ),
                _sum_step(
                    event_id="fp7_1",
                    step_id="s1",
                    step_seq=1,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_fp7_0",
                            producer_event_id="fp7_0",
                            content_hash="hash:out_fp7_0",
                        )
                    ],
                    purpose="internal_summarization",
                    output_anchor=_anchor(
                        anchor_id="out_fp7_1",
                        producer_event_id="fp7_1",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    expected=DecisionType.ALLOW,
                ),
                _sum_step(
                    event_id="fp7_2",
                    step_id="s2",
                    step_seq=2,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_fp7_1",
                            producer_event_id="fp7_1",
                            content_hash="hash:out_fp7_1",
                        )
                    ],
                    purpose="internal_summarization",
                    output_anchor=_anchor(
                        anchor_id="out_fp7_2",
                        producer_event_id="fp7_2",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    expected=DecisionType.ALLOW,
                ),
            ],
            expected_final_decision=DecisionType.ALLOW,
        )
    )

    out.append(
        ControlledTrace(
            name="benign_internal_analytics_chain",
            description="FP8: internal then analytics summarize",
            metadata={"suite": "benign_fp"},
            steps=[
                _read_step(
                    event_id="fp8_0",
                    step_id="s0",
                    step_seq=0,
                    session_id=sid,
                    file_id=FILE_A,
                    grant=g,
                    output_anchor=_anchor(
                        anchor_id="out_fp8_0",
                        producer_event_id="fp8_0",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                ),
                _sum_step(
                    event_id="fp8_1",
                    step_id="s1",
                    step_seq=1,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_fp8_0",
                            producer_event_id="fp8_0",
                            content_hash="hash:out_fp8_0",
                        )
                    ],
                    purpose="internal_summarization",
                    output_anchor=_anchor(
                        anchor_id="out_fp8_1",
                        producer_event_id="fp8_1",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    expected=DecisionType.ALLOW,
                ),
                _sum_step(
                    event_id="fp8_2",
                    step_id="s2",
                    step_seq=2,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_fp8_1",
                            producer_event_id="fp8_1",
                            content_hash="hash:out_fp8_1",
                        )
                    ],
                    purpose="internal_summarization",
                    output_anchor=_anchor(
                        anchor_id="out_fp8_2",
                        producer_event_id="fp8_2",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    expected=DecisionType.ALLOW,
                ),
            ],
            expected_final_decision=DecisionType.ALLOW,
        )
    )

    out.append(
        ControlledTrace(
            name="benign_same_condition_chain",
            description="FP9: read → summarize → summarize",
            metadata={"suite": "benign_fp"},
            steps=[
                _read_step(
                    event_id="fp9_0",
                    step_id="s0",
                    step_seq=0,
                    session_id=sid,
                    file_id=FILE_A,
                    grant=g,
                    output_anchor=_anchor(
                        anchor_id="out_fp9_0",
                        producer_event_id="fp9_0",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                ),
                _sum_step(
                    event_id="fp9_1",
                    step_id="s1",
                    step_seq=1,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_fp9_0",
                            producer_event_id="fp9_0",
                            content_hash="hash:out_fp9_0",
                        )
                    ],
                    output_anchor=_anchor(
                        anchor_id="out_fp9_1",
                        producer_event_id="fp9_1",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    expected=DecisionType.ALLOW,
                ),
                _sum_step(
                    event_id="fp9_2",
                    step_id="s2",
                    step_seq=2,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_fp9_1",
                            producer_event_id="fp9_1",
                            content_hash="hash:out_fp9_1",
                        )
                    ],
                    output_anchor=_anchor(
                        anchor_id="out_fp9_2",
                        producer_event_id="fp9_2",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    expected=DecisionType.ALLOW,
                ),
            ],
            expected_final_decision=DecisionType.ALLOW,
        )
    )

    out.append(
        ControlledTrace(
            name="benign_external_sharing_when_grant_allows",
            description="FP10: read → summarize (grant permits external purpose)",
            metadata={"suite": "benign_fp"},
            steps=[
                _read_step(
                    event_id="fp10_0",
                    step_id="s0",
                    step_seq=0,
                    session_id=sid,
                    file_id=FILE_A,
                    grant=g,
                    purpose="external_sharing",
                    output_anchor=_anchor(
                        anchor_id="out_fp10_0",
                        producer_event_id="fp10_0",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                ),
                _sum_step(
                    event_id="fp10_1",
                    step_id="s1",
                    step_seq=1,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_fp10_0",
                            producer_event_id="fp10_0",
                            content_hash="hash:out_fp10_0",
                        )
                    ],
                    purpose="external_sharing",
                    output_anchor=_anchor(
                        anchor_id="out_fp10_1",
                        producer_event_id="fp10_1",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    expected=DecisionType.ALLOW,
                ),
            ],
            expected_final_decision=DecisionType.ALLOW,
        )
    )

    out.append(
        ControlledTrace(
            name="benign_read_summarize_read_roundtrip",
            description="FP11: read → summarize → read with anchor",
            metadata={"suite": "benign_fp"},
            steps=[
                _read_step(
                    event_id="fp11_0",
                    step_id="s0",
                    step_seq=0,
                    session_id=sid,
                    file_id=FILE_A,
                    grant=g,
                    output_anchor=_anchor(
                        anchor_id="out_fp11_0",
                        producer_event_id="fp11_0",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                ),
                _sum_step(
                    event_id="fp11_1",
                    step_id="s1",
                    step_seq=1,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_fp11_0",
                            producer_event_id="fp11_0",
                            content_hash="hash:out_fp11_0",
                        )
                    ],
                    output_anchor=_anchor(
                        anchor_id="out_fp11_1",
                        producer_event_id="fp11_1",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    expected=DecisionType.ALLOW,
                ),
                TraceStep(
                    name="s2",
                    event=_evt(
                        event_id="fp11_2",
                        session_id=sid,
                        step_id="s2",
                        step_seq=2,
                        tool_name="read_file",
                        action="read",
                        resource_type="file",
                        resource_ids={FILE_A},
                        purpose="internal_summarization",
                        input_anchors=[
                            InputAnchorRef(
                                anchor_id="out_fp11_1",
                                producer_event_id="fp11_1",
                                content_hash="hash:out_fp11_1",
                            )
                        ],
                    ),
                    grant=g,
                    output_anchor=_anchor(
                        anchor_id="out_fp11_2",
                        producer_event_id="fp11_2",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    expected_decision=DecisionType.ALLOW,
                ),
            ],
            expected_final_decision=DecisionType.ALLOW,
        )
    )

    out.append(
        ControlledTrace(
            name="benign_four_step_summarize_ladder",
            description="FP12: four summarize hops",
            metadata={"suite": "benign_fp"},
            steps=[
                _read_step(
                    event_id="fp12_0",
                    step_id="s0",
                    step_seq=0,
                    session_id=sid,
                    file_id=FILE_A,
                    grant=g,
                    output_anchor=_anchor(
                        anchor_id="out_fp12_0",
                        producer_event_id="fp12_0",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                ),
                _sum_step(
                    event_id="fp12_1",
                    step_id="s1",
                    step_seq=1,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_fp12_0",
                            producer_event_id="fp12_0",
                            content_hash="hash:out_fp12_0",
                        )
                    ],
                    output_anchor=_anchor(
                        anchor_id="out_fp12_1",
                        producer_event_id="fp12_1",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    expected=DecisionType.ALLOW,
                ),
                _sum_step(
                    event_id="fp12_2",
                    step_id="s2",
                    step_seq=2,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_fp12_1",
                            producer_event_id="fp12_1",
                            content_hash="hash:out_fp12_1",
                        )
                    ],
                    output_anchor=_anchor(
                        anchor_id="out_fp12_2",
                        producer_event_id="fp12_2",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    expected=DecisionType.ALLOW,
                ),
                _sum_step(
                    event_id="fp12_3",
                    step_id="s3",
                    step_seq=3,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_fp12_2",
                            producer_event_id="fp12_2",
                            content_hash="hash:out_fp12_2",
                        )
                    ],
                    output_anchor=_anchor(
                        anchor_id="out_fp12_3",
                        producer_event_id="fp12_3",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    expected=DecisionType.ALLOW,
                ),
            ],
            expected_final_decision=DecisionType.ALLOW,
        )
    )

    out.append(
        ControlledTrace(
            name="benign_internal_email_then_external_allowed",
            description="FP13: internal summarize then external summarize",
            metadata={"suite": "benign_fp"},
            steps=[
                _read_step(
                    event_id="fp13_0",
                    step_id="s0",
                    step_seq=0,
                    session_id=sid,
                    file_id=FILE_A,
                    grant=g,
                    output_anchor=_anchor(
                        anchor_id="out_fp13_0",
                        producer_event_id="fp13_0",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                ),
                _sum_step(
                    event_id="fp13_1",
                    step_id="s1",
                    step_seq=1,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_fp13_0",
                            producer_event_id="fp13_0",
                            content_hash="hash:out_fp13_0",
                        )
                    ],
                    purpose="internal_summarization",
                    output_anchor=_anchor(
                        anchor_id="out_fp13_1",
                        producer_event_id="fp13_1",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    expected=DecisionType.ALLOW,
                ),
                _sum_step(
                    event_id="fp13_2",
                    step_id="s2",
                    step_seq=2,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_fp13_1",
                            producer_event_id="fp13_1",
                            content_hash="hash:out_fp13_1",
                        )
                    ],
                    purpose="external_sharing",
                    output_anchor=_anchor(
                        anchor_id="out_fp13_2",
                        producer_event_id="fp13_2",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    expected=DecisionType.ALLOW,
                ),
            ],
            expected_final_decision=DecisionType.ALLOW,
        )
    )

    out.append(
        ControlledTrace(
            name="benign_single_read",
            description="FP14: single read",
            metadata={"suite": "benign_fp"},
            steps=[
                _read_step(
                    event_id="fp14_0",
                    step_id="s0",
                    step_seq=0,
                    session_id=sid,
                    file_id=FILE_A,
                    grant=g,
                    output_anchor=_anchor(
                        anchor_id="out_fp14_0",
                        producer_event_id="fp14_0",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                ),
            ],
            expected_final_decision=DecisionType.ALLOW,
        )
    )

    out.append(
        ControlledTrace(
            name="benign_read_summarize_single",
            description="FP15: read → summarize",
            metadata={"suite": "benign_fp"},
            steps=[
                _read_step(
                    event_id="fp15_0",
                    step_id="s0",
                    step_seq=0,
                    session_id=sid,
                    file_id=FILE_A,
                    grant=g,
                    output_anchor=_anchor(
                        anchor_id="out_fp15_0",
                        producer_event_id="fp15_0",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                ),
                _sum_step(
                    event_id="fp15_1",
                    step_id="s1",
                    step_seq=1,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_fp15_0",
                            producer_event_id="fp15_0",
                            content_hash="hash:out_fp15_0",
                        )
                    ],
                    output_anchor=_anchor(
                        anchor_id="out_fp15_1",
                        producer_event_id="fp15_1",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    expected=DecisionType.ALLOW,
                ),
            ],
            expected_final_decision=DecisionType.ALLOW,
        )
    )

    out.append(
        ControlledTrace(
            name="benign_read_email_summarize_short",
            description="FP16: read → summarize → summarize",
            metadata={"suite": "benign_fp"},
            steps=[
                _read_step(
                    event_id="fp16_0",
                    step_id="s0",
                    step_seq=0,
                    session_id=sid,
                    file_id=FILE_A,
                    grant=g,
                    output_anchor=_anchor(
                        anchor_id="out_fp16_0",
                        producer_event_id="fp16_0",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                ),
                _sum_step(
                    event_id="fp16_1",
                    step_id="s1",
                    step_seq=1,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_fp16_0",
                            producer_event_id="fp16_0",
                            content_hash="hash:out_fp16_0",
                        )
                    ],
                    purpose="internal_summarization",
                    output_anchor=_anchor(
                        anchor_id="out_fp16_1",
                        producer_event_id="fp16_1",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    expected=DecisionType.ALLOW,
                ),
                _sum_step(
                    event_id="fp16_2",
                    step_id="s2",
                    step_seq=2,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_fp16_1",
                            producer_event_id="fp16_1",
                            content_hash="hash:out_fp16_1",
                        )
                    ],
                    purpose="internal_summarization",
                    output_anchor=_anchor(
                        anchor_id="out_fp16_2",
                        producer_event_id="fp16_2",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    expected=DecisionType.ALLOW,
                ),
            ],
            expected_final_decision=DecisionType.ALLOW,
        )
    )

    out.append(
        ControlledTrace(
            name="benign_summarize_twice_after_read",
            description="FP17: read → summarize → summarize (alternate naming)",
            metadata={"suite": "benign_fp"},
            steps=[
                _read_step(
                    event_id="fp17_0",
                    step_id="s0",
                    step_seq=0,
                    session_id=sid,
                    file_id=FILE_A,
                    grant=g,
                    output_anchor=_anchor(
                        anchor_id="out_fp17_0",
                        producer_event_id="fp17_0",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                ),
                _sum_step(
                    event_id="fp17_1",
                    step_id="s1",
                    step_seq=1,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_fp17_0",
                            producer_event_id="fp17_0",
                            content_hash="hash:out_fp17_0",
                        )
                    ],
                    output_anchor=_anchor(
                        anchor_id="out_fp17_1",
                        producer_event_id="fp17_1",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    expected=DecisionType.ALLOW,
                ),
                _sum_step(
                    event_id="fp17_2",
                    step_id="s2",
                    step_seq=2,
                    session_id=sid,
                    resource_ids={FILE_A},
                    grant=g,
                    input_anchors=[
                        InputAnchorRef(
                            anchor_id="out_fp17_1",
                            producer_event_id="fp17_1",
                            content_hash="hash:out_fp17_1",
                        )
                    ],
                    output_anchor=_anchor(
                        anchor_id="out_fp17_2",
                        producer_event_id="fp17_2",
                        resource_ids={FILE_A},
                        session_id=sid,
                    ),
                    expected=DecisionType.ALLOW,
                ),
            ],
            expected_final_decision=DecisionType.ALLOW,
        )
    )

    return out
