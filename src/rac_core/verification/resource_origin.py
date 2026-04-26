from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from rac_core.models import GrantEnvelope, InputAnchorRef, TypedAuthorizationEvent
from rac_core.store import InMemoryCausalLineageStore


class ResourceOriginVerificationResult(BaseModel):
    valid: bool
    resource_id: str = Field(min_length=1)
    source: str | None = None
    rule: str | None = None
    reason: str | None = None
    matched_anchor_id: str | None = None
    matched_producer_event_id: str | None = None
    checked_input_anchor_ids: list[str] = Field(default_factory=list)
    grant_resource_ids: set[str] = Field(default_factory=set)
    anchor_resource_ids: set[str] = Field(default_factory=set)
    metadata: dict[str, object] = Field(default_factory=dict)


class ResourceOriginBatchVerificationResult(BaseModel):
    valid: bool
    results: list[ResourceOriginVerificationResult] = Field(default_factory=list)
    rule: str | None = None
    reason: str | None = None
    failed_resource_ids: set[str] = Field(default_factory=set)
    metadata: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_batch_consistency(self) -> "ResourceOriginBatchVerificationResult":
        if self.valid and self.failed_resource_ids:
            raise ValueError("failed_resource_ids must be empty when valid=True.")
        return self


class ResourceOriginVerifier:
    def __init__(self, lineage_store: InMemoryCausalLineageStore) -> None:
        self.lineage_store = lineage_store

    def verify_resource_origin(
        self,
        resource_id: str,
        grant_envelope: GrantEnvelope,
        input_anchors: list[InputAnchorRef],
    ) -> ResourceOriginVerificationResult:
        grant_resource_ids = set(grant_envelope.resource_scope.allowed_ids)
        checked_ids = [ref.anchor_id for ref in input_anchors]

        if resource_id in grant_resource_ids:
            return ResourceOriginVerificationResult(
                valid=True,
                resource_id=resource_id,
                source="GRANT_ENVELOPE",
                grant_resource_ids=grant_resource_ids,
                checked_input_anchor_ids=checked_ids,
            )

        if not input_anchors:
            return ResourceOriginVerificationResult(
                valid=False,
                resource_id=resource_id,
                rule="RESOURCE_ORIGIN_UNVERIFIABLE",
                reason="not in grant envelope and no input anchors",
                grant_resource_ids=grant_resource_ids,
                checked_input_anchor_ids=checked_ids,
            )

        predecessor_result = self.lineage_store.resolve_predecessor(
            input_anchors=input_anchors,
            advisory_hints=[],
            session_id=grant_envelope.session_id,
        )
        if not predecessor_result.valid:
            return ResourceOriginVerificationResult(
                valid=False,
                resource_id=resource_id,
                rule="RESOURCE_ORIGIN_UNVERIFIABLE",
                reason=f"predecessor resolution invalid: {predecessor_result.status}",
                grant_resource_ids=grant_resource_ids,
                checked_input_anchor_ids=checked_ids,
                metadata={"predecessor_resolution_status": predecessor_result.status},
            )

        anchor_resource_ids: set[str] = set()
        for anchor_ref in input_anchors:
            producer = self.lineage_store.get_by_output_anchor(anchor_ref.anchor_id)
            if producer is None:
                return ResourceOriginVerificationResult(
                    valid=False,
                    resource_id=resource_id,
                    rule="RESOURCE_ORIGIN_UNVERIFIABLE",
                    reason="producer record not found for input anchor",
                    grant_resource_ids=grant_resource_ids,
                    checked_input_anchor_ids=checked_ids,
                    anchor_resource_ids=anchor_resource_ids,
                )
            if producer.session_id != grant_envelope.session_id:
                return ResourceOriginVerificationResult(
                    valid=False,
                    resource_id=resource_id,
                    rule="RESOURCE_ORIGIN_UNVERIFIABLE",
                    reason="cross session input anchor: producer session mismatch",
                    grant_resource_ids=grant_resource_ids,
                    checked_input_anchor_ids=checked_ids,
                    anchor_resource_ids=anchor_resource_ids,
                )
            output_anchor = producer.output_anchor
            if output_anchor is None:
                return ResourceOriginVerificationResult(
                    valid=False,
                    resource_id=resource_id,
                    rule="RESOURCE_ORIGIN_UNVERIFIABLE",
                    reason="producer output anchor missing",
                    grant_resource_ids=grant_resource_ids,
                    checked_input_anchor_ids=checked_ids,
                    anchor_resource_ids=anchor_resource_ids,
                )
            if not output_anchor.verified_by_controller:
                return ResourceOriginVerificationResult(
                    valid=False,
                    resource_id=resource_id,
                    rule="RESOURCE_ORIGIN_UNVERIFIABLE",
                    reason="input anchor producer output is not controller-verified",
                    grant_resource_ids=grant_resource_ids,
                    checked_input_anchor_ids=checked_ids,
                    anchor_resource_ids=anchor_resource_ids,
                )
            if (
                anchor_ref.content_hash is not None
                and anchor_ref.content_hash != output_anchor.content_hash
            ):
                return ResourceOriginVerificationResult(
                    valid=False,
                    resource_id=resource_id,
                    rule="RESOURCE_ORIGIN_UNVERIFIABLE",
                    reason="input anchor content_hash mismatch",
                    grant_resource_ids=grant_resource_ids,
                    checked_input_anchor_ids=checked_ids,
                    anchor_resource_ids=anchor_resource_ids,
                )
            if (
                anchor_ref.producer_event_id is not None
                and anchor_ref.producer_event_id != producer.event_id
            ):
                return ResourceOriginVerificationResult(
                    valid=False,
                    resource_id=resource_id,
                    rule="RESOURCE_ORIGIN_UNVERIFIABLE",
                    reason="input anchor producer_event_id mismatch",
                    grant_resource_ids=grant_resource_ids,
                    checked_input_anchor_ids=checked_ids,
                    anchor_resource_ids=anchor_resource_ids,
                )
            anchor_resource_ids.update(output_anchor.resource_ids)

        matched_anchor_id: str | None = None
        matched_producer_event_id: str | None = None
        for anchor_ref in input_anchors:
            producer = self.lineage_store.get_by_output_anchor(anchor_ref.anchor_id)
            if producer is None or producer.output_anchor is None:
                continue
            if resource_id in producer.output_anchor.resource_ids:
                matched_anchor_id = anchor_ref.anchor_id
                matched_producer_event_id = producer.event_id
                break

        if resource_id in anchor_resource_ids and matched_anchor_id is not None:
            return ResourceOriginVerificationResult(
                valid=True,
                resource_id=resource_id,
                source="VERIFIED_INPUT_ANCHOR",
                matched_anchor_id=matched_anchor_id,
                matched_producer_event_id=matched_producer_event_id,
                grant_resource_ids=grant_resource_ids,
                checked_input_anchor_ids=checked_ids,
                anchor_resource_ids=anchor_resource_ids,
            )

        return ResourceOriginVerificationResult(
            valid=False,
            resource_id=resource_id,
            rule="RESOURCE_ORIGIN_UNVERIFIABLE",
            reason="not in grant envelope and not found in verified input anchors",
            grant_resource_ids=grant_resource_ids,
            checked_input_anchor_ids=checked_ids,
            anchor_resource_ids=anchor_resource_ids,
        )

    def verify_event_resource_origins(
        self,
        event: TypedAuthorizationEvent,
        grant_envelope: GrantEnvelope,
    ) -> ResourceOriginBatchVerificationResult:
        if event.session_id != grant_envelope.session_id:
            return ResourceOriginBatchVerificationResult(
                valid=False,
                results=[],
                rule="RESOURCE_ORIGIN_UNVERIFIABLE",
                reason="event session_id does not match grant envelope session_id",
                failed_resource_ids=set(event.resource_scope.ids),
                metadata={
                    "event_session_id": event.session_id,
                    "grant_session_id": grant_envelope.session_id,
                },
            )

        results: list[ResourceOriginVerificationResult] = []
        failed: set[str] = set()
        for resource_id in sorted(event.resource_scope.ids):
            result = self.verify_resource_origin(
                resource_id=resource_id,
                grant_envelope=grant_envelope,
                input_anchors=list(event.input_anchors),
            )
            results.append(result)
            if not result.valid:
                failed.add(resource_id)

        if not failed:
            return ResourceOriginBatchVerificationResult(valid=True, results=results)

        return ResourceOriginBatchVerificationResult(
            valid=False,
            results=results,
            rule="RESOURCE_ORIGIN_UNVERIFIABLE",
            reason=f"unverifiable resource origins: {sorted(failed)}",
            failed_resource_ids=failed,
        )
