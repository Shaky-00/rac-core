from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .event import InputAnchorRef


class PendingToolCall(BaseModel):
    tool_name: str = Field(min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)
    advisory_predecessor_hints: list[str] = Field(default_factory=list)
    llm_explanation: str | None = None
    free_form_text: str | None = None
    agent_declared_action: str | None = None
    agent_declared_purpose: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class RuntimeTraceContext(BaseModel):
    session_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    step_seq: int = Field(ge=0)
    input_anchors: list[InputAnchorRef] = Field(default_factory=list)
    selected_purpose: str | None = None
    observed_time: datetime | None = None
    environment: str | None = None
    tenant: str | None = None
    runtime_labels: set[str] = Field(default_factory=set)
    delegated: bool = False
    delegatee: str | None = None
    delegator: str | None = None
    delegation_depth: int = Field(default=0, ge=0)
    trace_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
