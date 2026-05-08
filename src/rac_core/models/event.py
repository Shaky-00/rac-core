from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TypedEventSubject(BaseModel):
    user_id: str = Field(min_length=1)
    agent_id: str | None = None
    effective_subject: str | None = None
    tenant: str | None = None
    roles: set[str] = Field(default_factory=set)


class TypedEventResourceScope(BaseModel):
    type: str = Field(min_length=1)
    ids: set[str] = Field(default_factory=set)


class TypedEventConditions(BaseModel):
    time: datetime | None = None
    environment: str | None = None
    tenant: str | None = None
    runtime_labels: set[str] = Field(default_factory=set)


class TypedEventDelegation(BaseModel):
    delegated: bool = False
    delegatee: str | None = None
    delegator: str | None = None
    delegation_depth: int = Field(default=0, ge=0)


class InputAnchorRef(BaseModel):
    anchor_id: str = Field(min_length=1)
    producer_event_id: str | None = None
    content_hash: str | None = None


class TypedAuthorizationEvent(BaseModel):
    event_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    step_seq: int = Field(ge=0)
    subject: TypedEventSubject
    tool_name: str = Field(min_length=1)
    action: str = Field(min_length=1)
    required_actions: list[str] = Field(
        default_factory=list,
        description="v0.6 leaf action labels from manifest.authorization_profile when present.",
    )
    resource_scope: TypedEventResourceScope
    purpose: str = Field(min_length=1)
    conditions: TypedEventConditions = Field(default_factory=TypedEventConditions)
    delegation: TypedEventDelegation = Field(default_factory=TypedEventDelegation)
    input_anchors: list[InputAnchorRef] = Field(default_factory=list)
    advisory_predecessor_hints: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)

    def effective_required_actions(self) -> list[str]:
        """Leaf-level required actions; falls back to the single coarse ``action`` when list is empty."""
        if self.required_actions:
            return list(self.required_actions)
        if self.action:
            return [self.action]
        return []
