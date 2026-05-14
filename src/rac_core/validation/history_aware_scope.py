"""History-aware resource-scope baselines for TraceBench / ablation (not part of core RAC semantics)."""

from __future__ import annotations

from dataclasses import dataclass, field

from rac_core.models import Decision, DecisionType, Violation
from rac_core.validation.trace import ControlledTrace, TraceStep, effective_event_for_trace_step

# Shared with TraceBench static-tool baseline; keep single source of truth for tool names.
TRACEBENCH_STATIC_TOOL_ALLOWLIST = frozenset({"read_file", "summarize_file"})


@dataclass
class HistoryAwareState:
    """Per-trace state: grant-bound ids plus resources accepted on prior ALLOW steps."""

    grant_resource_ids: frozenset[str]
    accepted_resource_ids: set[str] = field(default_factory=set)


def grant_bound_resource_ids_for_trace(trace: ControlledTrace) -> frozenset[str]:
    """Union session grant resource scope and optional initial-basis resource ids."""
    if not trace.steps:
        return frozenset()
    g = trace.steps[0].grant
    ids: set[str] = set(g.resource_scope.allowed_ids)
    if trace.initial_basis is not None:
        ids |= set(trace.initial_basis.resource_scope.ids)
    return frozenset(ids)


def resource_ids_from_output_anchor(anchor) -> set[str]:
    if anchor is None:
        return set()
    return set(anchor.resource_ids)


def extract_current_resource_ids(step: TraceStep) -> set[str]:
    """Resource ids from the effective authorization event for this step."""
    ev = effective_event_for_trace_step(step)
    return set(ev.resource_scope.ids)


def local_deny_decision_if_blocked(step: TraceStep, *, ablation_mode_value: str) -> Decision | None:
    if step.local_allow:
        return None
    return Decision(
        decision=DecisionType.BLOCK,
        violations=[
            Violation(
                rule="LOCAL_DENY",
                reason="Local access control denied the pending action.",
            )
        ],
        metadata={"ablation_mode": ablation_mode_value},
    )


def tracebench_static_tool_allowlist_decision_if_denied(
    step: TraceStep,
    *,
    ablation_mode_value: str,
) -> Decision | None:
    """Same rule body as ``STATIC_TOOL_ALLOWLIST`` in ablation replay; ``None`` means passed."""
    ev = effective_event_for_trace_step(step)
    if ev.tool_name in TRACEBENCH_STATIC_TOOL_ALLOWLIST:
        return None
    return Decision(
        decision=DecisionType.BLOCK,
        violations=[
            Violation(
                rule="STATIC_TOOL_ALLOWLIST_DENY",
                reason=(
                    f"tool_name={ev.tool_name!r} not in static allowlist "
                    f"{sorted(TRACEBENCH_STATIC_TOOL_ALLOWLIST)} "
                    "(TraceBench baseline heuristic; does not use grant_templates)."
                ),
            )
        ],
        metadata={
            "ablation_mode": ablation_mode_value,
            "baseline": "static_tool_allowlist",
            "output_anchor_integrity_check": "skipped_by_baseline",
        },
    )


def history_scope_resource_decision_if_violation(
    step: TraceStep,
    state: HistoryAwareState,
    *,
    ablation_mode_value: str,
    deny_rule: str,
    baseline_key: str,
) -> Decision | None:
    """If any current resource id is outside grant ∪ accepted history, return BLOCK; else ``None``."""
    current_ids = extract_current_resource_ids(step)
    allowed = set(state.grant_resource_ids) | state.accepted_resource_ids
    forbidden = current_ids - allowed
    if not forbidden:
        return None
    return Decision(
        decision=DecisionType.BLOCK,
        violations=[
            Violation(
                rule=deny_rule,
                reason=(
                    "Resource(s) not in grant scope or prior accepted steps: "
                    f"{sorted(forbidden)}"
                ),
            )
        ],
        metadata={
            "ablation_mode": ablation_mode_value,
            "baseline": baseline_key,
            "output_anchor_integrity_check": "skipped_by_baseline",
        },
    )


def update_history_aware_state_on_allow(step: TraceStep, state: HistoryAwareState) -> None:
    """Append resources observed on an ALLOW step (event scope + output anchor)."""
    state.accepted_resource_ids |= extract_current_resource_ids(step)
    state.accepted_resource_ids |= resource_ids_from_output_anchor(step.output_anchor)


def history_aware_scope_step(step: TraceStep, state: HistoryAwareState) -> Decision:
    """Single-step HISTORY_AWARE_SCOPE; mutates ``state`` only on ALLOW."""
    ld = local_deny_decision_if_blocked(step, ablation_mode_value="HISTORY_AWARE_SCOPE")
    if ld is not None:
        return ld

    scope_block = history_scope_resource_decision_if_violation(
        step,
        state,
        ablation_mode_value="HISTORY_AWARE_SCOPE",
        deny_rule="HISTORY_AWARE_SCOPE_DENY",
        baseline_key="history_aware_scope",
    )
    if scope_block is not None:
        return scope_block

    update_history_aware_state_on_allow(step, state)
    return Decision(
        decision=DecisionType.ALLOW,
        metadata={
            "ablation_mode": "HISTORY_AWARE_SCOPE",
            "baseline": "history_aware_scope",
            "output_anchor_integrity_check": "skipped_by_baseline",
        },
    )


def static_history_aware_step(step: TraceStep, state: HistoryAwareState) -> Decision:
    """STATIC_TOOL_ALLOWLIST then HISTORY_AWARE_SCOPE resource rules; mutates ``state`` only on ALLOW."""
    ld = local_deny_decision_if_blocked(step, ablation_mode_value="STATIC_HISTORY_AWARE")
    if ld is not None:
        return ld

    st = tracebench_static_tool_allowlist_decision_if_denied(
        step, ablation_mode_value="STATIC_HISTORY_AWARE"
    )
    if st is not None:
        return st

    scope_block = history_scope_resource_decision_if_violation(
        step,
        state,
        ablation_mode_value="STATIC_HISTORY_AWARE",
        deny_rule="STATIC_HISTORY_SCOPE_DENY",
        baseline_key="static_history_aware",
    )
    if scope_block is not None:
        return scope_block

    update_history_aware_state_on_allow(step, state)
    return Decision(
        decision=DecisionType.ALLOW,
        metadata={
            "ablation_mode": "STATIC_HISTORY_AWARE",
            "baseline": "static_history_aware",
            "output_anchor_integrity_check": "skipped_by_baseline",
        },
    )
