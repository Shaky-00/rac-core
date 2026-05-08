from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TimeWindow(BaseModel):
    start: datetime | None = None
    end: datetime | None = None


class GrantSubject(BaseModel):
    user_id: str = Field(min_length=1)
    agent_id: str | None = None
    tenant: str | None = None
    organization: str | None = None
    roles: set[str] = Field(default_factory=set)
    effective_subject: str | None = None


class ResourceScope(BaseModel):
    type: str = Field(min_length=1)
    allowed_ids: set[str] = Field(default_factory=set)
    allowed_labels: set[str] = Field(default_factory=set)


class DelegationConstraint(BaseModel):
    allow_delegation: bool = False
    allowed_delegatees: set[str] = Field(default_factory=set)


class GrantConditions(BaseModel):
    time_window: TimeWindow | None = None
    environment: str | None = None
    tenant: str | None = None
    runtime_labels: set[str] = Field(default_factory=set)


class GrantEnvelope(BaseModel):
    """Session grant envelope (v0.6 research MVP). Unknown fields are ignored for forward tolerance."""

    model_config = ConfigDict(extra="ignore")

    grant_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    subject: GrantSubject
    allowed_actions: set[str] = Field(default_factory=set)
    allowed_tools: set[str] = Field(default_factory=set)
    resource_scope: ResourceScope
    purpose_scope: set[str] = Field(default_factory=set)
    delegation: DelegationConstraint = Field(default_factory=DelegationConstraint)
    conditions: GrantConditions = Field(default_factory=GrantConditions)
