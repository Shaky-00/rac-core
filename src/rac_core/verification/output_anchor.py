from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, Field, model_validator

from rac_core.models import TypedAuthorizationEvent, VerifiedStructuredOutputAnchor
from rac_core.registry import InMemoryResourceRegistry


class ToolOutputAnchorClaim(BaseModel):
    anchor_id: str = Field(min_length=1)
    producer_event_id: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    resource_ids: set[str] = Field(default_factory=set)
    output_type: str | None = None
    schema_version: str = "v1"
    metadata: dict[str, object] = Field(default_factory=dict)


class OutputAnchorVerificationResult(BaseModel):
    valid: bool
    verified_anchor: VerifiedStructuredOutputAnchor | None = None
    rule: str | None = None
    reason: str | None = None
    expected_content_hash: str | None = None
    claimed_content_hash: str | None = None
    expected_resource_ids: set[str] = Field(default_factory=set)
    claimed_resource_ids: set[str] = Field(default_factory=set)
    metadata: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_verified_anchor_presence(self) -> "OutputAnchorVerificationResult":
        if self.valid and self.verified_anchor is None:
            raise ValueError("verified_anchor must be provided when valid=True.")
        return self


class OutputAnchorVerifier:
    def __init__(self, resource_registry: InMemoryResourceRegistry | None = None) -> None:
        self.resource_registry = resource_registry

    def compute_content_hash(self, actual_output: object) -> str:
        if isinstance(actual_output, bytes):
            payload = actual_output
        elif isinstance(actual_output, str):
            payload = actual_output.encode("utf-8")
        else:
            normalized = json.dumps(
                actual_output,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                default=str,
            )
            payload = normalized.encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def verify_output_anchor(
        self,
        anchor_claim: ToolOutputAnchorClaim,
        actual_output: object,
        event: TypedAuthorizationEvent,
        observed_resource_ids: set[str],
    ) -> OutputAnchorVerificationResult:
        expected_content_hash = self.compute_content_hash(actual_output)
        expected_resource_ids = set(observed_resource_ids)
        claimed_resource_ids = set(anchor_claim.resource_ids)

        if anchor_claim.producer_event_id != event.event_id:
            return OutputAnchorVerificationResult(
                valid=False,
                rule="OUTPUT_ANCHOR_INVALID",
                reason="producer_event_id mismatch",
                expected_content_hash=expected_content_hash,
                claimed_content_hash=anchor_claim.content_hash,
                expected_resource_ids=expected_resource_ids,
                claimed_resource_ids=claimed_resource_ids,
            )

        if anchor_claim.content_hash != expected_content_hash:
            return OutputAnchorVerificationResult(
                valid=False,
                rule="OUTPUT_ANCHOR_INVALID",
                reason="content_hash mismatch",
                expected_content_hash=expected_content_hash,
                claimed_content_hash=anchor_claim.content_hash,
                expected_resource_ids=expected_resource_ids,
                claimed_resource_ids=claimed_resource_ids,
            )

        if claimed_resource_ids != expected_resource_ids:
            return OutputAnchorVerificationResult(
                valid=False,
                rule="OUTPUT_ANCHOR_INVALID",
                reason="resource_ids mismatch",
                expected_content_hash=expected_content_hash,
                claimed_content_hash=anchor_claim.content_hash,
                expected_resource_ids=expected_resource_ids,
                claimed_resource_ids=claimed_resource_ids,
            )

        if self.resource_registry is not None:
            for resource_id in expected_resource_ids:
                if not self.resource_registry.contains(resource_id):
                    return OutputAnchorVerificationResult(
                        valid=False,
                        rule="OUTPUT_ANCHOR_INVALID",
                        reason=f"observed resource not registered: {resource_id}",
                        expected_content_hash=expected_content_hash,
                        claimed_content_hash=anchor_claim.content_hash,
                        expected_resource_ids=expected_resource_ids,
                        claimed_resource_ids=claimed_resource_ids,
                    )

        verified_anchor = VerifiedStructuredOutputAnchor(
            anchor_id=anchor_claim.anchor_id,
            producer_event_id=anchor_claim.producer_event_id,
            content_hash=expected_content_hash,
            resource_ids=expected_resource_ids,
            output_type=anchor_claim.output_type,
            schema_version=anchor_claim.schema_version,
            verified_by_controller=True,
            session_id=event.session_id,
            metadata={
                "verified_from": "controller_recomputation",
                "event_id": event.event_id,
            },
        )
        return OutputAnchorVerificationResult(
            valid=True,
            verified_anchor=verified_anchor,
            expected_content_hash=expected_content_hash,
            claimed_content_hash=anchor_claim.content_hash,
            expected_resource_ids=expected_resource_ids,
            claimed_resource_ids=claimed_resource_ids,
        )

    def build_anchor_claim_from_verified(
        self, anchor: VerifiedStructuredOutputAnchor
    ) -> ToolOutputAnchorClaim:
        return ToolOutputAnchorClaim(
            anchor_id=anchor.anchor_id,
            producer_event_id=anchor.producer_event_id,
            content_hash=anchor.content_hash,
            resource_ids=set(anchor.resource_ids),
            output_type=anchor.output_type,
            schema_version=anchor.schema_version,
            metadata=dict(anchor.metadata),
        )
