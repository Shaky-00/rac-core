from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from rac_core.action_semantics import (
    ActionSemanticsRegistry,
    GrantProfileExpander,
    GrantTemplateConflictError,
    InvalidGrantTemplateError,
    UnknownGrantTemplateError,
    default_grant_templates_yaml_path,
    default_semantics_yaml_path,
)


@pytest.fixture
def registry() -> ActionSemanticsRegistry:
    return ActionSemanticsRegistry.load_from_yaml(default_semantics_yaml_path())


@pytest.fixture
def expander(registry: ActionSemanticsRegistry) -> GrantProfileExpander:
    return GrantProfileExpander.load_from_yaml(
        default_grant_templates_yaml_path(), registry
    )


def test_default_grant_templates_yaml_loads(expander: GrantProfileExpander) -> None:
    assert expander.list_templates()


def test_list_templates_all_defaults(expander: GrantProfileExpander) -> None:
    names = expander.list_templates()
    assert len(names) == 12
    assert set(names) == {
        "tool_inspection",
        "read_only_retrieval",
        "search_and_retrieval",
        "internal_analysis",
        "internal_artifact_generation",
        "internal_analysis_full",
        "internal_state_management",
        "external_disclosure_limited",
        "public_publication",
        "authority_administration",
        "execution_operation",
        "transaction_operation",
    }


def test_internal_analysis_allowed_actions(expander: GrantProfileExpander) -> None:
    p = expander.expand_templates(["internal_analysis"])
    assert p.allowed_action_labels == [
        "acquire.read_metadata",
        "acquire.read_object",
        "acquire.query_collection",
        "transform.extract_field",
        "transform.summarize",
        "transform.classify_score",
        "transform.aggregate_compare",
    ]
    assert p.purpose_scope == ["internal_analysis"]
    assert p.conditions["state_mutation"] is False
    assert p.conditions["external_disclosure"] is False


def test_internal_analysis_full_includes_analysis_and_create(
    expander: GrantProfileExpander,
) -> None:
    p = expander.expand_templates(["internal_analysis_full"])
    assert "transform.summarize" in p.allowed_action_labels
    assert "mutate.create_object" in p.allowed_action_labels
    assert "transform.generate_artifact" in p.allowed_action_labels
    assert p.conditions["state_mutation"] == "limited_internal_create"
    assert p.conditions["produces_anchor"] is True


def test_read_only_retrieval_excludes_summarize(expander: GrantProfileExpander) -> None:
    p = expander.expand_templates(["read_only_retrieval"])
    assert "transform.summarize" not in p.allowed_action_labels


def test_external_disclosure_limited_actions(expander: GrantProfileExpander) -> None:
    p = expander.expand_templates(["external_disclosure_limited"])
    assert set(p.allowed_action_labels) == {
        "disclose.send_message",
        "disclose.upload_object",
        "disclose.call_webhook",
        "disclose.sync_to_external",
    }


def test_authority_administration_includes_policy_and_credential(
    expander: GrantProfileExpander,
) -> None:
    p = expander.expand_templates(["authority_administration"])
    assert "authority.update_policy" in p.allowed_action_labels
    assert "authority.manage_credential" in p.allowed_action_labels


def test_multi_template_action_union_order_and_dedupe(
    expander: GrantProfileExpander,
) -> None:
    p = expander.expand_templates(["tool_inspection", "read_only_retrieval"])
    assert p.allowed_action_labels == [
        "meta.describe_tool",
        "meta.inspect_status",
        "meta.list_capabilities",
        "acquire.read_metadata",
        "acquire.read_object",
        "acquire.query_collection",
    ]


