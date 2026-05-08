from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ResourceMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arg: str = Field(min_length=1)
    resource_role: str = Field(min_length=1)
    resource_type: str = Field(min_length=1)
    resource_pattern: str | None = None
    required: bool = True


class EffectProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_mutation: bool
    external_disclosure: bool
    authority_change: bool
    real_world_effect: bool
    consumes_anchor: bool
    produces_anchor: bool
    effect_boundary: str = Field(
        min_length=1,
        description="Recommended: internal | external | authority | real_world",
    )


class AuthorizationProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_actions: list[str] = Field(min_length=1)
    resource_mappings: list[ResourceMapping] = Field(default_factory=list)
    effects: EffectProfile
    output_anchor_fields: list[str] = Field(default_factory=list)
    commit_type: str = Field(min_length=1)


class ToolManifest(BaseModel):
    """Tool manifest: coarse descriptor fields plus optional v0.6 ``authorization_profile``."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1)
    operation: str = Field(min_length=1)
    resource_arg: str = Field(min_length=1)
    resource_type: str = Field(min_length=1)
    resource_pattern: str | None = None
    output_anchor_fields: list[str] = Field(default_factory=list)
    authorization_effect: str | None = None
    commit_type: str | None = None
    authorization_profile: AuthorizationProfile | None = None
