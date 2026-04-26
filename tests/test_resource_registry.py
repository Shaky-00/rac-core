import pytest

from rac_core.models import ResourceMetadata
from rac_core.registry import InMemoryResourceRegistry


def test_register_and_get_resource_metadata() -> None:
    registry = InMemoryResourceRegistry()
    resource = ResourceMetadata(resource_id="file_A", resource_type="file")
    registry.register(resource)
    assert registry.get("file_A") == resource


def test_register_duplicate_resource_id_fails() -> None:
    registry = InMemoryResourceRegistry()
    resource = ResourceMetadata(resource_id="file_A", resource_type="file")
    registry.register(resource)
    with pytest.raises(ValueError):
        registry.register(resource)


def test_validate_resource_success_when_type_matches() -> None:
    registry = InMemoryResourceRegistry()
    resource = ResourceMetadata(resource_id="file_A", resource_type="file")
    registry.register(resource)
    validated = registry.validate_resource("file_A", expected_type="file")
    assert validated == resource


def test_validate_resource_unknown_fails() -> None:
    registry = InMemoryResourceRegistry()
    with pytest.raises(ValueError):
        registry.validate_resource("file_unknown")


def test_validate_resource_type_mismatch_fails() -> None:
    registry = InMemoryResourceRegistry()
    registry.register(ResourceMetadata(resource_id="file_A", resource_type="file"))
    with pytest.raises(ValueError):
        registry.validate_resource("file_A", expected_type="external_channel")


def test_validate_resource_ids_batch_success() -> None:
    registry = InMemoryResourceRegistry()
    registry.register(ResourceMetadata(resource_id="file_A", resource_type="file"))
    registry.register(ResourceMetadata(resource_id="file_B", resource_type="file"))
    validated = registry.validate_resource_ids({"file_A", "file_B"}, expected_type="file")
    assert len(validated) == 2
