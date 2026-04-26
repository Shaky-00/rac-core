from __future__ import annotations

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
    resource_scope: BasisResourceScope
    purpose_scope: set[str] = Field(default_factory=set)
    delegation: BasisDelegation = Field(default_factory=BasisDelegation)
    conditions: BasisConditions = Field(default_factory=BasisConditions)
    origin_anchors: set[str] = Field(default_factory=set)
    lineage_hash: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

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
