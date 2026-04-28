from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from rac_core.adapter import EventAdapter
from rac_core.models import (
    GrantEnvelope,
    InputAnchorRef,
    PendingToolCall,
    RuntimeTraceContext,
    SessionContext,
    ToolManifest,
)
from rac_core.registry import InMemoryResourceRegistry, InMemoryToolManifestRegistry
from rac_core.store import InMemoryCausalLineageStore


@dataclass
class MCPIntent:
    step_id: str
    step_seq: int
    tool_name: str
    arguments: dict[str, Any]
    selected_purpose: str | None = None
    input_anchor: str | None = None


class RACMCPAdapter:
    def __init__(
        self,
        *,
        session_context: SessionContext,
        grant_envelope: GrantEnvelope,
        lineage_store: InMemoryCausalLineageStore,
    ) -> None:
        self.session_context = session_context
        self.grant_envelope = grant_envelope
        self.lineage_store = lineage_store
        self.resource_registry = self._build_resource_registry()
        self.manifest_registry = self._build_manifest_registry()
        self.event_adapter = EventAdapter(
            manifest_registry=self.manifest_registry,
            resource_registry=self.resource_registry,
            lineage_store=self.lineage_store,
        )

    def build_pending_call(self, intent: MCPIntent) -> PendingToolCall:
        args = dict(intent.arguments)
        if intent.tool_name == "search_documents":
            args.setdefault("results", self._derive_search_scope(args.get("query")))
        return PendingToolCall(tool_name=intent.tool_name, arguments=args)

    def build_runtime_trace(self, intent: MCPIntent) -> RuntimeTraceContext:
        anchors: list[InputAnchorRef] = []
        if intent.input_anchor:
            anchors.append(InputAnchorRef(anchor_id=intent.input_anchor))
        return RuntimeTraceContext(
            session_id=self.session_context.session_id,
            step_id=intent.step_id,
            step_seq=intent.step_seq,
            input_anchors=anchors,
            selected_purpose=intent.selected_purpose,
            observed_time=datetime(2026, 4, 27, 12, 0, 0),
            environment=self.grant_envelope.conditions.environment or "trusted_workspace",
            tenant=self.session_context.tenant or self.grant_envelope.conditions.tenant,
            runtime_labels=set(self.grant_envelope.conditions.runtime_labels),
        )

    def _build_manifest_registry(self) -> InMemoryToolManifestRegistry:
        reg = InMemoryToolManifestRegistry()
        reg.register(
            ToolManifest(
                tool_name="read_file",
                operation="read",
                resource_arg="file_id",
                resource_type="file",
                resource_pattern="file:*",
                output_anchor_fields=["content_hash", "resource_ids"],
                authorization_effect="read_only",
                commit_type="read",
            )
        )
        reg.register(
            ToolManifest(
                tool_name="search_documents",
                operation="read",
                resource_arg="results",
                resource_type="file",
                resource_pattern="file:*",
                output_anchor_fields=["content_hash", "resource_ids"],
                authorization_effect="read_only",
                commit_type="read",
            )
        )
        reg.register(
            ToolManifest(
                tool_name="summarize_text",
                operation="summarize",
                resource_arg="input_anchor",
                resource_type="derived_content",
                resource_pattern="anchor:*",
                output_anchor_fields=["content_hash", "source_resource_ids"],
                authorization_effect="derived_read",
                commit_type="compute",
            )
        )
        reg.register(
            ToolManifest(
                tool_name="create_email_draft",
                operation="external_disclosure",
                resource_arg="recipient",
                resource_type="external_channel",
                resource_pattern="email:*",
                output_anchor_fields=["draft_id", "content_hash"],
                authorization_effect="external_write",
                commit_type="write_external",
            )
        )
        return reg

    def _build_resource_registry(self) -> InMemoryResourceRegistry:
        reg = InMemoryResourceRegistry()
        for rid in ("file_A", "file_B", "file_C"):
            from rac_core.models import ResourceMetadata

            reg.register(ResourceMetadata(resource_id=rid, resource_type="file"))
        for rid in ("external@example.com", "internal@acme.com"):
            from rac_core.models import ResourceMetadata

            reg.register(ResourceMetadata(resource_id=rid, resource_type="external_channel"))
        return reg

    def _derive_search_scope(self, query: object) -> list[str]:
        text = str(query or "").lower()
        if "q2" in text:
            return ["file_A"]
        if "acme" in text:
            return ["file_A", "file_B"]
        return ["file_B"]
