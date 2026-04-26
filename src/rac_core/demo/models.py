from __future__ import annotations

from pydantic import BaseModel, Field

from rac_core.models import Decision, DecisionType, PendingToolCall
from rac_core.models.anchor import VerifiedStructuredOutputAnchor
from rac_core.verification import ToolOutputAnchorClaim


class DemoToolResult(BaseModel):
    actual_output: object
    anchor_claim: ToolOutputAnchorClaim | None = None
    observed_resource_ids: set[str] = Field(default_factory=set)
    metadata: dict[str, object] = Field(default_factory=dict)


class DemoStepResult(BaseModel):
    step_name: str
    pending_tool_call: PendingToolCall
    event_id: str | None = None
    decision: Decision
    verified_anchor: VerifiedStructuredOutputAnchor | None = None
    blocked_reason: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class DemoRunResult(BaseModel):
    scenario_name: str
    steps: list[DemoStepResult] = Field(default_factory=list)
    final_decision: DecisionType
    blocked_at_step: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
