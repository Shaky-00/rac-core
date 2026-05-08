"""Validate v0.6 ``ToolManifest.authorization_profile`` against action semantics.

This module does **not** wire into :class:`~rac_core.checker.precommit.RACPreCommitChecker`
or :class:`~rac_core.adapter.event_adapter.EventAdapter`; callers opt in explicitly.
"""

from __future__ import annotations

from pathlib import Path
import yaml

from rac_core.action_semantics.registry import ActionSemanticsRegistry
from rac_core.models.manifest import AuthorizationProfile, ToolManifest


class ManifestProfileValidationError(Exception):
    """Raised when an ``AuthorizationProfile`` or manifest profile section is invalid."""


def sample_tool_manifests_yaml_path() -> Path:
    """Path to bundled sample manifests (repo-root ``configs/``).

    Same layout caveat as action-semantics defaults: wheel installs may need an
    explicit path until package_data / importlib.resources is adopted.
    """
    return Path(__file__).resolve().parents[3] / "configs" / "sample_tool_manifests.yaml"


def load_tool_manifests_from_yaml(path: str | Path) -> dict[str, ToolManifest]:
    """Load ``tools: { tool_id: { ... } }`` into ``ToolManifest`` instances (no validation)."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("YAML root must be a mapping.")
    tools = raw.get("tools")
    if not isinstance(tools, dict):
        raise ValueError("Missing top-level `tools` mapping.")
    out: dict[str, ToolManifest] = {}
    for key, body in tools.items():
        if not isinstance(body, dict):
            raise ValueError(f"Tool {key!r} must be a mapping.")
        out[str(key)] = ToolManifest.model_validate(body)
    return out


def validate_manifest_profile(
    profile: AuthorizationProfile,
    action_semantics_registry: ActionSemanticsRegistry,
) -> None:
    """Validate a non-null authorization profile (leaf actions, mappings, effects, anchors)."""
    if profile.effects is None:
        raise ManifestProfileValidationError("authorization_profile.effects is required.")

    if not profile.required_actions:
        raise ManifestProfileValidationError("authorization_profile.required_actions must be non-empty.")

    try:
        action_semantics_registry.validate_required_actions(list(profile.required_actions))
    except ValueError as exc:
        raise ManifestProfileValidationError(str(exc)) from exc

    for idx, mapping in enumerate(profile.resource_mappings):
        if not mapping.arg or not str(mapping.arg).strip():
            raise ManifestProfileValidationError(
                f"resource_mappings[{idx}].arg must be a non-empty string."
            )
        if not mapping.resource_role or not str(mapping.resource_role).strip():
            raise ManifestProfileValidationError(
                f"resource_mappings[{idx}].resource_role must be a non-empty string."
            )
        if not mapping.resource_type or not str(mapping.resource_type).strip():
            raise ManifestProfileValidationError(
                f"resource_mappings[{idx}].resource_type must be a non-empty string."
            )

    effects = profile.effects
    bool_fields = (
        "state_mutation",
        "external_disclosure",
        "authority_change",
        "real_world_effect",
        "consumes_anchor",
        "produces_anchor",
    )
    for name in bool_fields:
        val = getattr(effects, name)
        if not isinstance(val, bool):
            raise ManifestProfileValidationError(
                f"authorization_profile.effects.{name} must be a bool (got {type(val).__name__})."
            )

    boundary = (effects.effect_boundary or "").strip()
    if not boundary:
        raise ManifestProfileValidationError("authorization_profile.effects.effect_boundary must be non-empty.")

    commit = (profile.commit_type or "").strip()
    if not commit:
        raise ManifestProfileValidationError("authorization_profile.commit_type must be non-empty.")

    if effects.produces_anchor and not profile.output_anchor_fields:
        raise ManifestProfileValidationError(
            "When effects.produces_anchor is true, authorization_profile.output_anchor_fields must be non-empty."
        )

    if effects.consumes_anchor:
        has_input = any(
            str(m.resource_role).strip() == "input" for m in profile.resource_mappings
        )
        if not has_input:
            raise ManifestProfileValidationError(
                "When effects.consumes_anchor is true, resource_mappings must include at least one "
                "entry with resource_role 'input'."
            )


def validate_tool_manifest(
    manifest: ToolManifest,
    action_semantics_registry: ActionSemanticsRegistry,
) -> None:
    """If ``authorization_profile`` is set, validate it; otherwise accept coarse-only manifests."""
    if manifest.authorization_profile is None:
        return
    validate_manifest_profile(manifest.authorization_profile, action_semantics_registry)
