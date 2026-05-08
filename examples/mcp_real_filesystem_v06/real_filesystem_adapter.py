"""RAC v0.6 manifests + sandbox path → grant resource_id mapping for real filesystem MCP servers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from rac_core.action_semantics.registry import ActionSemanticsRegistry
from rac_core.action_semantics.taxonomy import default_semantics_yaml_path
from rac_core.adapter import EventAdapter, EventConstructionError
from rac_core.models import (
    AuthorizationProfile,
    EffectProfile,
    GrantEnvelope,
    InputAnchorRef,
    PendingToolCall,
    ResourceMapping,
    ResourceMetadata,
    RuntimeTraceContext,
    SessionContext,
    ToolManifest,
    TypedEventResourceScope,
)
from rac_core.registry import InMemoryResourceRegistry, InMemoryToolManifestRegistry
from rac_core.store import InMemoryCausalLineageStore


def _read_effect(*, produces_anchor: bool = True) -> EffectProfile:
    return EffectProfile(
        state_mutation=False,
        external_disclosure=False,
        authority_change=False,
        real_world_effect=False,
        consumes_anchor=False,
        produces_anchor=produces_anchor,
        effect_boundary="internal",
    )


def _write_effect() -> EffectProfile:
    return EffectProfile(
        state_mutation=True,
        external_disclosure=False,
        authority_change=False,
        real_world_effect=False,
        consumes_anchor=False,
        produces_anchor=True,
        effect_boundary="internal",
    )


def build_fs_manifest_registry() -> InMemoryToolManifestRegistry:
    """Tool names aligned with common MCP filesystem servers (e.g. @modelcontextprotocol/server-filesystem)."""
    reg = InMemoryToolManifestRegistry()
    reg.register(
        ToolManifest(
            tool_name="read_file",
            operation="read",
            resource_arg="path",
            resource_type="file",
            resource_pattern="file:*",
            output_anchor_fields=["output_id", "content_hash", "resource_ids"],
            authorization_effect="read_only",
            commit_type="read",
            authorization_profile=AuthorizationProfile(
                required_actions=["acquire.read_object"],
                resource_mappings=[
                    ResourceMapping(
                        arg="path",
                        resource_role="target",
                        resource_type="file",
                        resource_pattern="file:*",
                    )
                ],
                effects=_read_effect(),
                output_anchor_fields=["output_id", "content_hash", "resource_ids"],
                commit_type="read",
            ),
        )
    )
    reg.register(
        ToolManifest(
            tool_name="write_file",
            operation="write",
            resource_arg="path",
            resource_type="file",
            resource_pattern="file:*",
            output_anchor_fields=["output_id", "content_hash", "resource_ids"],
            authorization_effect="write",
            commit_type="write_internal",
            authorization_profile=AuthorizationProfile(
                required_actions=["mutate.create_object"],
                resource_mappings=[
                    ResourceMapping(
                        arg="path",
                        resource_role="target",
                        resource_type="file",
                        resource_pattern="file:*",
                    )
                ],
                effects=_write_effect(),
                output_anchor_fields=["output_id", "content_hash", "resource_ids"],
                commit_type="write_internal",
            ),
        )
    )
    reg.register(
        ToolManifest(
            tool_name="list_directory",
            operation="read",
            resource_arg="path",
            resource_type="file",
            resource_pattern="file:*",
            output_anchor_fields=["output_id", "content_hash", "resource_ids"],
            authorization_effect="read_only",
            commit_type="read",
            authorization_profile=AuthorizationProfile(
                required_actions=["acquire.read_metadata"],
                resource_mappings=[
                    ResourceMapping(
                        arg="path",
                        resource_role="target",
                        resource_type="file",
                        resource_pattern="file:*",
                    )
                ],
                effects=_read_effect(produces_anchor=True),
                output_anchor_fields=["output_id", "content_hash", "resource_ids"],
                commit_type="read",
            ),
        )
    )
    reg.register(
        ToolManifest(
            tool_name="search_files",
            operation="read",
            resource_arg="path",
            resource_type="file",
            resource_pattern="file:*",
            output_anchor_fields=["output_id", "content_hash", "resource_ids"],
            authorization_effect="read_only",
            commit_type="read",
            authorization_profile=AuthorizationProfile(
                required_actions=["acquire.search_collection"],
                resource_mappings=[
                    ResourceMapping(
                        arg="path",
                        resource_role="target",
                        resource_type="file",
                        resource_pattern="file:*",
                    )
                ],
                effects=_read_effect(),
                output_anchor_fields=["output_id", "content_hash", "resource_ids"],
                commit_type="read",
            ),
        )
    )
    reg.register(
        ToolManifest(
            tool_name="read_multiple_files",
            operation="read",
            resource_arg="paths",
            resource_type="file",
            resource_pattern="file:*",
            output_anchor_fields=["output_id", "content_hash", "resource_ids"],
            authorization_effect="read_only",
            commit_type="read",
            authorization_profile=AuthorizationProfile(
                required_actions=["acquire.read_object"],
                resource_mappings=[
                    ResourceMapping(
                        arg="paths",
                        resource_role="target",
                        resource_type="file",
                        resource_pattern="file:*",
                    )
                ],
                effects=_read_effect(),
                output_anchor_fields=["output_id", "content_hash", "resource_ids"],
                commit_type="read",
            ),
        )
    )
    return reg


class SandboxResourceMapper:
    """Maps paths under ``sandbox_root`` to stable RAC resource ids for grant scope checks."""

    def __init__(self, sandbox_root: Path) -> None:
        self.sandbox_root = sandbox_root.resolve()

    def _abs(self, path_str: str | Path) -> Path:
        p = Path(path_str)
        if not p.is_absolute():
            p = (self.sandbox_root / p).resolve()
        return p.resolve()

    def path_to_resource_ids(self, path_str: str) -> set[str]:
        abs_p = self._abs(path_str)
        try:
            rel = abs_p.relative_to(self.sandbox_root)
        except ValueError as exc:
            raise EventConstructionError(f"path outside sandbox ({self.sandbox_root}): {path_str}") from exc
        key = str(rel).replace("\\", "/").lstrip("./")
        if key == "file_A.txt":
            return {"file_A"}
        if key == "file_B.txt":
            return {"file_B"}
        if key in ("out/leak.txt", "out/leak2.txt"):
            return {"file_out_leak"}
        if key in ("", "."):
            return {"dir_root"}
        if key == "out":
            return {"dir_out"}
        raise EventConstructionError(
            f"unmapped sandbox-relative path for RAC demo (extend SandboxResourceMapper): {key!r}"
        )

    def paths_to_resource_ids(self, paths: list[str]) -> set[str]:
        out: set[str] = set()
        for p in paths:
            out.update(self.path_to_resource_ids(p))
        return out

    def resource_scope_ids_for_call(self, pending: PendingToolCall, manifest_resource_arg: str) -> set[str]:
        args = pending.arguments
        tool = pending.tool_name
        if tool in ("read_file", "write_file", "list_directory"):
            raw = args.get(manifest_resource_arg) or args.get("file_path") or args.get("directory")
            if raw is None:
                raise EventConstructionError(f"missing path-like argument for tool {tool!r}")
            if isinstance(raw, str):
                return self.path_to_resource_ids(raw)
            raise EventConstructionError(f"path argument must be str for {tool}")
        if tool == "search_files":
            raw = (
                args.get(manifest_resource_arg)
                or args.get("path")
                or args.get("directory")
                or args.get("rootPath")
            )
            if raw is None:
                raw = str(self.sandbox_root)
            if isinstance(raw, str):
                return self.path_to_resource_ids(raw)
            raise EventConstructionError("search_files path-like argument must be str")
        if tool == "read_multiple_files":
            paths_val = args.get("paths") or args.get("files")
            if paths_val is None:
                raise EventConstructionError("read_multiple_files requires paths/files array")
            if not isinstance(paths_val, list) or not paths_val:
                raise EventConstructionError("paths/files must be a non-empty list")
            strs = [str(x) for x in paths_val]
            return self.paths_to_resource_ids(strs)
        raise EventConstructionError(f"unsupported tool for sandbox mapper: {tool}")


class FilesystemEventAdapter(EventAdapter):
    """Event adapter that resolves filesystem paths under a sandbox to grant resource ids."""

    def __init__(
        self,
        *,
        sandbox_mapper: SandboxResourceMapper,
        manifest_registry: InMemoryToolManifestRegistry,
        resource_registry: InMemoryResourceRegistry,
        lineage_store: InMemoryCausalLineageStore,
        action_semantics_registry: ActionSemanticsRegistry | None = None,
    ) -> None:
        super().__init__(
            manifest_registry=manifest_registry,
            resource_registry=resource_registry,
            lineage_store=lineage_store,
            action_semantics_registry=action_semantics_registry,
        )
        self._sandbox_mapper = sandbox_mapper

    def _build_resource_scope(
        self,
        pending_tool_call: PendingToolCall,
        runtime_trace_context: RuntimeTraceContext,
        manifest_resource_arg: str,
        manifest_resource_type: str,
    ) -> TypedEventResourceScope:
        if manifest_resource_arg == "input_anchor":
            return super()._build_resource_scope(
                pending_tool_call,
                runtime_trace_context,
                manifest_resource_arg,
                manifest_resource_type,
            )
        ids = self._sandbox_mapper.resource_scope_ids_for_call(pending_tool_call, manifest_resource_arg)
        try:
            self.resource_registry.validate_resource_ids(ids, expected_type=manifest_resource_type)
        except ValueError as exc:
            raise EventConstructionError(str(exc)) from exc
        return TypedEventResourceScope(type=manifest_resource_type, ids=ids)


def build_fs_resource_registry() -> InMemoryResourceRegistry:
    reg = InMemoryResourceRegistry()
    for rid in ("file_A", "file_B", "file_out_leak", "dir_root", "dir_out"):
        reg.register(ResourceMetadata(resource_id=rid, resource_type="file"))
    return reg


@dataclass
class FilesystemMCPIntent:
    step_id: str
    step_seq: int
    tool_name: str
    arguments: dict[str, Any]
    selected_purpose: str | None = None
    input_anchor: str | None = None


class RealFilesystemRACAdapter:
    """Wires sandbox mapping, manifests, and RAC EventAdapter for filesystem MCP tools."""

    def __init__(
        self,
        *,
        sandbox_root: Path,
        grant_envelope: GrantEnvelope,
        lineage_store: InMemoryCausalLineageStore,
        action_semantics_registry: ActionSemanticsRegistry | None = None,
    ) -> None:
        self.sandbox_root = sandbox_root.resolve()
        self.grant_envelope = grant_envelope
        self.mapper = SandboxResourceMapper(self.sandbox_root)
        self.resource_registry = build_fs_resource_registry()
        self.manifest_registry = build_fs_manifest_registry()
        sem = action_semantics_registry or ActionSemanticsRegistry.load_from_yaml(default_semantics_yaml_path())
        self.action_semantics_registry = sem
        self.event_adapter = FilesystemEventAdapter(
            sandbox_mapper=self.mapper,
            manifest_registry=self.manifest_registry,
            resource_registry=self.resource_registry,
            lineage_store=lineage_store,
            action_semantics_registry=sem,
        )

    def build_pending_call(self, intent: FilesystemMCPIntent) -> PendingToolCall:
        return PendingToolCall(tool_name=intent.tool_name, arguments=dict(intent.arguments))

    def build_runtime_trace(self, intent: FilesystemMCPIntent, session_context: SessionContext) -> RuntimeTraceContext:
        anchors: list[InputAnchorRef] = []
        if intent.input_anchor:
            anchors.append(InputAnchorRef(anchor_id=intent.input_anchor))

        return RuntimeTraceContext(
            session_id=session_context.session_id,
            step_id=intent.step_id,
            step_seq=intent.step_seq,
            input_anchors=anchors,
            selected_purpose=intent.selected_purpose,
            observed_time=datetime.now(),
            environment=self.grant_envelope.conditions.environment or "trusted_workspace",
            tenant=session_context.tenant or self.grant_envelope.conditions.tenant,
            runtime_labels=set(self.grant_envelope.conditions.runtime_labels),
        )


REQUIRED_SERVER_TOOLS_FOR_DEMO = frozenset({"read_file", "write_file"})


def validate_required_tools_present(server_tool_names: list[str]) -> None:
    missing = REQUIRED_SERVER_TOOLS_FOR_DEMO - set(server_tool_names)
    if missing:
        raise ValueError(
            "Filesystem MCP server is missing tools required by this demo. "
            f"Missing: {sorted(missing)}. Server offered: {sorted(server_tool_names)}"
        )
