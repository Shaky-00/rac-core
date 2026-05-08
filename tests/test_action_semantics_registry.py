from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from rac_core.action_semantics import (
    ActionSemanticsRegistry,
    default_semantics_yaml_path,
)
from rac_core.action_semantics.partial_order import PartialOrderGraph
from rac_core.action_semantics.taxonomy import CANONICAL_CATEGORY_PREFIXES


@pytest.fixture
def default_registry() -> ActionSemanticsRegistry:
    return ActionSemanticsRegistry.load_from_yaml(default_semantics_yaml_path())


def test_default_yaml_loads(default_registry: ActionSemanticsRegistry) -> None:
    assert default_registry.leaf_labels
    assert default_registry.category_labels == frozenset(CANONICAL_CATEGORY_PREFIXES)


def test_all_taxonomy_leaf_labels_recognized(default_registry: ActionSemanticsRegistry) -> None:
    raw = yaml.safe_load(default_semantics_yaml_path().read_text(encoding="utf-8"))
    for _cat, leaves in raw["taxonomy"].items():
        for leaf in leaves:
            assert default_registry.is_leaf_action(leaf)
            default_registry.validate_action_label(leaf)


def test_validate_action_label_accepts_categories(default_registry: ActionSemanticsRegistry) -> None:
    for c in default_registry.category_labels:
        assert default_registry.is_category(c)
        default_registry.validate_action_label(c)


def test_category_cannot_be_required_action(default_registry: ActionSemanticsRegistry) -> None:
    with pytest.raises(ValueError, match="Category label"):
        default_registry.validate_required_actions(["meta"])


def test_unknown_label_rejected(default_registry: ActionSemanticsRegistry) -> None:
    with pytest.raises(ValueError, match="Unknown"):
        default_registry.validate_action_label("not_a_real.leaf")


def test_self_reflexive_order(default_registry: ActionSemanticsRegistry) -> None:
    leaf = next(iter(default_registry.leaf_labels))
    assert default_registry.is_no_more_permissive(leaf, leaf)


def test_default_partial_order_reachability(default_registry: ActionSemanticsRegistry) -> None:
    # meta.describe_tool <= meta.inspect_status
    assert default_registry.is_no_more_permissive(
        "meta.describe_tool", "meta.inspect_status"
    )
    # transitive acquire chain
    assert default_registry.is_no_more_permissive(
        "acquire.read_metadata", "acquire.search_collection"
    )
    # execute.trigger_job <= execute.run_command via run_code
    assert default_registry.is_no_more_permissive(
        "execute.trigger_job", "execute.run_command"
    )


def test_unlisted_pair_incomparable(default_registry: ActionSemanticsRegistry) -> None:
    a, b = "meta.describe_tool", "acquire.read_metadata"
    assert not default_registry.is_no_more_permissive(a, b)
    assert not default_registry.is_no_more_permissive(b, a)


def test_get_reachable_supersets(default_registry: ActionSemanticsRegistry) -> None:
    up = default_registry.get_reachable_supersets("execute.trigger_job")
    assert "execute.trigger_job" in up
    assert "execute.run_code" in up
    assert "execute.run_command" in up
    assert "execute.deploy_service" in up


def test_deployment_specific_edge_default_off(default_registry: ActionSemanticsRegistry) -> None:
    assert not default_registry.is_no_more_permissive("mutate.clear_cache", "mutate.delete_object")
    assert not default_registry.is_no_more_permissive(
        "authority.configure_runtime", "authority.manage_credential"
    )
    assert not default_registry.is_no_more_permissive(
        "transaction.create_shipment", "transaction.place_order"
    )


def test_deployment_specific_edge_enabled_in_yaml(tmp_path: Path) -> None:
    base = yaml.safe_load(default_semantics_yaml_path().read_text(encoding="utf-8"))
    for dep in base["deployment_specific_edges"]:
        if dep["from"] == "mutate.clear_cache":
            dep["enabled"] = True
    path = tmp_path / "sem.yaml"
    path.write_text(yaml.safe_dump(base, sort_keys=False), encoding="utf-8")
    reg = ActionSemanticsRegistry.load_from_yaml(path)
    assert reg.is_no_more_permissive("mutate.clear_cache", "mutate.delete_object")


def test_validate_required_actions_unknown_leaf(default_registry: ActionSemanticsRegistry) -> None:
    with pytest.raises(ValueError, match="Unknown or non-leaf"):
        default_registry.validate_required_actions(["zzzz.not_registered"])


def test_partial_order_graph_validate_unknown() -> None:
    g = PartialOrderGraph({"x", "y"})
    with pytest.raises(ValueError, match="Unknown"):
        g.validate_no_unknown_labels(["z"])
