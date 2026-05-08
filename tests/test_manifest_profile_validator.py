from __future__ import annotations

import pytest

from rac_core.action_semantics import ActionSemanticsRegistry, default_semantics_yaml_path
from rac_core.adapter import (
    ManifestProfileValidationError,
    validate_manifest_profile,
    validate_tool_manifest,
)
from rac_core.models import (
    AuthorizationProfile,
    EffectProfile,
    ResourceMapping,
    ToolManifest,
)


@pytest.fixture
def reg() -> ActionSemanticsRegistry:
    return ActionSemanticsRegistry.load_from_yaml(default_semantics_yaml_path())


def _valid_effects(**overrides: bool | str) -> EffectProfile:
    base = dict(
        state_mutation=False,
        external_disclosure=False,
        authority_change=False,
        real_world_effect=False,
        consumes_anchor=False,
        produces_anchor=True,
        effect_boundary="internal",
    )
    base.update(overrides)
    return EffectProfile(**base)  # type: ignore[arg-type]


def test_validate_manifest_profile_accepts_legal(reg: ActionSemanticsRegistry) -> None:
    profile = AuthorizationProfile(
        required_actions=["acquire.read_object"],
        resource_mappings=[
            ResourceMapping(
                arg="file_id",
                resource_role="target",
                resource_type="file",
                resource_pattern="file:*",
            )
        ],
        effects=_valid_effects(),
        output_anchor_fields=["output_id"],
        commit_type="read",
    )
    validate_manifest_profile(profile, reg)


def test_category_in_required_actions_rejected(reg: ActionSemanticsRegistry) -> None:
    profile = AuthorizationProfile(
        required_actions=["meta"],
        resource_mappings=[
            ResourceMapping(arg="x", resource_role="target", resource_type="file")
        ],
        effects=_valid_effects(),
        output_anchor_fields=["o"],
        commit_type="read",
    )
    with pytest.raises(ManifestProfileValidationError, match="Category label"):
        validate_manifest_profile(profile, reg)


def test_unknown_label_in_required_actions_rejected(reg: ActionSemanticsRegistry) -> None:
    profile = AuthorizationProfile(
        required_actions=["not.registered.leaf"],
        resource_mappings=[
            ResourceMapping(arg="x", resource_role="target", resource_type="file")
        ],
        effects=_valid_effects(),
        output_anchor_fields=["o"],
        commit_type="read",
    )
    with pytest.raises(ManifestProfileValidationError, match="Unknown or non-leaf"):
        validate_manifest_profile(profile, reg)


def test_empty_required_actions_rejected(reg: ActionSemanticsRegistry) -> None:
    profile = AuthorizationProfile.model_construct(
        required_actions=[],
        resource_mappings=[
            ResourceMapping(arg="x", resource_role="target", resource_type="file")
        ],
        effects=_valid_effects(),
        output_anchor_fields=["o"],
        commit_type="read",
    )
    with pytest.raises(ManifestProfileValidationError, match="non-empty"):
        validate_manifest_profile(profile, reg)


def test_resource_mapping_missing_arg(reg: ActionSemanticsRegistry) -> None:
    profile = AuthorizationProfile.model_construct(
        required_actions=["meta.describe_tool"],
        resource_mappings=[
            ResourceMapping.model_construct(
                arg="",
                resource_role="target",
                resource_type="file",
            )
        ],
        effects=_valid_effects(),
        output_anchor_fields=["o"],
        commit_type="read",
    )
    with pytest.raises(ManifestProfileValidationError, match="arg"):
        validate_manifest_profile(profile, reg)


def test_resource_mapping_missing_resource_type(reg: ActionSemanticsRegistry) -> None:
    profile = AuthorizationProfile.model_construct(
        required_actions=["meta.describe_tool"],
        resource_mappings=[
            ResourceMapping.model_construct(
                arg="f",
                resource_role="target",
                resource_type="",
            )
        ],
        effects=_valid_effects(),
        output_anchor_fields=["o"],
        commit_type="read",
    )
    with pytest.raises(ManifestProfileValidationError, match="resource_type"):
        validate_manifest_profile(profile, reg)


def test_missing_effects_rejected(reg: ActionSemanticsRegistry) -> None:
    profile = AuthorizationProfile.model_construct(
        required_actions=["meta.describe_tool"],
        resource_mappings=[
            ResourceMapping(arg="f", resource_role="target", resource_type="file")
        ],
        effects=None,
        output_anchor_fields=["o"],
        commit_type="read",
    )
    with pytest.raises(ManifestProfileValidationError, match="effects is required"):
        validate_manifest_profile(profile, reg)


def test_produces_anchor_requires_output_fields(reg: ActionSemanticsRegistry) -> None:
    profile = AuthorizationProfile(
        required_actions=["meta.describe_tool"],
        resource_mappings=[
            ResourceMapping(arg="f", resource_role="target", resource_type="file")
        ],
        effects=_valid_effects(produces_anchor=True),
        output_anchor_fields=[],
        commit_type="read",
    )
    with pytest.raises(ManifestProfileValidationError, match="output_anchor_fields"):
        validate_manifest_profile(profile, reg)


def test_consumes_anchor_requires_input_mapping(reg: ActionSemanticsRegistry) -> None:
    profile = AuthorizationProfile(
        required_actions=["transform.summarize"],
        resource_mappings=[
            ResourceMapping(arg="f", resource_role="target", resource_type="file")
        ],
        effects=_valid_effects(consumes_anchor=True, produces_anchor=True),
        output_anchor_fields=["o"],
        commit_type="compute",
    )
    with pytest.raises(ManifestProfileValidationError, match="input"):
        validate_manifest_profile(profile, reg)


def test_authorization_profile_none_coarse_manifest_ok(reg: ActionSemanticsRegistry) -> None:
    m = ToolManifest(
        tool_name="sample_coarse_tool",
        operation="read",
        resource_arg="rid",
        resource_type="file",
        authorization_profile=None,
    )
    validate_tool_manifest(m, reg)


def test_effects_bool_type_enforced(reg: ActionSemanticsRegistry) -> None:
    profile = AuthorizationProfile.model_construct(
        required_actions=["meta.describe_tool"],
        resource_mappings=[
            ResourceMapping(arg="f", resource_role="target", resource_type="file")
        ],
        effects=EffectProfile.model_construct(
            state_mutation="not-a-bool",  # type: ignore[arg-type]
            external_disclosure=False,
            authority_change=False,
            real_world_effect=False,
            consumes_anchor=False,
            produces_anchor=True,
            effect_boundary="internal",
        ),
        output_anchor_fields=["o"],
        commit_type="read",
    )
    with pytest.raises(ManifestProfileValidationError, match="state_mutation"):
        validate_manifest_profile(profile, reg)
