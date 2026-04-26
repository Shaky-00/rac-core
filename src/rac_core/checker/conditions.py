from __future__ import annotations

from pydantic import BaseModel, Field

from rac_core.models import BasisConditions, TypedEventConditions


class ConditionCheckResult(BaseModel):
    valid: bool
    rule: str | None = None
    reason: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class ConditionTightener:
    def check_event_conditions(
        self,
        event_conditions: TypedEventConditions,
        basis_conditions: BasisConditions,
    ) -> ConditionCheckResult:
        tw = basis_conditions.time_window
        if tw is not None:
            if event_conditions.time is None:
                return ConditionCheckResult(
                    valid=False,
                    rule="CONDITION_WEAKENING",
                    reason="event time missing while basis has time_window",
                )
            if tw.start is not None and event_conditions.time < tw.start:
                return ConditionCheckResult(
                    valid=False,
                    rule="CONDITION_WEAKENING",
                    reason="event time before basis time_window start",
                )
            if tw.end is not None and event_conditions.time > tw.end:
                return ConditionCheckResult(
                    valid=False,
                    rule="CONDITION_WEAKENING",
                    reason="event time after basis time_window end",
                )

        if basis_conditions.environment is not None:
            if event_conditions.environment != basis_conditions.environment:
                return ConditionCheckResult(
                    valid=False,
                    rule="CONDITION_WEAKENING",
                    reason="environment mismatch",
                )

        if basis_conditions.tenant is not None:
            if event_conditions.tenant != basis_conditions.tenant:
                return ConditionCheckResult(
                    valid=False,
                    rule="CONDITION_WEAKENING",
                    reason="tenant mismatch",
                )

        basis_labels = set(basis_conditions.runtime_labels)
        event_labels = set(event_conditions.runtime_labels)
        if basis_labels:
            if not event_labels:
                return ConditionCheckResult(
                    valid=False,
                    rule="CONDITION_WEAKENING",
                    reason="runtime_labels missing while basis has labels",
                )
            if not event_labels.issubset(basis_labels):
                return ConditionCheckResult(
                    valid=False,
                    rule="CONDITION_WEAKENING",
                    reason="runtime_labels expanded beyond inherited basis",
                )

        return ConditionCheckResult(valid=True)

    def tighten_conditions(
        self,
        event_conditions: TypedEventConditions,
        basis_conditions: BasisConditions,
    ) -> BasisConditions:
        check = self.check_event_conditions(event_conditions, basis_conditions)
        if not check.valid:
            raise ValueError(check.reason or "condition check failed")

        runtime_labels: set[str]
        if basis_conditions.runtime_labels and event_conditions.runtime_labels:
            runtime_labels = set(event_conditions.runtime_labels)
        else:
            runtime_labels = set(basis_conditions.runtime_labels)

        return BasisConditions(
            time_window=basis_conditions.time_window,
            environment=event_conditions.environment or basis_conditions.environment,
            tenant=event_conditions.tenant or basis_conditions.tenant,
            runtime_labels=runtime_labels,
        )
