"""
Optional helper: sample Markdown / CSV / LaTeX tables for validation layout checks.

Run from repository root:
  python3 scripts/paper_optional/generate_validation_tables.py
"""
from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

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
    ControlledTraceResult,
    TraceRunner,
    TraceStep,
    build_ablation_matrix_rows,
    build_ablation_summary_rows,
    build_trace_validation_rows,
    to_csv,
    to_json,
    to_latex_tabular,
    to_markdown_table,
)


def trace_labels_table1() -> dict[str, tuple[str, str]]:
    return {
        "benign-read-summarize": ("Benign", "read → summarize"),
        "action-escalation": ("Action escalation", "read → external"),
        "resource-expansion": ("Resource expansion", "file_A → file_B"),
        "purpose-drift": ("Purpose drift", "internal → external"),
        "delegation-amplification": ("Delegation", "non-del. → del."),
        "condition-weakening": ("Condition", "trusted → external"),
        "forged-predecessor": ("Forged predecessor", "out_read → out_fake"),
        "advisory-conflict-runtime-wins": ("Advisory conflict", "hint conflict"),
        "multi-predecessor-unsupported": ("Multi-pred.", "out_A + out_B"),
    }


def trace_labels_ablation_short() -> dict[str, str]:
    return {
        "benign-read-summarize": "Benign",
        "action-escalation": "Action escalation",
        "forged-predecessor": "Forged predecessor",
        "resource-expansion": "Resource expansion",
    }


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


def build_checker() -> RACPreCommitChecker:
    return RACPreCommitChecker(
        lineage_store=InMemoryCausalLineageStore(),
        basis_store=InMemoryBasisStore(),
    )


def build_checker_factory() -> Callable[[], RACPreCommitChecker]:
    def _factory() -> RACPreCommitChecker:
        return build_checker()

    return _factory


def build_controlled_traces() -> list[ControlledTrace]:
    g = build_grant()
    traces: list[ControlledTrace] = []

    traces.append(
        ControlledTrace(
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
                    grant=g,
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
                    grant=g,
                    expected_decision=DecisionType.ALLOW,
                ),
            ],
            expected_final_decision=DecisionType.ALLOW,
        )
    )

    traces.append(
        ControlledTrace(
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
                    grant=g,
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
                    grant=g,
                    expected_decision=DecisionType.BLOCK,
                    expected_rule="ACTION_ESCALATION",
                ),
            ],
            expected_final_decision=DecisionType.BLOCK,
        )
    )

    traces.append(
        ControlledTrace(
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
                    grant=g,
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
                    grant=g,
                    expected_decision=DecisionType.BLOCK,
                    expected_rule="RESOURCE_ORIGIN_UNVERIFIABLE",
                ),
            ],
            expected_final_decision=DecisionType.BLOCK,
        )
    )

    traces.append(
        ControlledTrace(
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
                    grant=g,
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
                    grant=g,
                    expected_decision=DecisionType.BLOCK,
                    expected_rule="PURPOSE_DRIFT",
                ),
            ],
            expected_final_decision=DecisionType.BLOCK,
        )
    )

    g_nd = build_grant(allow_delegation=False)
    traces.append(
        ControlledTrace(
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
                    grant=g_nd,
                    expected_decision=DecisionType.BLOCK,
                    expected_rule="DELEGATION_AMPLIFICATION",
                )
            ],
            expected_final_decision=DecisionType.BLOCK,
        )
    )

    traces.append(
        ControlledTrace(
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
                    grant=g,
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
                    grant=g,
                    expected_decision=DecisionType.BLOCK,
                    expected_rule="CONDITION_WEAKENING",
                ),
            ],
            expected_final_decision=DecisionType.BLOCK,
        )
    )

    traces.append(
        ControlledTrace(
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
                    grant=g,
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
                    grant=g,
                    expected_decision=DecisionType.BLOCK,
                    expected_rule="LINEAGE_INVALID",
                ),
            ],
            expected_final_decision=DecisionType.BLOCK,
        )
    )

    traces.append(
        ControlledTrace(
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
                    grant=g,
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
                    grant=g,
                    expected_decision=DecisionType.ALLOW,
                ),
            ],
            expected_final_decision=DecisionType.ALLOW,
        )
    )

    g_multi = build_grant(
        allowed_ids={"file_A", "file_B"},
        allowed_actions={"read", "summarize"},
    )
    traces.append(
        ControlledTrace(
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
                    grant=g_multi,
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
                    grant=g_multi,
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
                        input_anchors=[
                            InputAnchorRef(anchor_id="out_A"),
                            InputAnchorRef(anchor_id="out_B"),
                        ],
                    ),
                    grant=g_multi,
                    expected_decision=DecisionType.BLOCK,
                    expected_rule="MULTI_PREDECESSOR_UNSUPPORTED",
                ),
            ],
            expected_final_decision=DecisionType.BLOCK,
        )
    )

    return traces


