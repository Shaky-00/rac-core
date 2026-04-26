from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, Field, model_validator

from .anchor import VerifiedStructuredOutputAnchor


class CausalLineageRecord(BaseModel):
    session_id: str = Field(min_length=1)
    step_seq: int = Field(ge=0)
    step_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    parent_hash: str | None = None
    input_anchors: list[str] = Field(default_factory=list)
    tool_name: str = Field(min_length=1)
    action: str = Field(min_length=1)
    resource_ids: set[str] = Field(default_factory=set)
    resource_type: str | None = None
    purpose: str = Field(min_length=1)
    output_anchor: VerifiedStructuredOutputAnchor | None = None
    basis_id: str = Field(min_length=1)
    step_hash: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    def canonical_hash_payload(self) -> dict[str, object]:
        output_anchor_payload: dict[str, object] | None
        if self.output_anchor is not None:
            oa = self.output_anchor
            output_anchor_payload = {
                "anchor_id": oa.anchor_id,
                "producer_event_id": oa.producer_event_id,
                "content_hash": oa.content_hash,
                "resource_ids": sorted(oa.resource_ids),
                "output_type": oa.output_type,
                "schema_version": oa.schema_version,
                "verified_by_controller": oa.verified_by_controller,
                "session_id": oa.session_id,
            }
        else:
            output_anchor_payload = None
        return {
            "session_id": self.session_id,
            "step_seq": self.step_seq,
            "parent_hash": self.parent_hash,
            "input_anchors": self.input_anchors,
            "tool_name": self.tool_name,
            "action": self.action,
            "resource_ids": sorted(self.resource_ids),
            "resource_type": self.resource_type,
            "purpose": self.purpose,
            "output_anchor": output_anchor_payload,
            "basis_id": self.basis_id,
        }

    def compute_step_hash(self) -> str:
        payload = json.dumps(
            self.canonical_hash_payload(),
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def verify_step_hash(self) -> bool:
        if self.step_hash is None:
            return False
        return self.step_hash == self.compute_step_hash()

    @model_validator(mode="after")
    def ensure_step_hash(self) -> "CausalLineageRecord":
        if self.step_hash is None:
            self.step_hash = self.compute_step_hash()
        return self


class PredecessorResolutionResult(BaseModel):
    status: str
    valid: bool
    predecessor_step_id: str | None = None
    predecessor_event_id: str | None = None
    predecessor_hash: str | None = None
    producer_event_ids: list[str] = Field(default_factory=list)
    input_anchor_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    reason: str | None = None
    multi_predecessor: bool = False
