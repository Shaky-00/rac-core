from pydantic import BaseModel, Field


class VerifiedStructuredOutputAnchor(BaseModel):
    anchor_id: str = Field(min_length=1)
    producer_event_id: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    resource_ids: set[str] = Field(default_factory=set)
    output_type: str | None = None
    schema_version: str = "v1"
    verified_by_controller: bool = False
    session_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
