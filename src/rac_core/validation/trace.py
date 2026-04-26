from __future__ import annotations

from pydantic import BaseModel, Field

from rac_core.checker import RACPreCommitChecker
from rac_core.models import (
    Decision,
    DecisionType,
    GrantEnvelope,
    TypedAuthorizationEvent,
    VerifiedStructuredOutputAnchor,
)


class TraceStep(BaseModel):
    name: str
    event: TypedAuthorizationEvent
    grant: GrantEnvelope
    output_anchor: VerifiedStructuredOutputAnchor | None = None
    local_allow: bool = True
    persist: bool = True
    expected_decision: DecisionType
    expected_rule: str | None = None


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


class ControlledTraceResult(BaseModel):
    name: str
    passed: bool
    step_results: list[TraceStepResult] = Field(default_factory=list)
    blocked_at_step: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class TraceRunner:
    def __init__(self, checker: RACPreCommitChecker) -> None:
        self.checker = checker

    def run(self, trace: ControlledTrace) -> ControlledTraceResult:
        step_results: list[TraceStepResult] = []
        blocked_at_step: str | None = None
        overall_passed = True

        for step in trace.steps:
            decision = self.checker.check(
                event=step.event,
                grant_envelope=step.grant,
                local_allow=step.local_allow,
                output_anchor=step.output_anchor,
                persist=step.persist,
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
