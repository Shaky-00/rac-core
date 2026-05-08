from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rac_core.models import (
    GrantEnvelope,
    InputAnchorRef,
    PendingToolCall,
    RuntimeTraceContext,
    SessionContext,
    TypedAuthorizationEvent,
    TypedEventConditions,
    TypedEventDelegation,
    TypedEventResourceScope,
    TypedEventSubject,
)


@dataclass
class MappingResult:
    ok: bool
    event: TypedAuthorizationEvent | None
    pending: PendingToolCall | None
    runtime_trace: RuntimeTraceContext | None
    mapping_warnings: list[str]


class AuthorizationEventMapper:
    def __init__(self, manifest_path: Path) -> None:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        self._manifest_version = str(payload.get("trusted_manifest_version", "unknown"))
        self._tools = {t["tool_name"]: t for t in payload.get("tools", [])}

    def map_pending_call(
        self,
        *,
        step_seq: int,
        step_id: str,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
        session_context: SessionContext,
        grant_envelope: GrantEnvelope,
        session_anchors: dict[str, dict[str, Any]],
        selected_purpose: str,
    ) -> MappingResult:
        warnings: list[str] = []
        manifest = self._tools.get(tool_name)
        if manifest is None:
            return MappingResult(False, None, None, None, [f"unknown_manifest_tool:{tool_name}"])
        if manifest.get("mcp_server") != server_name:
            return MappingResult(False, None, None, None, ["server_manifest_mismatch"])

        resource_ids: set[str] = set()
        for name in manifest.get("resource_args", []):
            value = arguments.get(name)
            if value is None and tool_name == "search_reports" and name == "search_space_resource":
                value = "res:index:reports"
                warnings.append("search_reports_defaulted_search_space_resource")
            self._collect_values(resource_ids, value)

        input_anchors: list[InputAnchorRef] = []
        for name in manifest.get("artifact_args", []):
            value = arguments.get(name)
            if value is None:
                continue
            candidates = [value] if isinstance(value, str) else [x for x in value if isinstance(x, str)]
            for anchor_id in candidates:
                if anchor_id in session_anchors:
                    input_anchors.append(InputAnchorRef(anchor_id=anchor_id))
                    resource_ids.update(set(session_anchors[anchor_id].get("resource_ids", [])))
                else:
                    warnings.append(f"unknown_input_anchor:{anchor_id}")

        for name in manifest.get("recipient_args", []):
            self._collect_values(resource_ids, arguments.get(name))

        if not resource_ids:
            warnings.append("resource_scope_empty;using_grant_scope")
            resource_ids = set(grant_envelope.resource_scope.allowed_ids)

        action, action_warnings = self._resolve_rac_action(manifest)
        warnings.extend(action_warnings)

        pending = PendingToolCall(
            tool_name=tool_name,
            arguments=dict(arguments),
            metadata={
                "server_name": server_name,
                "trusted_manifest_version": self._manifest_version,
                "action_relation_class": manifest.get("action_relation_class"),
            },
        )
        runtime = RuntimeTraceContext(
            session_id=session_context.session_id,
            step_id=step_id,
            step_seq=step_seq,
            input_anchors=input_anchors,
            selected_purpose=selected_purpose,
            observed_time=datetime.now(timezone.utc),
            environment=grant_envelope.conditions.environment,
            tenant=grant_envelope.conditions.tenant,
            runtime_labels=set(grant_envelope.conditions.runtime_labels),
        )
        event = TypedAuthorizationEvent(
            event_id=f"evt:{session_context.session_id}:{step_id}",
            session_id=session_context.session_id,
            step_id=step_id,
            step_seq=step_seq,
            subject=TypedEventSubject(
                user_id=session_context.user_id,
                agent_id=session_context.agent_id,
                effective_subject=session_context.subject_id(),
                tenant=session_context.tenant,
                roles=set(session_context.roles),
            ),
            tool_name=tool_name,
            action=action,
            resource_scope=TypedEventResourceScope(type=grant_envelope.resource_scope.type, ids=resource_ids),
            purpose=selected_purpose,
            conditions=TypedEventConditions(
                time=runtime.observed_time,
                environment=runtime.environment,
                tenant=runtime.tenant,
                runtime_labels=set(runtime.runtime_labels),
            ),
            delegation=TypedEventDelegation(),
            input_anchors=input_anchors,
            advisory_predecessor_hints=[],
            metadata={
                "mcp_server": server_name,
                "trusted_manifest_version": self._manifest_version,
                "manifest_tool": manifest,
            },
        )
        return MappingResult(True, event, pending, runtime, warnings)

    @staticmethod
    def _collect_values(target: set[str], value: Any) -> None:
        if isinstance(value, str) and value:
            target.add(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item:
                    target.add(item)

    @staticmethod
    def _resolve_rac_action(manifest: dict[str, Any]) -> tuple[str, list[str]]:
        warnings: list[str] = []
        canonical = str(manifest.get("canonical_action") or "read")
        relation = str(manifest.get("action_relation_class") or "")

        # Keep mapping generic and manifest-driven: when the lattice lacks a
        # dedicated internal artifact creation action, map to derived_compute.
        if relation.startswith("internal_artifact_"):
            return "derived_compute", warnings
        if canonical == "internal_artifact_create":
            warnings.append("action_internal_artifact_create_mapped_to_derived_compute")
            return "derived_compute", warnings
        if canonical == "search":
            warnings.append("action_search_mapped_to_read_for_rac")
            return "read", warnings
        return canonical, warnings