def test_multi_template_purpose_union_order(registry: ActionSemanticsRegistry, tmp_path: Path) -> None:
    raw = {
        "templates": {
            "p_a": {
                "actions": ["meta.describe_tool"],
                "purpose_constraints": ["purpose_one"],
                "conditions": {"shared": True},
                "delegation": {},
            },
            "p_b": {
                "actions": ["meta.inspect_status"],
                "purpose_constraints": ["purpose_two"],
                "conditions": {"shared": True},
                "delegation": {},
            },
        }
    }
    path = tmp_path / "g.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    ex = GrantProfileExpander.load_from_yaml(path, registry)
    p = ex.expand_templates(["p_b", "p_a"])
    assert p.purpose_scope == ["purpose_two", "purpose_one"]


def test_multi_template_conditions_merge(registry: ActionSemanticsRegistry, tmp_path: Path) -> None:
    raw = {
        "templates": {
            "c_a": {
                "actions": ["meta.describe_tool"],
                "purpose_constraints": [],
                "conditions": {"a_only": 1, "shared": True},
                "delegation": {},
            },
            "c_b": {
                "actions": ["meta.inspect_status"],
                "purpose_constraints": [],
                "conditions": {"b_only": 2, "shared": True},
                "delegation": {},
            },
        }
    }
    path = tmp_path / "g.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    ex = GrantProfileExpander.load_from_yaml(path, registry)
    p = ex.expand_templates(["c_a", "c_b"])
    assert p.conditions == {"a_only": 1, "shared": True, "b_only": 2}


def test_condition_conflict_raises(registry: ActionSemanticsRegistry, tmp_path: Path) -> None:
    raw = {
        "templates": {
            "x1": {
                "actions": ["meta.describe_tool"],
                "purpose_constraints": [],
                "conditions": {"k": 1},
                "delegation": {},
            },
            "x2": {
                "actions": ["meta.list_capabilities"],
                "purpose_constraints": [],
                "conditions": {"k": 2},
                "delegation": {},
            },
        }
    }
    path = tmp_path / "g.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    ex = GrantProfileExpander.load_from_yaml(path, registry)
    with pytest.raises(GrantTemplateConflictError, match="Conflict"):
        ex.expand_templates(["x1", "x2"])


def test_unknown_action_in_yaml_rejected_on_load(registry: ActionSemanticsRegistry, tmp_path: Path) -> None:
    raw = {
        "templates": {
            "bad": {
                "actions": ["not.a.registered.leaf"],
                "purpose_constraints": [],
                "conditions": {},
                "delegation": {},
            },
        }
    }
    path = tmp_path / "g.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    with pytest.raises(InvalidGrantTemplateError, match="invalid actions"):
        GrantProfileExpander.load_from_yaml(path, registry)


def test_category_action_rejected_on_load(registry: ActionSemanticsRegistry, tmp_path: Path) -> None:
    raw = {
        "templates": {
            "bad": {
                "actions": ["meta"],
                "purpose_constraints": [],
                "conditions": {},
                "delegation": {},
            },
        }
    }
    path = tmp_path / "g.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    with pytest.raises(InvalidGrantTemplateError, match="invalid actions"):
        GrantProfileExpander.load_from_yaml(path, registry)


def test_unknown_template_id_in_expand(expander: GrantProfileExpander) -> None:
    with pytest.raises(UnknownGrantTemplateError, match="no_such_template"):
        expander.expand_templates(["internal_analysis", "no_such_template"])


def test_get_template_unknown(expander: GrantProfileExpander) -> None:
    with pytest.raises(UnknownGrantTemplateError):
        expander.get_template("missing")


def test_source_templates_match_input(expander: GrantProfileExpander) -> None:
    ids = ["read_only_retrieval", "search_and_retrieval"]
    p = expander.expand_templates(ids)
    assert p.source_templates == ids


def test_expand_accepts_explicit_constraints_parameter(
    expander: GrantProfileExpander,
) -> None:
    """Parameter is reserved; expansion must still succeed when passed."""
    p = expander.expand_templates(
        ["tool_inspection"],
        explicit_constraints={"future": True},
    )
    assert "business_data_access" in p.conditions
