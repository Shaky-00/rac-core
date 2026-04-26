from pydantic import BaseModel, Field


class ResourceMetadata(BaseModel):
    resource_id: str = Field(min_length=1)
    resource_type: str = Field(min_length=1)
    owner: str | None = None
    tenant: str | None = None
    sensitivity_label: str | None = None
    labels: set[str] = Field(default_factory=set)
    tags: set[str] = Field(default_factory=set)
    metadata: dict[str, object] = Field(default_factory=dict)
