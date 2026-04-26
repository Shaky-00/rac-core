from pydantic import BaseModel, Field


class ToolManifest(BaseModel):
    tool_name: str = Field(min_length=1)
    operation: str = Field(min_length=1)
    resource_arg: str = Field(min_length=1)
    resource_type: str = Field(min_length=1)
    resource_pattern: str | None = None
    output_anchor_fields: list[str] = Field(default_factory=list)
    authorization_effect: str | None = None
    commit_type: str | None = None
