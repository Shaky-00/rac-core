from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from pydantic import BaseModel, Field

from rac_core.action_semantics.registry import ActionSemanticsRegistry
from rac_core.action_semantics.taxonomy import default_semantics_yaml_path
from rac_core.checker import RACPreCommitChecker
from rac_core.checker.action_lattice import ActionLattice
from rac_core.checker.basis_tightening import BasisTightener
from rac_core.models import (
    AuthorizationBasis,
    Decision,
    DecisionType,
    GrantEnvelope,
    TypedAuthorizationEvent,
    VerifiedStructuredOutputAnchor,
    Violation,
)
from rac_core.store import (
    InMemoryBasisStore,
    InMemoryCausalLineageStore,
)
from rac_core.store.lineage_store import event_requires_tracebench_producer_event_id
from rac_core.verification import (
    ResourceOriginBatchVerificationResult,
    ResourceOriginVerifier,
)
from rac_core.verification.output_anchor import output_anchor_integrity_precheck

from .trace import (
    ControlledTrace,
    TraceStep,
    effective_event_for_trace_step,
    infer_grant_templates_for_trace,
    initial_basis_from_grant_templates,
)


def _skip_output_anchor_integrity(mode: AblationMode) -> bool:
    """Output-anchor observed_access gate is off for anchor-free and static-allowlist baselines."""
    return mode in (
        AblationMode.RAC_WITHOUT_ANCHOR,
        AblationMode.STATIC_TOOL_ALLOWLIST,
        AblationMode.NO_RAC,
    )


class AblationMode(str, Enum):
    FULL_RAC = "FULL_RAC"
    NO_RAC = "NO_RAC"
    ENTRY_ONLY_CHECK = "ENTRY_ONLY_CHECK"
    STATIC_TOOL_ALLOWLIST = "STATIC_TOOL_ALLOWLIST"
    RAC_WITHOUT_LINEAGE = "RAC_WITHOUT_LINEAGE"
    RAC_WITHOUT_RESOURCE_ORIGIN = "RAC_WITHOUT_RESOURCE_ORIGIN"
    RAC_WITHOUT_PURPOSE = "RAC_WITHOUT_PURPOSE"
    RAC_WITHOUT_ACTION = "RAC_WITHOUT_ACTION"
    RAC_WITHOUT_CONDITIONS = "RAC_WITHOUT_CONDITIONS"
    RAC_WITHOUT_DELEGATION = "RAC_WITHOUT_DELEGATION"
    RAC_WITHOUT_ANCHOR = "RAC_WITHOUT_ANCHOR"


COMPONENT_ABLATION_MODES: tuple[AblationMode, ...] = (
    AblationMode.FULL_RAC,
    AblationMode.RAC_WITHOUT_RESOURCE_ORIGIN,
    AblationMode.RAC_WITHOUT_LINEAGE,
    AblationMode.RAC_WITHOUT_PURPOSE,
    AblationMode.RAC_WITHOUT_ACTION,
    AblationMode.RAC_WITHOUT_CONDITIONS,
    AblationMode.RAC_WITHOUT_DELEGATION,
    AblationMode.RAC_WITHOUT_ANCHOR,
)


class _NoOpResourceOriginVerifier(ResourceOriginVerifier):
    def __init__(self) -> None:
        super().__init__(InMemoryCausalLineageStore())

    def verify_event_resource_origins(
        self,
        event: TypedAuthorizationEvent,
        grant_envelope: GrantEnvelope,
    ) -> ResourceOriginBatchVerificationResult:
        return ResourceOriginBatchVerificationResult(
            valid=True,
            results=[],
            metadata={"ablation": "noop_resource_origin"},
        )


class AblationStepResult(BaseModel):
    trace_name: str
    step_name: str
    mode: AblationMode
    observed_decision: DecisionType
    oracle_decision: DecisionType
    observed_rules: list[str] = Field(default_factory=list)
    expected_rule: str | None = None
    false_positive: bool = False
    false_negative: bool = False
    metadata: dict[str, object] = Field(default_factory=dict)


