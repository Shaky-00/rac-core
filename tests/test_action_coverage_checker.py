from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from rac_core.action_semantics import (
    ActionSemanticsRegistry,
    action_covered,
    all_actions_covered,
    default_semantics_yaml_path,
)


@pytest.fixture
def reg() -> ActionSemanticsRegistry:
    return ActionSemanticsRegistry.load_from_yaml(default_semantics_yaml_path())


def test_summarize_not_covered_by_query_collection(reg: ActionSemanticsRegistry) -> None:
    assert not action_covered(
        "transform.summarize",
        {"acquire.query_collection"},
        reg,
    )


def test_send_message_not_covered_by_summarize(reg: ActionSemanticsRegistry) -> None:
    assert not action_covered(
        "disclose.send_message",
        {"transform.summarize"},
        reg,
    )


def test_required_leq_allowed_covers(reg: ActionSemanticsRegistry) -> None:
    assert action_covered(
        "meta.describe_tool",
        {"meta.inspect_status"},
        reg,
    )


def test_reverse_order_does_not_cover(reg: ActionSemanticsRegistry) -> None:
    assert not action_covered(
        "meta.inspect_status",
        {"meta.describe_tool"},
        reg,
    )


def test_deployment_edge_off_clear_cache_not_covered_by_delete(reg: ActionSemanticsRegistry) -> None:
    assert not action_covered("mutate.clear_cache", {"mutate.delete_object"}, reg)


def test_deployment_edge_on_allows_coverage(tmp_path: Path) -> None:
    base = yaml.safe_load(default_semantics_yaml_path().read_text(encoding="utf-8"))
    for dep in base["deployment_specific_edges"]:
        if dep["from"] == "mutate.clear_cache":
            dep["enabled"] = True
    p = tmp_path / "s.yaml"
    p.write_text(yaml.safe_dump(base, sort_keys=False), encoding="utf-8")
    r = ActionSemanticsRegistry.load_from_yaml(p)
    assert action_covered("mutate.clear_cache", {"mutate.delete_object"}, r)


def test_all_required_must_be_covered(reg: ActionSemanticsRegistry) -> None:
    allowed = {"meta.inspect_status", "transform.summarize"}
    required = ["meta.describe_tool", "transform.extract_field"]
    assert all_actions_covered(required, allowed, reg)


def test_any_missing_required_fails(reg: ActionSemanticsRegistry) -> None:
    allowed = {"meta.inspect_status"}  # covers describe_tool only
    required = ["meta.describe_tool", "transform.extract_field"]
    assert not all_actions_covered(required, allowed, reg)


def test_self_equality_in_allowed(reg: ActionSemanticsRegistry) -> None:
    assert action_covered("transform.summarize", {"transform.summarize"}, reg)


def test_allowed_labels_must_be_leaves_not_categories(reg: ActionSemanticsRegistry) -> None:
    with pytest.raises(ValueError, match="leaf action labels"):
        action_covered("meta.describe_tool", {"meta"}, reg)
