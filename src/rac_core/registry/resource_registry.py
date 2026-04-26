from rac_core.models import ResourceMetadata


class InMemoryResourceRegistry:
    def __init__(self) -> None:
        self._resources: dict[str, ResourceMetadata] = {}

    def register(self, resource: ResourceMetadata) -> None:
        if resource.resource_id in self._resources:
            raise ValueError(f"Resource already exists: {resource.resource_id}")
        self._resources[resource.resource_id] = resource

    def get(self, resource_id: str) -> ResourceMetadata | None:
        return self._resources.get(resource_id)

    def contains(self, resource_id: str) -> bool:
        return resource_id in self._resources

    def validate_resource(
        self, resource_id: str, expected_type: str | None = None
    ) -> ResourceMetadata:
        resource = self.get(resource_id)
        if resource is None:
            raise ValueError(f"Unknown resource: {resource_id}")
        if expected_type is not None and resource.resource_type != expected_type:
            raise ValueError(
                f"Resource type mismatch for {resource_id}: "
                f"expected={expected_type}, actual={resource.resource_type}"
            )
        return resource

    def validate_resource_ids(
        self, resource_ids: set[str], expected_type: str | None = None
    ) -> list[ResourceMetadata]:
        return [
            self.validate_resource(resource_id=resource_id, expected_type=expected_type)
            for resource_id in sorted(resource_ids)
        ]
