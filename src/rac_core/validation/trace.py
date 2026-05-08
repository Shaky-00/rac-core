from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from rac_core.action_semantics import (
    GrantProfileExpander,
    default_grant_templates_yaml_path,
)
from rac_core.action_semantics.registry import ActionSemanticsRegistry
from rac_core.action_semantics.taxonomy import default_semantics_yaml_path
from rac_core.checker import RACPreCommitChecker
from rac_core.models import (
    AuthorizationBasis,
    BasisConditions,
    BasisDelegation,
    BasisResourceScope,
    Decision,
    DecisionType,
    GrantEnvelope,
    TypedAuthorizationEvent,
    VerifiedStructuredOutputAnchor,
    Violation,
)
from rac_core.store.lineage_store import event_requires_tracebench_producer_event_id
from rac_core.verification.output_anchor import output_anchor_integrity_precheck


class TraceStep(BaseModel):
    name: str
    event: TypedAuthorizationEvent
    grant: GrantEnvelope
    output_anchor: VerifiedStructuredOutputAnchor | None = None
    local_allow: bool = True
    persist: bool = True
    expected_decision: DecisionType
    expected_rule: str | None = None
    #: When set, merged into ``event.required_actions`` for this step (v0.6 leaf labels).
    required_actions: list[str] | None = None


class TraceStepResult(BaseModel):
    name: str
    decision: Decision
    expected_decision: DecisionType
    expected_rule: str | None = None
    passed: bool
    observed_rules: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class ControlledTrace(BaseModel):
    name: str
    steps: list[TraceStep]
    description: str | None = None
    expected_final_decision: DecisionType | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    #: v0.6: union of these grant template ids seeds ``initial_basis`` on the first hop.
    grant_templates: list[str] | None = None
    #: Explicit initial basis (overrides ``grant_templates`` when set).
    initial_basis: AuthorizationBasis | None = None
    #: When True, do not inject v0.6 ``initial_basis`` or synthetic ``required_actions``.
    legacy_rac_trace: bool = False


class ControlledTraceResult(BaseModel):
    name: str
    passed: bool
    step_results: list[TraceStepResult] = Field(default_factory=list)
    blocked_at_step: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


def initial_basis_from_grant_templates(
    grant: GrantEnvelope,
    template_ids: list[str],
    *,
    basis_id: str | None = None,
    grant_templates_yaml: Path | None = None,
    grant_templates_root: dict[str, Any] | None = None,
) -> AuthorizationBasis:
    """Build a session initial :class:`AuthorizationBasis` from compiled grant templates (v0.6).

    Shared by ``TraceRunner`` / ``AblationRunner``, deterministic demos
    (:func:`demo_initial_basis_from_grant`), and reproducibility audits.

    Populates ``allowed_action_labels``, ``purpose_scope`` (union with grant),
    ``compiled_grant_conditions``, ``compiled_grant_delegation``, ``source_templates``,
    plus runtime ``conditions`` / ``delegation`` copied from the grant envelope so
    time windows and delegation gates align with the session grant.

    Args:
        grant: Session grant envelope (resource scope, subjects, conditions, …).
        template_ids: Ordered list of grant template ids to union via
            :class:`~rac_core.action_semantics.grant_template.GrantProfileExpander`.
        basis_id: Optional stable id; defaults to ``basis:trace_init:{session_id}``.
        grant_templates_yaml: Optional override for the compiled-templates YAML path
            (defaults to :func:`~rac_core.action_semantics.grant_template.default_grant_templates_yaml_path`).
        grant_templates_root: Optional parsed YAML root (must include a ``templates`` mapping).
            When set, takes precedence over ``grant_templates_yaml`` and the default path.
    """
    reg = ActionSemanticsRegistry.load_from_yaml(default_semantics_yaml_path())
    if grant_templates_root is not None:
        exp = GrantProfileExpander.load_from_root_mapping(grant_templates_root, reg)
    elif grant_templates_yaml is not None:
        exp = GrantProfileExpander.load_from_yaml(grant_templates_yaml, reg)
    else:
        exp = GrantProfileExpander.load_from_yaml(default_grant_templates_yaml_path(), reg)
    profile = exp.expand_templates(template_ids)
    subj = grant.subject.effective_subject or grant.subject.user_id
    runtime_conditions = BasisConditions(
        time_window=grant.conditions.time_window,
        environment=grant.conditions.environment,
        tenant=grant.conditions.tenant,
        runtime_labels=set(grant.conditions.runtime_labels),
    )
    runtime_delegation = BasisDelegation(
        allow_delegation=grant.delegation.allow_delegation,
        allowed_delegatees=set(grant.delegation.allowed_delegatees),
    )
    bid = basis_id if basis_id is not None else f"basis:trace_init:{grant.session_id}"
    b = AuthorizationBasis.from_compiled_grant_profile(
        profile,
        basis_id=bid,
        subjects={subj},
        resource_scope=BasisResourceScope(
            type=grant.resource_scope.type,
            ids=set(grant.resource_scope.allowed_ids),
            labels=set(grant.resource_scope.allowed_labels),
        ),
        legacy_actions=set(grant.allowed_actions),
        runtime_conditions=runtime_conditions,
        runtime_delegation=runtime_delegation,
    )
    return b.model_copy(
        update={"purpose_scope": set(b.purpose_scope) | set(grant.purpose_scope)}
    )


