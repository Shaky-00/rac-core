from __future__ import annotations

from rac_core.models import (
    AuthorizationBasis,
    CausalLineageRecord,
    Decision,
    DecisionType,
    GrantEnvelope,
    TypedAuthorizationEvent,
    VerifiedStructuredOutputAnchor,
    Violation,
)
from rac_core.store import InMemoryBasisStore, InMemoryCausalLineageStore
from rac_core.verification import ResourceOriginVerifier

from .action_lattice import ActionLattice
from .basis_tightening import BasisTightener
from .conditions import ConditionTightener


class RACPreCommitChecker:
    def __init__(
        self,
        lineage_store: InMemoryCausalLineageStore,
        basis_store: InMemoryBasisStore,
        resource_origin_verifier: ResourceOriginVerifier | None = None,
        action_lattice: ActionLattice | None = None,
        condition_tightener: ConditionTightener | None = None,
        basis_tightener: BasisTightener | None = None,
    ) -> None:
        self.lineage_store = lineage_store
        self.basis_store = basis_store
        self.resource_origin_verifier = resource_origin_verifier or ResourceOriginVerifier(
            lineage_store
        )
        self.action_lattice = action_lattice or ActionLattice()
        self.condition_tightener = condition_tightener or ConditionTightener()
        self.basis_tightener = basis_tightener or BasisTightener(
            action_lattice=self.action_lattice,
            condition_tightener=self.condition_tightener,
        )

    def check(
        self,
        event: TypedAuthorizationEvent,
        grant_envelope: GrantEnvelope,
        *,
        local_allow: bool = True,
        output_anchor: VerifiedStructuredOutputAnchor | None = None,
        persist: bool = True,
    ) -> Decision:
        if not local_allow:
            return Decision(
                decision=DecisionType.BLOCK,
                violations=[
                    Violation(
                        rule="LOCAL_DENY",
                        reason="Local access control denied the pending action.",
                    )
                ],
            )

        if event.session_id != grant_envelope.session_id:
            return self._block("SESSION_MISMATCH", "event session_id does not match grant")

        predecessor = self.lineage_store.resolve_predecessor(
            event.input_anchors,
            event.advisory_predecessor_hints,
            event.session_id,
        )
        if not predecessor.valid:
            if predecessor.multi_predecessor:
                return self._block(
                    "MULTI_PREDECESSOR_UNSUPPORTED",
                    predecessor.reason or "multi predecessor unsupported",
                )
            return self._block("LINEAGE_INVALID", predecessor.reason or predecessor.status)

        resource_origin = self.resource_origin_verifier.verify_event_resource_origins(
            event, grant_envelope
        )
        if not resource_origin.valid:
            return Decision(
                decision=DecisionType.BLOCK,
                violations=[
                    Violation(
                        rule="RESOURCE_ORIGIN_UNVERIFIABLE",
                        reason=resource_origin.reason
                        or "resource origin verification failed",
                        metadata={"failed_resource_ids": sorted(resource_origin.failed_resource_ids)},
                    )
                ],
            )

        if predecessor.status == "VALID":
            inherited_basis = self.basis_store.load_finalized_basis(
                event.session_id, predecessor.predecessor_step_id or ""
            )
            if inherited_basis is None:
                return self._block(
                    "BASIS_NOT_FOUND",
                    "Unable to load predecessor finalized basis from BasisStore.",
                )
        else:
            inherited_basis = AuthorizationBasis.from_grant_envelope(
                grant_envelope, basis_id=f"basis:initial:{event.session_id}"
            )

        violations = self._check_consistency(event, inherited_basis)
        if violations:
            return Decision(decision=DecisionType.BLOCK, violations=violations)

        tightening = self.basis_tightener.tighten_basis(
            inherited_basis,
            event,
            new_basis_id=f"basis:{event.session_id}:{event.step_id}",
        )
        if not tightening.valid or tightening.basis is None:
            return self._block(
                tightening.rule or "BASIS_EMPTY_AFTER_UPDATE",
                tightening.reason or "basis tightening failed",
            )
        new_basis = tightening.basis

        lineage_hash: str | None = new_basis.lineage_hash
        if persist:
            try:
                record = CausalLineageRecord(
                    session_id=event.session_id,
                    step_seq=event.step_seq,
                    step_id=event.step_id,
                    event_id=event.event_id,
                    parent_hash=predecessor.predecessor_hash,
                    input_anchors=[anchor.anchor_id for anchor in event.input_anchors],
                    tool_name=event.tool_name,
                    action=event.action,
                    resource_ids=set(event.resource_scope.ids),
                    resource_type=event.resource_scope.type,
                    purpose=event.purpose,
                    output_anchor=output_anchor,
                    basis_id=new_basis.basis_id,
                )
                new_basis.lineage_hash = record.step_hash
                lineage_hash = record.step_hash
                self.lineage_store.append_step(record)
                self.basis_store.save_basis(event.session_id, event.step_id, new_basis)
            except Exception as exc:  # noqa: BLE001
                return self._block("PERSISTENCE_ERROR", str(exc))

        return Decision(
            decision=DecisionType.ALLOW,
            metadata={
                "basis_id": new_basis.basis_id,
                "lineage_hash": lineage_hash,
                "predecessor_status": predecessor.status,
                "resource_origin_status": "VALID" if resource_origin.valid else "INVALID",
            },
        )

    def _block(self, rule: str, reason: str) -> Decision:
        return Decision(
            decision=DecisionType.BLOCK,
            violations=[Violation(rule=rule, reason=reason)],
        )

    def _check_consistency(
        self, event: TypedAuthorizationEvent, inherited_basis: AuthorizationBasis
    ) -> list[Violation]:
        violations: list[Violation] = []

        event_subject = event.subject.effective_subject or event.subject.user_id
        if inherited_basis.subjects and event_subject not in inherited_basis.subjects:
            violations.append(
                Violation(
                    rule="SUBJECT_INCONSISTENCY",
                    reason="event subject not covered by inherited basis",
                )
            )

        if not self.action_lattice.is_action_allowed(event.action, inherited_basis.actions):
            violations.append(
                Violation(
                    rule="ACTION_ESCALATION",
                    reason="event action is more permissive than inherited basis",
                )
            )

        if not set(event.resource_scope.ids).issubset(inherited_basis.resource_scope.ids):
            violations.append(
                Violation(
                    rule="RESOURCE_EXPANSION",
                    reason="event resources are not contained in inherited basis",
                )
            )
        if (
            inherited_basis.resource_scope.type
            and event.resource_scope.type != inherited_basis.resource_scope.type
        ):
            violations.append(
                Violation(
                    rule="RESOURCE_EXPANSION",
                    reason="event resource type does not match inherited basis resource type",
                )
            )

        if event.purpose not in inherited_basis.purpose_scope:
            violations.append(
                Violation(
                    rule="PURPOSE_DRIFT",
                    reason="event purpose is not in inherited purpose_scope",
                )
            )

        if (
            not inherited_basis.delegation.allow_delegation
            and event.delegation.delegated
        ):
            violations.append(
                Violation(
                    rule="DELEGATION_AMPLIFICATION",
                    reason="delegation introduced while inherited basis disallows it",
                )
            )
        if (
            event.delegation.delegated
            and inherited_basis.delegation.allowed_delegatees
        ):
            if event.delegation.delegatee not in inherited_basis.delegation.allowed_delegatees:
                violations.append(
                    Violation(
                        rule="DELEGATION_AMPLIFICATION",
                        reason="delegatee not in inherited allowed_delegatees",
                    )
                )

        condition_check = self.condition_tightener.check_event_conditions(
            event.conditions, inherited_basis.conditions
        )
        if not condition_check.valid:
            violations.append(
                Violation(
                    rule="CONDITION_WEAKENING",
                    reason=condition_check.reason or "event conditions violate inherited basis",
                )
            )

        return violations
