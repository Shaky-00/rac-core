from __future__ import annotations

from rac_core.models import (
    GrantEnvelope,
    SessionContext,
    PendingToolCall,
    RuntimeTraceContext,
    TypedAuthorizationEvent,
    TypedEventConditions,
    TypedEventDelegation,
    TypedEventResourceScope,
    TypedEventSubject,
)
from rac_core.registry import InMemoryResourceRegistry, InMemoryToolManifestRegistry
from rac_core.store import InMemoryCausalLineageStore


class EventConstructionError(Exception):
    pass


class EventAdapter:
    def __init__(
        self,
        manifest_registry: InMemoryToolManifestRegistry,
        resource_registry: InMemoryResourceRegistry,
        lineage_store: InMemoryCausalLineageStore,
    ) -> None:
        self.manifest_registry = manifest_registry
        self.resource_registry = resource_registry
        self.lineage_store = lineage_store

    def construct_event(
        self,
        session_context: SessionContext,
        grant_envelope: GrantEnvelope,
        pending_tool_call: PendingToolCall,
        runtime_trace_context: RuntimeTraceContext,
    ) -> TypedAuthorizationEvent:
        self._validate_session_consistency(
            session_context=session_context,
            grant_envelope=grant_envelope,
            runtime_trace_context=runtime_trace_context,
        )

        try:
            manifest = self.manifest_registry.load(pending_tool_call.tool_name)
        except ValueError as exc:
            raise EventConstructionError(str(exc)) from exc

        predecessor_result = self.lineage_store.resolve_predecessor(
            runtime_trace_context.input_anchors,
            pending_tool_call.advisory_predecessor_hints,
            session_context.session_id,
        )
        if runtime_trace_context.input_anchors and not predecessor_result.valid:
            raise EventConstructionError(
                f"Invalid runtime input anchors: {predecessor_result.status}"
            )

        resource_scope = self._build_resource_scope(
            pending_tool_call=pending_tool_call,
            runtime_trace_context=runtime_trace_context,
            manifest_resource_arg=manifest.resource_arg,
            manifest_resource_type=manifest.resource_type,
        )

        purpose = self._select_purpose(grant_envelope, runtime_trace_context)

        subject = TypedEventSubject(
            user_id=session_context.user_id,
            agent_id=session_context.agent_id,
            effective_subject=session_context.subject_id(),
            tenant=session_context.tenant,
            roles=set(session_context.roles),
        )

        conditions = TypedEventConditions(
            time=runtime_trace_context.observed_time,
            environment=runtime_trace_context.environment
            or grant_envelope.conditions.environment,
            tenant=runtime_trace_context.tenant
            or session_context.tenant
            or grant_envelope.conditions.tenant,
            runtime_labels=set(runtime_trace_context.runtime_labels)
            or set(grant_envelope.conditions.runtime_labels),
        )

        delegation = TypedEventDelegation(
            delegated=runtime_trace_context.delegated,
            delegatee=runtime_trace_context.delegatee,
            delegator=runtime_trace_context.delegator,
            delegation_depth=runtime_trace_context.delegation_depth,
        )

        metadata: dict[str, object] = {
            "manifest_tool_name": manifest.tool_name,
            "manifest_operation": manifest.operation,
            "manifest_resource_arg": manifest.resource_arg,
            "manifest_resource_type": manifest.resource_type,
            "predecessor_resolution": predecessor_result.model_dump(),
        }
        if runtime_trace_context.trace_id is not None:
            metadata["trace_id"] = runtime_trace_context.trace_id
        if predecessor_result.warnings:
            metadata["warnings"] = predecessor_result.warnings

        event_id = f"evt:{session_context.session_id}:{runtime_trace_context.step_id}"

        return TypedAuthorizationEvent(
            event_id=event_id,
            session_id=session_context.session_id,
            step_id=runtime_trace_context.step_id,
            step_seq=runtime_trace_context.step_seq,
            subject=subject,
            tool_name=pending_tool_call.tool_name,
            action=manifest.operation,
            resource_scope=resource_scope,
            purpose=purpose,
            conditions=conditions,
            delegation=delegation,
            input_anchors=list(runtime_trace_context.input_anchors),
            advisory_predecessor_hints=list(pending_tool_call.advisory_predecessor_hints),
            metadata=metadata,
        )

    def _validate_session_consistency(
        self,
        session_context: SessionContext,
        grant_envelope: GrantEnvelope,
        runtime_trace_context: RuntimeTraceContext,
    ) -> None:
        if session_context.session_id != grant_envelope.session_id:
            raise EventConstructionError("Session context and grant envelope session_id mismatch.")
        if runtime_trace_context.session_id != session_context.session_id:
            raise EventConstructionError("Runtime trace and session context session_id mismatch.")

    def _build_resource_scope(
        self,
        pending_tool_call: PendingToolCall,
        runtime_trace_context: RuntimeTraceContext,
        manifest_resource_arg: str,
        manifest_resource_type: str,
    ) -> TypedEventResourceScope:
        if manifest_resource_arg == "input_anchor":
            if not runtime_trace_context.input_anchors:
                raise EventConstructionError(
                    "input_anchor resource_arg requires runtime input_anchors."
                )

            producer_resource_ids: set[str] = set()
            for anchor_ref in runtime_trace_context.input_anchors:
                producer_record = self.lineage_store.get_by_output_anchor(anchor_ref.anchor_id)
                if (
                    producer_record is None
                    or producer_record.output_anchor is None
                    or not producer_record.output_anchor.verified_by_controller
                ):
                    raise EventConstructionError(
                        "Unable to resolve verified producer output anchor for summarize_file."
                    )
                producer_resource_ids.update(producer_record.output_anchor.resource_ids)

            if not producer_resource_ids:
                raise EventConstructionError(
                    "No producer resource_ids derived from verified input anchors."
                )

            try:
                self.resource_registry.validate_resource_ids(
                    producer_resource_ids, expected_type="file"
                )
            except ValueError as exc:
                raise EventConstructionError(str(exc)) from exc

            return TypedEventResourceScope(type="file", ids=producer_resource_ids)

        raw_value = pending_tool_call.arguments.get(manifest_resource_arg)
        resource_ids = self._coerce_resource_ids(raw_value, manifest_resource_arg)

        expected_type = manifest_resource_type
        try:
            self.resource_registry.validate_resource_ids(resource_ids, expected_type=expected_type)
        except ValueError as exc:
            raise EventConstructionError(str(exc)) from exc
        return TypedEventResourceScope(type=expected_type, ids=resource_ids)

    def _coerce_resource_ids(self, value: object, field_name: str) -> set[str]:
        if isinstance(value, str):
            if not value:
                raise EventConstructionError(f"Argument `{field_name}` must not be empty.")
            return {value}
        if isinstance(value, list):
            if not value:
                raise EventConstructionError(f"Argument `{field_name}` list must not be empty.")
            if not all(isinstance(item, str) and item for item in value):
                raise EventConstructionError(
                    f"Argument `{field_name}` must be str or list[str]."
                )
            return set(value)
        raise EventConstructionError(f"Argument `{field_name}` must be str or list[str].")

    def _select_purpose(
        self, grant_envelope: GrantEnvelope, runtime_trace_context: RuntimeTraceContext
    ) -> str:
        purpose_scope = set(grant_envelope.purpose_scope)
        if not purpose_scope:
            raise EventConstructionError("Grant purpose_scope is empty.")

        if runtime_trace_context.selected_purpose:
            if runtime_trace_context.selected_purpose not in purpose_scope:
                raise EventConstructionError("selected_purpose is not in grant purpose_scope.")
            return runtime_trace_context.selected_purpose

        if len(purpose_scope) == 1:
            return next(iter(purpose_scope))
        raise EventConstructionError("purpose scope ambiguous; selected_purpose is required.")