def _heuristic_grant_templates_for_trace(trace: ControlledTrace) -> list[str]:
    """Heuristic template list only (ignores ``trace.grant_templates``).

    **Not** part of production RAC runtime trusted logic: used for controlled traces,
    ablations, and older fixture defaults. Paper runs should set
    :attr:`ControlledTrace.grant_templates` explicitly and record the chosen ids in
    experiment metadata instead of relying on this function alone.
    """
    has_email_allow = any(
        st.event.tool_name == "create_email_draft"
        and st.expected_decision == DecisionType.ALLOW
        for st in trace.steps
    )
    has_email_block_action = any(
        st.event.tool_name == "create_email_draft"
        and st.expected_decision == DecisionType.BLOCK
        and st.expected_rule == "ACTION_ESCALATION"
        for st in trace.steps
    )
    has_email_other = any(st.event.tool_name == "create_email_draft" for st in trace.steps) and (
        not has_email_allow and not has_email_block_action
    )
    if has_email_allow or has_email_other:
        return ["internal_analysis", "external_disclosure_limited"]
    if has_email_block_action:
        return ["internal_analysis"]
    return ["internal_analysis"]


def infer_grant_templates_for_trace(trace: ControlledTrace) -> list[str]:
    """Resolve grant template ids used to build ``initial_basis`` for a controlled trace.

    **Validation / testing helper only** — not deployed as trusted controller policy.
    Prefer setting :attr:`ControlledTrace.grant_templates` explicitly for reproducible
    papers; this helper exists so migrated traces get a sensible default without
    hand-editing every oracle.

    Resolution order:
        1. If ``trace.grant_templates`` is set, return it (authoritative).
        2. Otherwise return :func:`_heuristic_grant_templates_for_trace` (email-aware
           narrow vs broad union). See that function for the exact rules.

    For audit trails, use :func:`describe_trace_grant_inference` or
    :func:`build_trace_inference_report` to record both explicit and heuristic columns.
    """
    if trace.grant_templates is not None:
        return list(trace.grant_templates)
    return _heuristic_grant_templates_for_trace(trace)


def effective_event_for_trace_step(step: TraceStep) -> TypedAuthorizationEvent:
    """Resolve v0.6 ``required_actions`` for checker input (TraceStep override > event > tool default).

    Tool-name defaults exist only for validation/demo fixtures; production events should
    carry manifest-derived ``required_actions``. Used by :func:`describe_trace_grant_inference`
    for reproducibility reporting.
    """
    if step.required_actions is not None:
        return step.event.model_copy(update={"required_actions": list(step.required_actions)})
    ev = step.event
    if ev.required_actions:
        return ev
    if ev.tool_name == "read_file":
        return ev.model_copy(update={"required_actions": ["acquire.read_object"]})
    if ev.tool_name == "summarize_file":
        return ev.model_copy(update={"required_actions": ["transform.summarize"]})
    if ev.tool_name == "create_email_draft":
        return ev.model_copy(update={"required_actions": ["disclose.send_message"]})
    return ev


def describe_trace_grant_inference(trace: ControlledTrace) -> dict[str, Any]:
    """Summarize how a controlled trace resolves grant templates and ``required_actions``.

    Read-only audit helper: does **not** run the checker or mutate traces. Intended for
    experiment reproducibility (record ``final_grant_templates`` and whether the heuristic
    was used alongside oracle metadata).
    """
    explicit_tpl = list(trace.grant_templates) if trace.grant_templates is not None else None
    inferred_tpl = _heuristic_grant_templates_for_trace(trace)
    final_tpl = infer_grant_templates_for_trace(trace)
    whether_inferred = trace.grant_templates is None

    step_rows: list[dict[str, Any]] = []
    n_explicit_ra = 0
    n_inferred_ra = 0
    n_with_ra = 0
    n_event_only_ra = 0
    for st in trace.steps:
        ev0 = st.event
        explicit_step_ra = st.required_actions is not None
        ev_has = bool(ev0.required_actions)
        eff = effective_event_for_trace_step(st)
        eff_ra = list(eff.required_actions)
        if eff_ra:
            n_with_ra += 1
        if explicit_step_ra:
            n_explicit_ra += 1
        if ev_has and not explicit_step_ra:
            n_event_only_ra += 1
        used_inferred = not explicit_step_ra and not ev_has and bool(eff_ra)
        if used_inferred:
            n_inferred_ra += 1
        step_rows.append(
            {
                "step_name": st.name,
                "explicit_required_actions_on_trace_step": explicit_step_ra,
                "event_had_required_actions_before_resolution": ev_has,
                "effective_required_actions": eff_ra,
                "used_inferred_required_actions_from_tool_name": used_inferred,
            }
        )

    return {
        "trace_name": trace.name,
        "explicit_grant_templates": explicit_tpl,
        "inferred_grant_templates_heuristic": inferred_tpl,
        "final_grant_templates": list(final_tpl),
        "whether_grant_templates_inferred": whether_inferred,
        "legacy_rac_trace": trace.legacy_rac_trace,
        "number_of_steps": len(trace.steps),
        "number_of_steps_with_required_actions": n_with_ra,
        "number_of_steps_using_explicit_required_actions_on_trace_step": n_explicit_ra,
        "number_of_steps_using_event_required_actions_only": n_event_only_ra,
        "number_of_steps_using_inferred_required_actions": n_inferred_ra,
        "steps": step_rows,
    }


