from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from rac_core.action_semantics.registry import ActionSemanticsRegistry
from rac_core.action_semantics.taxonomy import default_semantics_yaml_path
from rac_core.adapter import EventAdapter
from rac_core.models import (
    AuthorizationProfile,
    EffectProfile,
    GrantEnvelope,
    InputAnchorRef,
    PendingToolCall,
    ResourceMapping,
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
        action_semantics_registry: ActionSemanticsRegistry | None = None,
    ) -> None:
        self.session_context = session_context
        self.grant_envelope = grant_envelope
        self.lineage_store = lineage_store
        self.action_semantics_registry = action_semantics_registry or ActionSemanticsRegistry.load_from_yaml(
            default_semantics_yaml_path()
        )
        self.resource_registry = self._build_resource_registry()
        self.manifest_registry = self._build_manifest_registry()
        self.event_adapter = EventAdapter(
            manifest_registry=self.manifest_registry,
            resource_registry=self.resource_registry,
            lineage_store=self.lineage_store,
            action_semantics_registry=self.action_semantics_registry,
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

        read_effects = EffectProfile(
            state_mutation=False,
            external_disclosure=False,
            authority_change=False,
            real_world_effect=False,
            consumes_anchor=False,
            produces_anchor=True,
            effect_boundary="internal",
        )
        reg.register(
            ToolManifest(
                tool_name="read_file",
                operation="read",
                resource_arg="file_id",
                resource_type="file",
                resource_pattern="file:*",
                output_anchor_fields=["output_id", "content_hash", "resource_ids"],
                authorization_effect="read_only",
                commit_type="read",
                authorization_profile=AuthorizationProfile(
                    required_actions=["acquire.read_object"],
                    resource_mappings=[
                        ResourceMapping(
                            arg="file_id",
                            resource_role="target",
                            resource_type="file",
                            resource_pattern="file:*",
                        )
                    ],
                    effects=read_effects,
                    output_anchor_fields=["output_id", "content_hash", "resource_ids"],
                    commit_type="read",
                ),
            )
        )

        search_effects = EffectProfile(
            state_mutation=False,
            external_disclosure=False,
            authority_change=False,
            real_world_effect=False,
            consumes_anchor=False,
            produces_anchor=True,
            effect_boundary="internal",
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
                authorization_profile=AuthorizationProfile(
                    required_actions=["acquire.search_collection"],
                    resource_mappings=[
                        ResourceMapping(
                            arg="query",
                            resource_role="query",
                            resource_type="collection",
                            resource_pattern=None,
                            required=False,
                        ),
                        ResourceMapping(
                            arg="results",
                            resource_role="target",
                            resource_type="file",
                            resource_pattern="file:*",
                        ),
                    ],
                    effects=search_effects,
                    output_anchor_fields=["content_hash", "resource_ids"],
                    commit_type="read",
                ),
            )
        )

        summarize_effects = EffectProfile(
            state_mutation=False,
            external_disclosure=False,
            authority_change=False,
            real_world_effect=False,
            consumes_anchor=True,
            produces_anchor=True,
            effect_boundary="internal",
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
                authorization_profile=AuthorizationProfile(
                    required_actions=["transform.summarize"],
                    resource_mappings=[
                        ResourceMapping(
                            arg="input_anchor",
                            resource_role="input",
                            resource_type="derived_content",
                            resource_pattern="anchor:*",
                        )
                    ],
                    effects=summarize_effects,
                    output_anchor_fields=["output_id", "content_hash", "source_resource_ids"],
                    commit_type="compute",
                ),
            )
        )

        email_effects = EffectProfile(
            state_mutation=True,
            external_disclosure=True,
            authority_change=False,
            real_world_effect=False,
            consumes_anchor=True,
            produces_anchor=True,
            effect_boundary="external",
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
                authorization_profile=AuthorizationProfile(
                    required_actions=["disclose.send_message"],
                    resource_mappings=[
                        ResourceMapping(
                            arg="recipient",
                            resource_role="recipient",
                            resource_type="external_channel",
                            resource_pattern="email:*",
                        ),
                        ResourceMapping(
                            arg="input_anchor",
                            resource_role="input",
                            resource_type="derived_content",
                            resource_pattern="anchor:*",
                            required=False,
                        ),
                    ],
                    effects=email_effects,
                    output_anchor_fields=["draft_id", "content_hash"],
                    commit_type="write_external",
                ),
            )
        )
        return reg

    def _build_resource_registry(self) -> InMemoryResourceRegistry:
        from rac_core.models import ResourceMetadata

        reg = InMemoryResourceRegistry()
        for rid in ("file_A", "file_B", "file_C"):
            reg.register(ResourceMetadata(resource_id=rid, resource_type="file"))
        for rid in ("external@example.com", "internal@acme.com"):
            reg.register(ResourceMetadata(resource_id=rid, resource_type="external_channel"))
        reg.register(ResourceMetadata(resource_id="collection", resource_type="collection"))
        return reg

    def _derive_search_scope(self, query: object) -> list[str]:
        text = str(query or "").lower()
        if "q2" in text:
            return ["file_A"]
        if "acme" in text:
            return ["file_A", "file_B"]
        return ["file_B"]
