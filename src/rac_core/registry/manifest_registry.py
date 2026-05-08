from __future__ import annotations

from pathlib import Path

import yaml

from rac_core.models import (
    AuthorizationProfile,
    EffectProfile,
    ResourceMapping,
    ToolManifest,
)

_SAMPLE_TOOL_MANIFESTS = (
    Path(__file__).resolve().parents[3] / "configs" / "sample_tool_manifests.yaml"
)


class InMemoryToolManifestRegistry:
    def __init__(self) -> None:
        self._manifests: dict[str, ToolManifest] = {}

    def register(self, manifest: ToolManifest) -> None:
        if manifest.tool_name in self._manifests:
            raise ValueError(f"Manifest already exists for tool_name={manifest.tool_name}.")
        self._manifests[manifest.tool_name] = manifest

    def get(self, tool_name: str) -> ToolManifest | None:
        return self._manifests.get(tool_name)

    def load(self, tool_name: str) -> ToolManifest:
        manifest = self.get(tool_name)
        if manifest is None:
            raise ValueError(f"Unknown tool manifest: {tool_name}")
        return manifest

    def contains(self, tool_name: str) -> bool:
        return tool_name in self._manifests

    def list_tool_names(self) -> list[str]:
        return sorted(self._manifests.keys())


def _extra_registry_tools() -> list[ToolManifest]:
    """Tools referenced by demos/tests but not defined in ``sample_tool_manifests.yaml``."""
    internal_read_effects = EffectProfile(
        state_mutation=False,
        external_disclosure=False,
        authority_change=False,
        real_world_effect=False,
        consumes_anchor=False,
        produces_anchor=True,
        effect_boundary="internal",
    )
    internal_write_effects = EffectProfile(
        state_mutation=True,
        external_disclosure=False,
        authority_change=False,
        real_world_effect=False,
        consumes_anchor=False,
        produces_anchor=True,
        effect_boundary="internal",
    )
    return [
        ToolManifest(
            tool_name="search_documents",
            operation="read",
            resource_arg="results",
            resource_type="file",
            resource_pattern="file:*",
            output_anchor_fields=["output_id", "content_hash", "resource_ids"],
            authorization_effect="read_only",
            commit_type="read",
            authorization_profile=AuthorizationProfile(
                required_actions=["acquire.query_collection"],
                resource_mappings=[
                    ResourceMapping(
                        arg="results",
                        resource_role="target",
                        resource_type="file",
                        resource_pattern="file:*",
                    )
                ],
                effects=internal_read_effects,
                output_anchor_fields=["output_id", "content_hash", "resource_ids"],
                commit_type="read",
            ),
        ),
        ToolManifest(
            tool_name="create_file",
            operation="write",
            resource_arg="file_path",
            resource_type="file",
            resource_pattern="file:*",
            output_anchor_fields=["output_id", "content_hash", "resource_ids"],
            authorization_effect="write_local",
            commit_type="write",
            authorization_profile=AuthorizationProfile(
                required_actions=["mutate.create_object"],
                resource_mappings=[
                    ResourceMapping(
                        arg="file_path",
                        resource_role="target",
                        resource_type="file",
                        resource_pattern="file:*",
                    )
                ],
                effects=internal_write_effects,
                output_anchor_fields=["output_id", "content_hash", "resource_ids"],
                commit_type="write",
            ),
        ),
    ]


def build_default_manifest_registry() -> InMemoryToolManifestRegistry:
    """Load canonical v0.6 sample manifests plus a few extra tools used by older demos."""
    registry = InMemoryToolManifestRegistry()
    with open(_SAMPLE_TOOL_MANIFESTS, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    for _name, spec in raw["tools"].items():
        registry.register(ToolManifest.model_validate(spec))
    for m in _extra_registry_tools():
        registry.register(m)
    return registry
