from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, Field, model_validator

from rac_core.models import (
    Decision,
    DecisionType,
    TypedAuthorizationEvent,
    VerifiedStructuredOutputAnchor,
    Violation,
)
from rac_core.registry import InMemoryResourceRegistry


def output_anchor_integrity_precheck(
    output_anchor: VerifiedStructuredOutputAnchor | None,
    *,
    skip_integrity: bool,
) -> Decision | None:
    """Optional TraceBench-style observed_access vs structured anchor gate before PreCommit.

    When ``skip_integrity`` is True (e.g. RAC_WITHOUT_OUTPUT_ANCHOR / STATIC_TOOL_ALLOWLIST),
    returns ``None`` so the caller continues with the main checker path.

    When the gate fires, returns a BLOCK :class:`~rac_core.models.decision.Decision` with rule
    ``OUTPUT_ANCHOR_MISMATCH`` and metadata ``output_anchor_integrity_check=enabled``.
    """
    if skip_integrity or output_anchor is None:
        return None
    ok, reason = verify_observed_access_matches_anchor(output_anchor)
    if ok:
        return None
    return Decision(
        decision=DecisionType.BLOCK,
        violations=[
            Violation(
                rule="OUTPUT_ANCHOR_MISMATCH",
                reason=reason or "observed_access inconsistent with structured output anchor",
                metadata={"OutputAnchorIntegrity": True},
            )
        ],
        metadata={"output_anchor_integrity_check": "enabled"},
    )


def verify_observed_access_matches_anchor(
    output_anchor: VerifiedStructuredOutputAnchor,
) -> tuple[bool, str | None]:
    """Cross-check fixture ``observed_access`` telemetry against the structured anchor fields.

    Reads ``output_anchor.metadata["observed_access"]`` when present (TraceBench / replay).
    When absent, returns ``(True, None)`` so normal traces are unaffected.

    Returns:
        ``(True, None)`` if valid or no ``observed_access``; otherwise ``(False, reason)``.
    """
    raw_obs = output_anchor.metadata.get("observed_access")
    if raw_obs is None:
        return True, None
    if not isinstance(raw_obs, dict):
        return False, "observed_access must be a JSON object when present."

    declared_resources = set(output_anchor.resource_ids)
    observed_resources: set[str] = set()
    for key in ("resource_ids", "actual_resource_ids", "bytes_read_from_resources"):
        val = raw_obs.get(key)
        if isinstance(val, list):
            observed_resources.update(str(x) for x in val)

    if observed_resources:
        extraneous = observed_resources - declared_resources
        if extraneous:
            return (
                False,
                "observed_access references resource(s) not declared on output_anchor.resource_ids: "
                f"{sorted(extraneous)} (declared {sorted(declared_resources)})",
            )

    declared_hash = output_anchor.content_hash
    observed_hashes: list[str] = []
    for key in ("content_hash", "actual_content_sha256", "observed_summary_sha256"):
        v = raw_obs.get(key)
        if isinstance(v, str) and v.strip():
            observed_hashes.append(v.strip())

    if observed_hashes:
        if declared_hash not in observed_hashes:
            return (
                False,
                "observed_access digest(s) disagree with output_anchor.content_hash "
                f"(declared {declared_hash!r}, observed {observed_hashes!r})",
            )

    return True, None


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