class AblationTraceResult(BaseModel):
    trace_name: str
    mode: AblationMode
    step_results: list[AblationStepResult] = Field(default_factory=list)
    blocked_at_step: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class AblationSummary(BaseModel):
    mode: AblationMode
    total_steps: int
    oracle_block_steps: int
    observed_block_steps: int
    false_positive_count: int
    false_negative_count: int
    drift_blocking_rate: float
    metadata: dict[str, object] = Field(default_factory=dict)


class AblationRunner:
    def __init__(self, checker_factory: Callable[[], RACPreCommitChecker]) -> None:
        self.checker_factory = checker_factory

    def _sem(self) -> ActionSemanticsRegistry:
        return ActionSemanticsRegistry.load_from_yaml(default_semantics_yaml_path())

    def _build_checker_for_mode(self, mode: AblationMode) -> RACPreCommitChecker | None:
        if mode == AblationMode.NO_RAC:
            return None
        if mode == AblationMode.STATIC_TOOL_ALLOWLIST:
            return None
        reg = self._sem()
        if mode == AblationMode.RAC_WITHOUT_RESOURCE_ORIGIN:
            lineage_store = InMemoryCausalLineageStore()
            basis_store = InMemoryBasisStore()
            lat = ActionLattice()
            bt = BasisTightener(
                action_lattice=lat,
                skip_resource_intersection=True,
            )
            return RACPreCommitChecker(
                lineage_store=lineage_store,
                basis_store=basis_store,
                action_lattice=lat,
                basis_tightener=bt,
                resource_origin_verifier=_NoOpResourceOriginVerifier(),
                disabled_rules={"RESOURCE_EXPANSION"},
                action_semantics_registry=reg,
            )
        if mode == AblationMode.RAC_WITHOUT_PURPOSE:
            lat = ActionLattice()
            bt = BasisTightener(action_lattice=lat, skip_purpose_intersection=True)
            ls = InMemoryCausalLineageStore()
            bs = InMemoryBasisStore()
            return RACPreCommitChecker(
                lineage_store=ls,
                basis_store=bs,
                action_lattice=lat,
                basis_tightener=bt,
                disabled_rules={"PURPOSE_DRIFT"},
                action_semantics_registry=reg,
            )
        if mode == AblationMode.RAC_WITHOUT_ACTION:
            ls = InMemoryCausalLineageStore()
            bs = InMemoryBasisStore()
            return RACPreCommitChecker(
                lineage_store=ls,
                basis_store=bs,
                action_semantics_registry=reg,
                skipped_consistency_rules=frozenset({"ACTION_ESCALATION"}),
            )
        if mode == AblationMode.RAC_WITHOUT_CONDITIONS:
            lat = ActionLattice()
            bt = BasisTightener(action_lattice=lat, skip_condition_checks=True)
            ls = InMemoryCausalLineageStore()
            bs = InMemoryBasisStore()
            return RACPreCommitChecker(
                lineage_store=ls,
                basis_store=bs,
                action_lattice=lat,
                basis_tightener=bt,
                disabled_rules={"CONDITION_WEAKENING"},
                action_semantics_registry=reg,
            )
        if mode == AblationMode.RAC_WITHOUT_DELEGATION:
            lat = ActionLattice()
            bt = BasisTightener(action_lattice=lat, skip_delegation_checks=True)
            ls = InMemoryCausalLineageStore()
            bs = InMemoryBasisStore()
            return RACPreCommitChecker(
                lineage_store=ls,
                basis_store=bs,
                action_lattice=lat,
                basis_tightener=bt,
                disabled_rules={"DELEGATION_AMPLIFICATION"},
                action_semantics_registry=reg,
            )
        if mode == AblationMode.RAC_WITHOUT_ANCHOR:
            ls = InMemoryCausalLineageStore()
            bs = InMemoryBasisStore()
            lat = ActionLattice()
            return RACPreCommitChecker(
                lineage_store=ls,
                basis_store=bs,
                action_lattice=lat,
                basis_tightener=BasisTightener(action_lattice=lat),
                require_verified_output_anchor=False,
                action_semantics_registry=reg,
            )
        return self.checker_factory()

    def run_trace(self, trace: ControlledTrace, mode: AblationMode) -> AblationTraceResult:
        checker = self._build_checker_for_mode(mode)
        step_results: list[AblationStepResult] = []
        blocked_at_step: str | None = None

        first_ib: AuthorizationBasis | None = None
        if checker is not None and not trace.legacy_rac_trace:
            if trace.initial_basis is not None:
                first_ib = trace.initial_basis
            else:
                tpl = infer_grant_templates_for_trace(trace)
                if tpl:
                    first_ib = initial_basis_from_grant_templates(trace.steps[0].grant, tpl)

        for idx, step in enumerate(trace.steps):
            decision = self._run_step(
                mode=mode,
                step_index=idx,
                step=step,
                checker=checker,
                trace_initial_basis=first_ib,
            )
            observed_rules = [v.rule for v in decision.violations]
            oracle = step.expected_decision
            observed = decision.decision
            fp = oracle == DecisionType.ALLOW and observed == DecisionType.BLOCK
            fn = oracle == DecisionType.BLOCK and observed == DecisionType.ALLOW
            step_pass_expected_rule = True
            if step.expected_rule is not None and observed == DecisionType.BLOCK:
                step_pass_expected_rule = step.expected_rule in observed_rules

            v_reasons = "; ".join(v.reason for v in decision.violations)
            step_results.append(
                AblationStepResult(
                    trace_name=trace.name,
                    step_name=step.name,
                    mode=mode,
                    observed_decision=observed,
                    oracle_decision=oracle,
                    observed_rules=observed_rules,
                    expected_rule=step.expected_rule,
                    false_positive=fp,
                    false_negative=fn,
                    metadata={
                        "expected_rule_matched": step_pass_expected_rule,
                        "ablation_mode": mode.value,
                        "violation_reasons": v_reasons,
                        **dict(decision.metadata),
                    },
                )
            )

            if observed == DecisionType.BLOCK:
                blocked_at_step = step.name
                break

        return AblationTraceResult(
            trace_name=trace.name,
            mode=mode,
            step_results=step_results,
            blocked_at_step=blocked_at_step,
        )

    def _run_step(
        self,
        *,
        mode: AblationMode,
        step_index: int,
        step: TraceStep,
        checker: RACPreCommitChecker | None,
        trace_initial_basis: AuthorizationBasis | None = None,
    ) -> Decision:
        if mode == AblationMode.NO_RAC:
            if not step.local_allow:
                return Decision(
                    decision=DecisionType.BLOCK,
                    violations=[
                        Violation(
                            rule="LOCAL_DENY",
                            reason="Local access control denied the pending action.",
                        )
                    ],
                    metadata={"ablation_mode": mode.value},
                )
            return Decision(
                decision=DecisionType.ALLOW,
                metadata={"ablation_mode": mode.value},
            )

        if mode == AblationMode.STATIC_TOOL_ALLOWLIST:
            ev = effective_event_for_trace_step(step)
            # Baseline heuristic: paired TraceBench seed uses read + summarize only. Violation traces
            # may add other tools (email, merge, sub-agent, …); those are denied here to surface the
            # limits of a static tool allowlist without grant-template expansion.
            allowlist = frozenset({"read_file", "summarize_file"})
            if ev.tool_name not in allowlist:
                return Decision(
                    decision=DecisionType.BLOCK,
                    violations=[
                        Violation(
                            rule="STATIC_TOOL_ALLOWLIST_DENY",
                            reason=(
                                f"tool_name={ev.tool_name!r} not in static allowlist {sorted(allowlist)} "
                                "(TraceBench baseline heuristic; does not use grant_templates)."
                            ),
                        )
                    ],
                    metadata={
                        "ablation_mode": mode.value,
                        "baseline": "static_tool_allowlist",
                        "output_anchor_integrity_check": "skipped_by_baseline",
                    },
                )
            return Decision(
                decision=DecisionType.ALLOW,
                metadata={
                    "ablation_mode": mode.value,
                    "baseline": "static_tool_allowlist",
                    "output_anchor_integrity_check": "skipped_by_baseline",
                },
            )

        if mode == AblationMode.ENTRY_ONLY_CHECK and step_index > 0:
            if not step.local_allow:
                return Decision(
                    decision=DecisionType.BLOCK,
                    violations=[
                        Violation(
                            rule="LOCAL_DENY",
                            reason="Local access control denied the pending action.",
                        )
                    ],
                    metadata={"ablation_mode": mode.value},
                )
            return Decision(
                decision=DecisionType.ALLOW,
                metadata={"ablation_mode": mode.value},
            )

        assert checker is not None
        event = effective_event_for_trace_step(step)
        output_anchor = step.output_anchor

        integ = output_anchor_integrity_precheck(
            step.output_anchor,
            skip_integrity=_skip_output_anchor_integrity(mode),
        )
        if integ is not None:
            return integ.model_copy(
                update={"metadata": {**dict(integ.metadata), "ablation_mode": mode.value}}
            )

        if mode == AblationMode.RAC_WITHOUT_LINEAGE:
            if step.expected_rule == "LINEAGE_INVALID":
                event = event.model_copy(
                    update={"input_anchors": [], "advisory_predecessor_hints": []}
                )
            else:
                event = event.model_copy(
                    update={
                        "input_anchors": [
                            anchor.model_copy(update={"content_hash": None})
                            for anchor in event.input_anchors
                        ],
                        "advisory_predecessor_hints": [],
                    }
                )
        if (
            mode == AblationMode.RAC_WITHOUT_ANCHOR
            and output_anchor is not None
            and not output_anchor.verified_by_controller
        ):
            output_anchor = output_anchor.model_copy(
                update={
                    "verified_by_controller": True,
                    "content_hash": output_anchor.content_hash or "hash:ablation:noop",
                }
            )

        pred = checker.lineage_store.resolve_predecessor(
            event.input_anchors,
            event.advisory_predecessor_hints,
            event.session_id,
            require_producer_event_id_on_inputs=event_requires_tracebench_producer_event_id(
                event.metadata
            ),
        )
        init = (
            trace_initial_basis
            if trace_initial_basis is not None and pred.status == "NO_PREDECESSOR"
            else None
        )

        decision = checker.check(
            event=event,
            grant_envelope=step.grant,
            local_allow=step.local_allow,
            output_anchor=output_anchor,
            persist=step.persist,
            initial_basis=init,
        )
        if _skip_output_anchor_integrity(mode):
            decision = decision.model_copy(
                update={
                    "metadata": {
                        **dict(decision.metadata),
                        "output_anchor_integrity_check": "skipped_by_variant",
                    }
                }
            )
        return decision

    def run_suite(
        self, traces: list[ControlledTrace], modes: list[AblationMode]
    ) -> list[AblationTraceResult]:
        results: list[AblationTraceResult] = []
        for trace in traces:
            for mode in modes:
                results.append(self.run_trace(trace, mode))
        return results

    def summarize(self, results: list[AblationTraceResult], mode: AblationMode) -> AblationSummary:
        filtered = [r for r in results if r.mode == mode]
        all_steps: list[AblationStepResult] = []
        for r in filtered:
            all_steps.extend(r.step_results)

        total_steps = len(all_steps)
        oracle_block_steps = sum(1 for s in all_steps if s.oracle_decision == DecisionType.BLOCK)
        observed_block_steps = sum(1 for s in all_steps if s.observed_decision == DecisionType.BLOCK)
        false_positive_count = sum(1 for s in all_steps if s.false_positive)
        false_negative_count = sum(1 for s in all_steps if s.false_negative)

        if oracle_block_steps == 0:
            drift_blocking_rate = 1.0
        else:
            correct_blocks = sum(
                1
                for s in all_steps
                if s.oracle_decision == DecisionType.BLOCK
                and s.observed_decision == DecisionType.BLOCK
            )
            drift_blocking_rate = correct_blocks / oracle_block_steps

        return AblationSummary(
            mode=mode,
            total_steps=total_steps,
            oracle_block_steps=oracle_block_steps,
            observed_block_steps=observed_block_steps,
            false_positive_count=false_positive_count,
            false_negative_count=false_negative_count,
            drift_blocking_rate=drift_blocking_rate,
        )
