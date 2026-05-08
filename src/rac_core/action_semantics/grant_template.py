"""Grant templates and compiled grant profiles (v0.6 authoring-time expansion).

Templates are expanded by a trusted :class:`GrantProfileExpander` into a
:class:`CompiledGrantProfile` before runtime checks. This module does **not**
attach profiles to :class:`~rac_core.models.grant.GrantEnvelope` yet.

Note: Default YAML paths use ``Path(__file__).parents[3]`` (repo layout with
``src/rac_core/...``). Installed wheels without repo-relative ``configs/`` need
callers to pass explicit paths or a future ``importlib.resources`` / package_data
layout (follow-up).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from rac_core.action_semantics.registry import ActionSemanticsRegistry


class GrantTemplateError(Exception):
    """Base error for grant template loading and expansion."""


class UnknownGrantTemplateError(GrantTemplateError):
    """Referenced ``template_id`` is not registered."""


class InvalidGrantTemplateError(GrantTemplateError):
    """Template YAML or semantic content is invalid."""


class GrantTemplateConflictError(GrantTemplateError):
    """Conflicting values when merging templates (conditions or delegation)."""


class GrantTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: str = Field(min_length=1)
    actions: list[str] = Field(min_length=1)
    purpose_constraints: list[str] = Field(default_factory=list)
    conditions: dict[str, Any] = Field(default_factory=dict)
    delegation: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None


class CompiledGrantProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_templates: list[str]
    allowed_action_labels: list[str]
    purpose_scope: list[str]
    conditions: dict[str, Any]
    delegation: dict[str, Any]


def default_grant_templates_yaml_path() -> Path:
    """Default bundled grant-templates path (repo-root ``configs/``)."""
    return Path(__file__).resolve().parents[3] / "configs" / "default_grant_templates.yaml"


class GrantProfileExpander:
    """Loads grant templates from YAML and expands them using :class:`ActionSemanticsRegistry`."""

    __slots__ = ("_templates", "_registry")

    def __init__(
        self,
        templates: dict[str, GrantTemplate],
        registry: ActionSemanticsRegistry,
    ) -> None:
        self._templates = dict(templates)
        self._registry = registry

    @classmethod
    def load_from_root_mapping(
        cls,
        root: dict[str, Any],
        action_semantics_registry: ActionSemanticsRegistry,
    ) -> GrantProfileExpander:
        if not isinstance(root, dict):
            raise InvalidGrantTemplateError("YAML root must be a mapping.")
        block = root.get("templates")
        if not isinstance(block, dict):
            raise InvalidGrantTemplateError("Missing top-level `templates` mapping.")

        expander = cls({}, action_semantics_registry)
        loaded: dict[str, GrantTemplate] = {}
        for template_id, body in block.items():
            if not isinstance(template_id, str) or not template_id:
                raise InvalidGrantTemplateError(f"Invalid template id key: {template_id!r}")
            if not isinstance(body, dict):
                raise InvalidGrantTemplateError(
                    f"Template {template_id!r} body must be a mapping, got {type(body).__name__}"
                )
            tmpl = GrantTemplate(
                template_id=template_id,
                actions=list(body.get("actions") or []),
                purpose_constraints=list(body.get("purpose_constraints") or []),
                conditions=dict(body.get("conditions") or {}),
                delegation=dict(body.get("delegation") or {}),
                description=body.get("description"),
            )
            expander.validate_template(tmpl)
            loaded[template_id] = tmpl

        expander._templates = loaded
        return expander

    @classmethod
    def load_from_yaml(
        cls, path: str | Path, action_semantics_registry: ActionSemanticsRegistry
    ) -> GrantProfileExpander:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls.load_from_root_mapping(raw, action_semantics_registry)

    def list_templates(self) -> list[str]:
        """All registered ``template_id`` values (YAML insertion order)."""
        return list(self._templates.keys())

    def get_template(self, template_id: str) -> GrantTemplate:
        if template_id not in self._templates:
            raise UnknownGrantTemplateError(f"Unknown grant template: {template_id!r}")
        return self._templates[template_id]

    def validate_template(self, template: GrantTemplate) -> None:
        """Ensure actions are registered leaf labels (never category or unknown)."""
        try:
            self._registry.validate_required_actions(template.actions)
        except ValueError as exc:
            raise InvalidGrantTemplateError(
                f"Template {template.template_id!r} has invalid actions: {exc}"
            ) from exc

    def expand_templates(
        self,
        template_ids: list[str],
        explicit_constraints: dict[str, Any] | None = None,
    ) -> CompiledGrantProfile:
        """Union templates into a compiled profile (conditions/delegation merged with conflict checks).

        ``explicit_constraints`` is reserved for later phases; it is accepted but not merged.
        """
        _ = explicit_constraints  # reserved for v0.6 follow-up override semantics

        if not template_ids:
            raise InvalidGrantTemplateError("template_ids must be a non-empty list.")

        for tid in template_ids:
            if tid not in self._templates:
                raise UnknownGrantTemplateError(f"Unknown grant template: {tid!r}")

        allowed_ordered: list[str] = []
        seen_actions: set[str] = set()
        purpose_ordered: list[str] = []
        seen_purpose: set[str] = set()
        merged_conditions: dict[str, Any] = {}
        merged_delegation: dict[str, Any] = {}

        for tid in template_ids:
            t = self._templates[tid]
            for action in t.actions:
                if action not in seen_actions:
                    seen_actions.add(action)
                    allowed_ordered.append(action)
            for p in t.purpose_constraints:
                if p not in seen_purpose:
                    seen_purpose.add(p)
                    purpose_ordered.append(p)
            self._merge_mapping(
                merged_conditions,
                t.conditions,
                context=f"conditions for template {tid!r}",
            )
            self._merge_mapping(
                merged_delegation,
                t.delegation,
                context=f"delegation for template {tid!r}",
            )

        return CompiledGrantProfile(
            source_templates=list(template_ids),
            allowed_action_labels=allowed_ordered,
            purpose_scope=purpose_ordered,
            conditions=merged_conditions,
            delegation=merged_delegation,
        )

    def _merge_mapping(
        self,
        target: dict[str, Any],
        incoming: dict[str, Any],
        *,
        context: str,
    ) -> None:
        for key, value in incoming.items():
            if key in target and target[key] != value:
                raise GrantTemplateConflictError(
                    f"Conflict merging {context} on key {key!r}: "
                    f"existing {target[key]!r} vs incoming {value!r}"
                )
            target[key] = value