def build_trace_inference_report(traces: list[ControlledTrace]) -> dict[str, Any]:
    """Build a batch audit dict for many controlled traces (same semantics as :func:`describe_trace_grant_inference`)."""
    rows = [describe_trace_grant_inference(t) for t in traces]
    return {
        "traces": rows,
        "count": len(rows),
        "count_grant_templates_inferred": sum(
            1 for r in rows if r["whether_grant_templates_inferred"]
        ),
    }


class TraceRunner:
    def __init__(
        self,
        checker: RACPreCommitChecker,
        *,
        skip_output_anchor_integrity: bool = False,
    ) -> None:
        self.checker = checker
        self.skip_output_anchor_integrity = skip_output_anchor_integrity

    def run(self, trace: ControlledTrace) -> ControlledTraceResult:
        step_results: list[TraceStepResult] = []
        blocked_at_step: str | None = None
        overall_passed = True

        first_ib: AuthorizationBasis | None = None
        if not trace.legacy_rac_trace:
            if trace.initial_basis is not None:
                first_ib = trace.initial_basis
            else:
                tpl = infer_grant_templates_for_trace(trace)
                if tpl:
                    first_ib = initial_basis_from_grant_templates(trace.steps[0].grant, tpl)

        for i, step in enumerate(trace.steps):
            event = effective_event_for_trace_step(step)
            integ = output_anchor_integrity_precheck(
                step.output_anchor,
                skip_integrity=self.skip_output_anchor_integrity,
            )
            if integ is not None:
                decision = integ
                observed_rules = [v.rule for v in decision.violations]
                step_passed = decision.decision == step.expected_decision
                if step.expected_rule is not None and step.expected_rule not in observed_rules:
                    step_passed = False
                step_results.append(
                    TraceStepResult(
                        name=step.name,
                        decision=decision,
                        expected_decision=step.expected_decision,
                        expected_rule=step.expected_rule,
                        passed=step_passed,
                        observed_rules=observed_rules,
                    )
                )
                if not step_passed:
                    overall_passed = False
                blocked_at_step = step.name
                break

            pred = self.checker.lineage_store.resolve_predecessor(
                event.input_anchors,
                event.advisory_predecessor_hints,
                event.session_id,
                require_producer_event_id_on_inputs=event_requires_tracebench_producer_event_id(
                    event.metadata
                ),
            )
            init = (
                first_ib
                if (first_ib is not None and pred.status == "NO_PREDECESSOR")
                else None
            )
            decision = self.checker.check(
                event=event,
                grant_envelope=step.grant,
                local_allow=step.local_allow,
                output_anchor=step.output_anchor,
                persist=step.persist,
                initial_basis=init,
            )
            if self.skip_output_anchor_integrity:
                decision = decision.model_copy(
                    update={
                        "metadata": {
                            **dict(decision.metadata),
                            "output_anchor_integrity_check": "skipped_by_variant",
                        }
                    }
                )
            observed_rules = [v.rule for v in decision.violations]
            step_passed = decision.decision == step.expected_decision
            if step.expected_rule is not None and step.expected_rule not in observed_rules:
                step_passed = False

            step_results.append(
                TraceStepResult(
                    name=step.name,
                    decision=decision,
                    expected_decision=step.expected_decision,
                    expected_rule=step.expected_rule,
                    passed=step_passed,
                    observed_rules=observed_rules,
                )
            )
            if not step_passed:
                overall_passed = False

            if decision.decision == DecisionType.BLOCK:
                blocked_at_step = step.name
                break

        if trace.expected_final_decision is not None:
            if not step_results:
                overall_passed = False
            elif step_results[-1].decision.decision != trace.expected_final_decision:
                overall_passed = False

        return ControlledTraceResult(
            name=trace.name,
            passed=overall_passed,
            step_results=step_results,
            blocked_at_step=blocked_at_step,
        )


def build_taxonomy_traces() -> list[ControlledTrace]:
    """Return 40+ drift taxonomy controlled traces (see :mod:`rac_core.validation.taxonomy_traces`)."""
    from .taxonomy_traces import build_taxonomy_traces_list

    return build_taxonomy_traces_list()
