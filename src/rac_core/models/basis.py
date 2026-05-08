from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .grant import GrantEnvelope, TimeWindow


class BasisResourceScope(BaseModel):
    type: str = Field(min_length=1)
    ids: set[str] = Field(default_factory=set)
    labels: set[str] = Field(default_factory=set)


class BasisDelegation(BaseModel):
    allow_delegation: bool = False
    allowed_delegatees: set[str] = Field(default_factory=set)
    delegation_depth: int = Field(default=0, ge=0)


class BasisConditions(BaseModel):
    time_window: TimeWindow | None = None
    environment: str | None = None
    tenant: str | None = None
    runtime_labels: set[str] = Field(default_factory=set)


class AuthorizationBasis(BaseModel):
    basis_id: str = Field(min_length=1)
    subjects: set[str] = Field(default_factory=set)
    actions: set[str] = Field(default_factory=set)
    allowed_action_labels: list[str] = Field(
        default_factory=list,
        description="v0.6 leaf labels from grant/profile expansion when populated.",
    )
    source_templates: list[str] = Field(
        default_factory=list,
        description="Grant template ids used when basis was issued from a compiled profile.",
    )
    compiled_grant_conditions: dict[str, Any] = Field(
        default_factory=dict,
        description="Policy conditions from CompiledGrantProfile (template YAML); distinct from runtime BasisConditions.",
    )
    compiled_grant_delegation: dict[str, Any] = Field(
        default_factory=dict,
        description="Delegation constraints from CompiledGrantProfile (template YAML); distinct from structural BasisDelegation.",
    )
    resource_scope: BasisResourceScope
    purpose_scope: set[str] = Field(default_factory=set)
    delegation: BasisDelegation = Field(default_factory=BasisDelegation)
    conditions: BasisConditions = Field(default_factory=BasisConditions)
    origin_anchors: set[str] = Field(default_factory=set)
    lineage_hash: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    def effective_allowed_action_labels(self) -> list[str]:
        """Leaf-level allowed labels; falls back to sorted coarse ``actions`` when list is empty."""
        if self.allowed_action_labels:
            return list(self.allowed_action_labels)
        return sorted(self.actions)

    @classmethod
    def from_compiled_grant_profile(
        cls,
        profile: "CompiledGrantProfile",
        *,
        basis_id: str,
        subjects: set[str],
        resource_scope: BasisResourceScope,
        lineage_hash: str | None = None,
        legacy_actions: set[str] | None = None,
        origin_anchors: set[str] | None = None,
        runtime_conditions: BasisConditions | None = None,
        runtime_delegation: BasisDelegation | None = None,
    ) -> AuthorizationBasis:
        """Issue a basis from a trusted :class:`~rac_core.action_semantics.grant_template.CompiledGrantProfile`.

        Optional coarse ``actions`` (parameter ``legacy_actions``) populate ``AuthorizationBasis.actions``
        when no leaf labels are supplied; template policy dicts are stored in ``compiled_grant_*`` fields;
        ``conditions`` / ``delegation`` slots hold runtime structural state (defaults unless overridden).
        """
        from rac_core.action_semantics.grant_template import CompiledGrantProfile as _CompiledGrantProfile

        if not isinstance(profile, _CompiledGrantProfile):
            raise TypeError(f"profile must be CompiledGrantProfile, got {type(profile).__name__}")
        actions = set(legacy_actions) if legacy_actions is not None else set()
        return cls(
            basis_id=basis_id,
            subjects=set(subjects),
            actions=actions,
            allowed_action_labels=list(profile.allowed_action_labels),
            source_templates=list(profile.source_templates),
            compiled_grant_conditions=dict(profile.conditions),
            compiled_grant_delegation=dict(profile.delegation),
            resource_scope=resource_scope,
            purpose_scope=set(profile.purpose_scope),
            delegation=runtime_delegation or BasisDelegation(),
            conditions=runtime_conditions or BasisConditions(),
            origin_anchors=set(origin_anchors) if origin_anchors is not None else set(),
            lineage_hash=lineage_hash,
            metadata={},
        )

    @classmethod
    def from_grant_envelope(
        cls, grant: GrantEnvelope, basis_id: str = "basis_initial"
    ) -> "AuthorizationBasis":
        subject = grant.subject.effective_subject or grant.subject.user_id
        return cls(
            basis_id=basis_id,
            subjects={subject},
            actions=set(grant.allowed_actions),
            resource_scope=BasisResourceScope(
                type=grant.resource_scope.type,
                ids=set(grant.resource_scope.allowed_ids),
                labels=set(grant.resource_scope.allowed_labels),
            ),
            purpose_scope=set(grant.purpose_scope),
            delegation=BasisDelegation(
                allow_delegation=grant.delegation.allow_delegation,
                allowed_delegatees=set(grant.delegation.allowed_delegatees),
            ),
            conditions=BasisConditions(
                time_window=grant.conditions.time_window,
                environment=grant.conditions.environment,
                tenant=grant.conditions.tenant,
                runtime_labels=set(grant.conditions.runtime_labels),
            ),
        )
