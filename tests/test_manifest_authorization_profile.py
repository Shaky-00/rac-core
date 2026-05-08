from __future__ import annotations

from rac_core.action_semantics import ActionSemanticsRegistry, default_semantics_yaml_path
from rac_core.adapter import (
    load_tool_manifests_from_yaml,
    sample_tool_manifests_yaml_path,
    validate_tool_manifest,
)


def test_sample_tool_manifests_yaml_loads() -> None:
    manifests = load_tool_manifests_from_yaml(sample_tool_manifests_yaml_path())
    assert set(manifests.keys()) == {
        "read_file",
        "summarize_file",
        "compare_reports",
        "create_email_draft",
        "update_policy",
    }


def test_read_file_required_action() -> None:
    manifests = load_tool_manifests_from_yaml(sample_tool_manifests_yaml_path())
    p = manifests["read_file"].authorization_profile
    assert p is not None
    assert p.required_actions == ["acquire.read_object"]


def test_summarize_file_required_action() -> None:
    manifests = load_tool_manifests_from_yaml(sample_tool_manifests_yaml_path())
    p = manifests["summarize_file"].authorization_profile
    assert p is not None
    assert p.required_actions == ["transform.summarize"]


def test_compare_reports_multiple_required_actions() -> None:
    manifests = load_tool_manifests_from_yaml(sample_tool_manifests_yaml_path())
    p = manifests["compare_reports"].authorization_profile
    assert p is not None
    assert p.required_actions == [
        "acquire.query_collection",
        "transform.aggregate_compare",
    ]


def test_create_email_draft_external_disclosure_and_boundary() -> None:
    manifests = load_tool_manifests_from_yaml(sample_tool_manifests_yaml_path())
    p = manifests["create_email_draft"].authorization_profile
    assert p is not None
    assert p.effects.external_disclosure is True
    assert p.effects.effect_boundary == "external"


def test_update_policy_authority_change() -> None:
    manifests = load_tool_manifests_from_yaml(sample_tool_manifests_yaml_path())
    p = manifests["update_policy"].authorization_profile
    assert p is not None
    assert p.effects.authority_change is True


def test_sample_manifests_validate_with_registry() -> None:
    reg = ActionSemanticsRegistry.load_from_yaml(default_semantics_yaml_path())
    for m in load_tool_manifests_from_yaml(sample_tool_manifests_yaml_path()).values():
        validate_tool_manifest(m, reg)
