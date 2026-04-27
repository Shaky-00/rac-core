from __future__ import annotations

from pydantic import BaseModel, Field

from rac_core.models import AuthorizationBasis, BasisResourceScope, TypedAuthorizationEvent

from .action_lattice import ActionLattice
from .conditions import ConditionTightener


class BasisTighteningResult(BaseModel):
    valid: bool
    basis: AuthorizationBasis | None = None
    rule: str | None = None
    reason: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class BasisTightener:
    def __init__(
        self,
        action_lattice: ActionLattice | None = None,
        condition_tightener: ConditionTightener | None = None,
        *,
        skip_purpose_intersection: bool = False,
        skip_action_lattice: bool = False,
        skip_delegation_checks: bool = False,
        skip_condition_checks: bool = False,
        skip_resource_intersection: bool = False,
    ) -> None:
        self.action_lattice = action_lattice or ActionLattice()
        self.condition_tightener = condition_tightener or ConditionTightener()
        self.skip_purpose_intersection = skip_purpose_intersection
        self.skip_action_lattice = skip_action_lattice
        self.skip_delegation_checks = skip_delegation_checks
        self.skip_condition_checks = skip_condition_checks
        self.skip_resource_intersection = skip_resource_intersection

    def tighten_basis(
        self,
        inherited_basis: AuthorizationBasis,
        event: TypedAuthorizationEvent,
        new_basis_id: str,
    ) -> BasisTighteningResult:
        if (
            inherited_basis.resource_scope.type
            and event.resource_scope.type != inherited_basis.resource_scope.type
        ):
            return BasisTighteningResult(
                valid=False,
                rule="RESOURCE_EXPANSION",
                reason="event resource type does not match inherited basis resource type",
            )

        if self.skip_resource_intersection:
            new_resource_ids = set(inherited_basis.resource_scope.ids) | set(
                event.resource_scope.ids
            )
        else:
            new_resource_ids = set(inherited_basis.resource_scope.ids).intersection(
                event.resource_scope.ids
            )
        if not new_resource_ids:
            return BasisTighteningResult(
                valid=False,
                rule="BASIS_EMPTY_AFTER_UPDATE",
                reason="resource scope becomes empty after tightening",
            )

        if self.skip_purpose_intersection:
            new_purpose_scope = set(inherited_basis.purpose_scope) | {event.purpose}
        else:
            new_purpose_scope = set(inherited_basis.purpose_scope).intersection({event.purpose})
        if not new_purpose_scope:
            return BasisTighteningResult(
                valid=False,
                rule="BASIS_EMPTY_AFTER_UPDATE",
                reason="purpose scope becomes empty after tightening",
            )

        event_subject = event.subject.effective_subject or event.subject.user_id
        if inherited_basis.subjects and event_subject not in inherited_basis.subjects:
            return BasisTighteningResult(
                valid=False,
                rule="SUBJECT_INCONSISTENCY",
                reason="event subject not covered by inherited basis",
            )
        new_subjects = {event_subject}

        if not self.skip_action_lattice:
            if not self.action_lattice.is_action_allowed(event.action, inherited_basis.actions):
                return BasisTighteningResult(
                    valid=False,
                    rule="ACTION_ESCALATION",
                    reason="event action is not allowed by inherited actions",
                )
            new_actions = set(inherited_basis.actions).intersection(
                self.action_lattice.downstream_allowed_actions(event.action)
            )
        else:
            new_actions = set(inherited_basis.actions)
        if not new_actions:
            return BasisTighteningResult(
                valid=False,
                rule="BASIS_EMPTY_AFTER_UPDATE",
                reason="action scope becomes empty after tightening",
            )

        if self.skip_condition_checks:
            new_conditions = inherited_basis.conditions
        else:
            try:
                new_conditions = self.condition_tightener.tighten_conditions(
                    event.conditions, inherited_basis.conditions
                )
            except ValueError as exc:
                return BasisTighteningResult(
                    valid=False,
                    rule="CONDITION_WEAKENING",
                    reason=str(exc),
                )

        if not self.skip_delegation_checks:
            if (
                not inherited_basis.delegation.allow_delegation
                and event.delegation.delegated
            ):
                return BasisTighteningResult(
                    valid=False,
                    rule="DELEGATION_AMPLIFICATION",
                    reason="delegation introduced while inherited basis disallows delegation",
                )
            if (
                event.delegation.delegated
                and inherited_basis.delegation.allowed_delegatees
            ):
                if event.delegation.delegatee not in inherited_basis.delegation.allowed_delegatees:
                    return BasisTighteningResult(
                        valid=False,
                        rule="DELEGATION_AMPLIFICATION",
                        reason="delegatee not in inherited allowed_delegatees",
                    )

        new_origin_anchors = set(inherited_basis.origin_anchors).union(
            {anchor.anchor_id for anchor in event.input_anchors}
        )

        new_basis = AuthorizationBasis(
            basis_id=new_basis_id,
            subjects=new_subjects,
            actions=new_actions,
            resource_scope=BasisResourceScope(
                type=inherited_basis.resource_scope.type,
                ids=new_resource_ids,
                labels=set(inherited_basis.resource_scope.labels),
            ),
            purpose_scope=new_purpose_scope,
            delegation=inherited_basis.delegation,
            conditions=new_conditions,
            origin_anchors=new_origin_anchors,
            lineage_hash=inherited_basis.lineage_hash,
            metadata={
                **dict(inherited_basis.metadata),
                "tightened_from": inherited_basis.basis_id,
                "event_id": event.event_id,
            },
        )
        return BasisTighteningResult(valid=True, basis=new_basis)
