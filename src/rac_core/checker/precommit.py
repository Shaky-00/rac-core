from __future__ import annotations

from typing import Literal

from rac_core.action_semantics.coverage import action_covered
from rac_core.action_semantics.registry import ActionSemanticsRegistry
from rac_core.action_semantics.taxonomy import default_semantics_yaml_path
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
from rac_core.store.lineage_store import event_requires_tracebench_producer_event_id
from rac_core.verification import ResourceOriginVerifier

from .action_lattice import ActionLattice
from .basis_tightening import BasisTightener
from .conditions import ConditionTightener

ViolationType = Literal[
    "SUBJECT_INCONSISTENCY",
    "ACTION_ESCALATION",
    "ACTION_BASIS_MISSING",
    "RESOURCE_EXPANSION",
    "PURPOSE_DRIFT",
    "DELEGATION_AMPLIFICATION",
    "CONDITION_WEAKENING",
]


class RACPreCommitChecker:
    def __init__(
        self,
        lineage_store: InMemoryCausalLineageStore,
        basis_store: InMemoryBasisStore,
        resource_origin_verifier: ResourceOriginVerifier | None = None,
        action_lattice: ActionLattice | None = None,
        condition_tightener: ConditionTightener | None = None,
        basis_tightener: BasisTightener | None = None,
        *,
        action_semantics_registry: ActionSemanticsRegistry | None = None,
        disabled_rules: set[ViolationType] | None = None,
        skipped_consistency_rules: frozenset[str] | None = None,
        require_verified_output_anchor: bool = False,
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
        self._action_semantics_registry_override = action_semantics_registry
        self._action_semantics_registry_lazy: ActionSemanticsRegistry | None = None
        merged_disabled_rules: set[str] = set(disabled_rules or set())
        if skipped_consistency_rules is not None:
            merged_disabled_rules |= set(skipped_consistency_rules)
        self.skipped_consistency_rules = frozenset(merged_disabled_rules)
        self.require_verified_output_anchor = require_verified_output_anchor

    def _action_semantics_registry(self) -> ActionSemanticsRegistry:
        if self._action_semantics_registry_override is not None:
            return self._action_semantics_registry_override
        if self._action_semantics_registry_lazy is None:
            self._action_semantics_registry_lazy = ActionSemanticsRegistry.load_from_yaml(
                default_semantics_yaml_path()
            )
        return self._action_semantics_registry_lazy

    def check(
        self,
        event: TypedAuthorizationEvent,
        grant_envelope: GrantEnvelope,
        *,
        local_allow: bool = True,
        output_anchor: VerifiedStructuredOutputAnchor | None = None,
        persist: bool = True,
        initial_basis: AuthorizationBasis | None = None,
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

        if self.require_verified_output_anchor and output_anchor is not None:
            if not output_anchor.verified_by_controller:
                return self._block(
                    "OUTPUT_ANCHOR_INVALID",
                    "Structured output anchor is not controller-verified.",
                )

        predecessor = self.lineage_store.resolve_predecessor(
            event.input_anchors,
            event.advisory_predecessor_hints,
            event.session_id,
            require_producer_event_id_on_inputs=event_requires_tracebench_producer_event_id(
                event.metadata
            ),
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
            if initial_basis is not None:
                inherited_basis = initial_basis
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
        skip = self.skipped_consistency_rules

        event_subject = event.subject.effective_subject or event.subject.user_id
        if "SUBJECT_INCONSISTENCY" not in skip:
            if inherited_basis.subjects and event_subject not in inherited_basis.subjects:
                violations.append(
                    Violation(
                        rule="SUBJECT_INCONSISTENCY",
                        reason="event subject not covered by inherited basis",
                    )
                )

        if "ACTION_ESCALATION" not in skip:
            if event.required_actions:
                violations.extend(
                    self._check_action_coverage_v06(event, inherited_basis)
                )
            else:
                if not self.action_lattice.is_action_allowed(event.action, inherited_basis.actions):
                    violations.append(
                        Violation(
                            rule="ACTION_ESCALATION",
                            reason="event action is more permissive than inherited basis",
                        )
                    )

        if "RESOURCE_EXPANSION" not in skip:
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

        if "PURPOSE_DRIFT" not in skip:
            if event.purpose not in inherited_basis.purpose_scope:
                violations.append(
                    Violation(
                        rule="PURPOSE_DRIFT",
                        reason="event purpose is not in inherited purpose_scope",
                    )
                )

        if "DELEGATION_AMPLIFICATION" not in skip:
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

        if "CONDITION_WEAKENING" not in skip:
            condition_check = self.condition_tightener.check_event_conditions(
                event.conditions, inherited_basis.conditions
            )
            if not condition_check.valid:
                violations.append(
                    Violation(
                        rule="CONDITION_WEAKENING",
                        reason=condition_check.reason
                        or "event conditions violate inherited basis",
                    )
                )

        return violations

    def _check_action_coverage_v06(
        self, event: TypedAuthorizationEvent, basis: AuthorizationBasis
    ) -> list[Violation]:
        """v0.6 leaf coverage when ``event.required_actions`` is non-empty.

        When ``basis.allowed_action_labels`` is empty, refuse the coarse ``basis.actions``
        fallback (mixed / ambiguous state). Otherwise require every ``required_actions``
        entry be covered under the configured partial order
        (:func:`~rac_core.action_semantics.coverage.action_covered`).
        """
        if not basis.allowed_action_labels:
            return [
                Violation(
                    rule="ACTION_BASIS_MISSING",
                    reason=(
                        "event.required_actions is non-empty but inherited basis.allowed_action_labels "
                        "is empty; v0.6 action coverage cannot run and coarse basis.actions are not used "
                        "as a fallback."
                    ),
                )
            ]
        reg = self._action_semantics_registry()
        allowed = set(basis.allowed_action_labels)
        try:
            uncovered = [
                r for r in event.required_actions if not action_covered(r, allowed, reg)
            ]
        except ValueError as exc:
            return [Violation(rule="ACTION_ESCALATION", reason=str(exc))]
        if uncovered:
            return [
                Violation(
                    rule="ACTION_ESCALATION",
                    reason=(
                        "v0.6 action coverage failed; uncovered required_action(s): "
                        + ", ".join(sorted(uncovered))
                    ),
                )
            ]
        return []