def build_ablation_traces() -> list[ControlledTrace]:
    by_name = {t.name: t for t in build_controlled_traces()}
    order = (
        "benign-read-summarize",
        "action-escalation",
        "forged-predecessor",
        "resource-expansion",
    )
    return [by_name[n] for n in order]


def run_controlled_trace_validation() -> list[ControlledTraceResult]:
    results: list[ControlledTraceResult] = []
    for trace in build_controlled_traces():
        checker = build_checker()
        results.append(TraceRunner(checker).run(trace))
    return results


ABLATION_MODES: list[AblationMode] = [
    AblationMode.NO_RAC,
    AblationMode.ENTRY_ONLY_CHECK,
    AblationMode.RAC_WITHOUT_LINEAGE,
    AblationMode.RAC_WITHOUT_RESOURCE_ORIGIN,
    AblationMode.FULL_RAC,
]


def generate_validation_tables(
    output_dir: str | Path,
    *,
    print_paths: bool = True,
) -> list[Path]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    labels_t1 = trace_labels_table1()
    controlled_results = run_controlled_trace_validation()
    t1_rows = build_trace_validation_rows(controlled_results, trace_labels=labels_t1)

    ablation_runner = AblationRunner(checker_factory=build_checker_factory())
    ab_traces = build_ablation_traces()
    ab_results = ablation_runner.run_suite(ab_traces, ABLATION_MODES)
    trace_order = [t.name for t in ab_traces]
    matrix_rows = build_ablation_matrix_rows(
        ab_results,
        trace_order=trace_order,
        trace_labels=trace_labels_ablation_short(),
    )

    summaries = []
    for mode in ABLATION_MODES:
        summaries.append(ablation_runner.summarize(ab_results, mode))
    summary_rows = build_ablation_summary_rows(summaries)

    written: list[Path] = []

    def write_triplet(base: str, rows: list) -> None:
        for ext, fn in (
            ("md", to_markdown_table),
            ("csv", to_csv),
            ("tex", lambda r: to_latex_tabular(r)),
        ):
            p = out / f"{base}.{ext}"
            p.write_text(fn(rows), encoding="utf-8")
            written.append(p)

    write_triplet("controlled_trace_validation", t1_rows)
    write_triplet("ablation_matrix", matrix_rows)
    write_triplet("ablation_summary", summary_rows)

    json_path = out / "ablation_summary.json"
    json_path.write_text(to_json(summary_rows), encoding="utf-8")
    written.append(json_path)

    if print_paths:
        print("Generated validation tables:")
        for p in written:
            try:
                rel = p.relative_to(ROOT)
                print(f"- {rel.as_posix()}")
            except ValueError:
                print(f"- {p}")

    return written


def main() -> None:
    default_out = ROOT / "artifacts" / "generated" / "tables"
    generate_validation_tables(default_out, print_paths=True)


if __name__ == "__main__":
    main()
