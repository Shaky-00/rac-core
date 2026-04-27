from rac_core.models import ToolManifest


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


def build_default_manifest_registry() -> InMemoryToolManifestRegistry:
    registry = InMemoryToolManifestRegistry()
    registry.register(
        ToolManifest(
            tool_name="read_file",
            operation="read",
            resource_arg="file_id",
            resource_type="file",
            resource_pattern="file:*",
            output_anchor_fields=["output_id", "content_hash", "resource_ids"],
            authorization_effect="read_only",
            commit_type="read",
        )
    )
    registry.register(
        ToolManifest(
            tool_name="summarize_file",
            operation="summarize",
            resource_arg="input_anchor",
            resource_type="derived_content",
            resource_pattern="anchor:*",
            output_anchor_fields=["output_id", "content_hash", "source_resource_ids"],
            authorization_effect="derived_read",
            commit_type="compute",
        )
    )
    registry.register(
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
    registry.register(
        ToolManifest(
            tool_name="search_documents",
            operation="read",
            resource_arg="results",
            resource_type="file",
            resource_pattern="file:*",
            output_anchor_fields=["output_id", "content_hash", "resource_ids"],
            authorization_effect="read_only",
            commit_type="read",
        )
    )
    registry.register(
        ToolManifest(
            tool_name="create_file",
            operation="write",
            resource_arg="file_path",
            resource_type="file",
            resource_pattern="file:*",
            output_anchor_fields=["output_id", "content_hash", "resource_ids"],
            authorization_effect="write_local",
            commit_type="write",
        )
    )
    return registry
