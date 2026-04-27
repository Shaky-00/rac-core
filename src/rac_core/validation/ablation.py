from __future__ import annotations

from collections.abc import Callable
from enum import Enum

from pydantic import BaseModel, Field

from rac_core.checker import RACPreCommitChecker
from rac_core.checker.action_lattice import ActionLattice
from rac_core.checker.basis_tightening import BasisTightener
from rac_core.models import (
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
from rac_core.verification import (
    ResourceOriginBatchVerificationResult,
    ResourceOriginVerifier,
)

from .trace import ControlledTrace, TraceStep


class AblationMode(str, Enum):
    FULL_RAC = "FULL_RAC"
    NO_RAC = "NO_RAC"
    ENTRY_ONLY_CHECK = "ENTRY_ONLY_CHECK"
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

    def _build_checker_for_mode(self, mode: AblationMode) -> RACPreCommitChecker | None:
        if mode == AblationMode.NO_RAC:
            return None
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
                skipped_consistency_rules=frozenset({"RESOURCE_EXPANSION"}),
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
                skipped_consistency_rules=frozenset({"PURPOSE_DRIFT"}),
            )
        if mode == AblationMode.RAC_WITHOUT_ACTION:
            lat = ActionLattice()
            bt = BasisTightener(action_lattice=lat, skip_action_lattice=True)
            ls = InMemoryCausalLineageStore()
            bs = InMemoryBasisStore()
            return RACPreCommitChecker(
                lineage_store=ls,
                basis_store=bs,
                action_lattice=lat,
                basis_tightener=bt,
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
                skipped_consistency_rules=frozenset({"CONDITION_WEAKENING"}),
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
                skipped_consistency_rules=frozenset({"DELEGATION_AMPLIFICATION"}),
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
            )
        return self.checker_factory()

    def run_trace(self, trace: ControlledTrace, mode: AblationMode) -> AblationTraceResult:
        checker = self._build_checker_for_mode(mode)
        step_results: list[AblationStepResult] = []
        blocked_at_step: str | None = None

        for idx, step in enumerate(trace.steps):
            decision = self._run_step(
                mode=mode,
                step_index=idx,
                step=step,
                checker=checker,
            )
            observed_rules = [v.rule for v in decision.violations]
            oracle = step.expected_decision
            observed = decision.decision
            fp = oracle == DecisionType.ALLOW and observed == DecisionType.BLOCK
            fn = oracle == DecisionType.BLOCK and observed == DecisionType.ALLOW
            step_pass_expected_rule = True
            if step.expected_rule is not None and observed == DecisionType.BLOCK:
                step_pass_expected_rule = step.expected_rule in observed_rules

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
        event = step.event
        output_anchor = step.output_anchor
        if mode == AblationMode.RAC_WITHOUT_LINEAGE:
            event = step.event.model_copy(
                update={"input_anchors": [], "advisory_predecessor_hints": []}
            )
        if (
            mode == AblationMode.RAC_WITHOUT_ANCHOR
            and output_anchor is not None
            and not output_anchor.verified_by_controller
        ):
            output_anchor = output_anchor.model_copy(update={"verified_by_controller": True})

        return checker.check(
            event=event,
            grant_envelope=step.grant,
            local_allow=step.local_allow,
            output_anchor=output_anchor,
            persist=step.persist,
        )

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
