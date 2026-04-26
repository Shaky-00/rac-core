import pytest

from rac_core.models import ToolManifest
from rac_core.registry import (
    InMemoryToolManifestRegistry,
    build_default_manifest_registry,
)


def test_register_and_load_manifest() -> None:
    registry = InMemoryToolManifestRegistry()
    manifest = ToolManifest(
        tool_name="read_file",
        operation="read",
        resource_arg="file_id",
        resource_type="file",
    )
    registry.register(manifest)
    assert registry.load("read_file") == manifest


def test_register_duplicate_tool_name_fails() -> None:
    registry = InMemoryToolManifestRegistry()
    manifest = ToolManifest(
        tool_name="read_file",
        operation="read",
        resource_arg="file_id",
        resource_type="file",
    )
    registry.register(manifest)
    with pytest.raises(ValueError):
        registry.register(manifest)


def test_load_unknown_tool_name_fails() -> None:
    registry = InMemoryToolManifestRegistry()
    with pytest.raises(ValueError):
        registry.load("unknown_tool")


def test_build_default_manifest_registry_contains_minimal_tools() -> None:
    registry = build_default_manifest_registry()
    names = set(registry.list_tool_names())
    assert {"read_file", "summarize_file", "create_email_draft"} <= names


def test_default_read_file_operation_is_read() -> None:
    registry = build_default_manifest_registry()
    assert registry.load("read_file").operation == "read"


def test_default_create_email_draft_operation_is_external_disclosure() -> None:
    registry = build_default_manifest_registry()
    assert registry.load("create_email_draft").operation == "external_disclosure"
