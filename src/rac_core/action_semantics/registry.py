"""Configurable ActionSemanticsRegistry (v0.6) backed by YAML."""

from __future__ import annotations

from pathlib import Path
import yaml

from rac_core.action_semantics.partial_order import PartialOrderGraph


class ActionSemanticsRegistry:
    """Loads leaf taxonomy, category labels, and a partial order over leaves."""

    __slots__ = ("_categories", "_leaves", "_graph")

    def __init__(
        self,
        *,
        categories: frozenset[str],
        leaves: frozenset[str],
        graph: PartialOrderGraph,
    ) -> None:
        self._categories = categories
        self._leaves = leaves
        self._graph = graph

    @classmethod
    def load_from_yaml(cls, path: str | Path) -> ActionSemanticsRegistry:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("YAML root must be a mapping.")

        taxonomy = raw.get("taxonomy")
        if not isinstance(taxonomy, dict):
            raise ValueError("Missing or invalid `taxonomy` mapping.")

        categories: set[str] = set()
        leaves: set[str] = set()
        for cat_key, items in taxonomy.items():
            if not isinstance(cat_key, str) or not cat_key:
                raise ValueError(f"Invalid taxonomy category key: {cat_key!r}")
            categories.add(cat_key)
            if not isinstance(items, list):
                raise ValueError(f"taxonomy[{cat_key!r}] must be a list of leaf labels.")
            for leaf in items:
                if not isinstance(leaf, str) or not leaf:
                    raise ValueError(f"Invalid leaf under {cat_key!r}: {leaf!r}")
                if leaf in leaves:
                    raise ValueError(f"Duplicate leaf label: {leaf!r}")
                leaves.add(leaf)

        graph = PartialOrderGraph(leaves)
        for pair in raw.get("partial_order_edges") or []:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise ValueError(f"partial_order_edges entry must be [a, b], got {pair!r}")
            a, b = str(pair[0]), str(pair[1])
            graph.add_edge(a, b)

        for dep in raw.get("deployment_specific_edges") or []:
            if not isinstance(dep, dict):
                raise ValueError(f"deployment_specific_edges item must be a mapping, got {dep!r}")
            if dep.get("enabled") is True:
                fa = dep.get("from")
                ta = dep.get("to")
                if not isinstance(fa, str) or not isinstance(ta, str):
                    raise ValueError(f"deployment_specific_edges entry needs from/to strings: {dep!r}")
                graph.add_edge(fa, ta)

        return cls(categories=frozenset(categories), leaves=frozenset(leaves), graph=graph)

    @property
    def partial_order(self) -> PartialOrderGraph:
        return self._graph

    @property
    def leaf_labels(self) -> frozenset[str]:
        return self._leaves

    @property
    def category_labels(self) -> frozenset[str]:
        return self._categories

    def is_category(self, label: str) -> bool:
        return label in self._categories

    def is_leaf_action(self, label: str) -> bool:
        return label in self._leaves

    def validate_action_label(self, label: str) -> None:
        """Reject unknown labels. Category and leaf symbols from the config are accepted."""
        if label in self._leaves or label in self._categories:
            return
        raise ValueError(f"Unknown action label: {label!r}")

    def validate_required_actions(self, required_actions: list[str]) -> None:
        """``required_actions`` must be leaf-only, registered, and never category labels."""
        if not isinstance(required_actions, list):
            raise ValueError("required_actions must be a list of strings.")
        for item in required_actions:
            if not isinstance(item, str) or not item:
                raise ValueError(f"Invalid required_action entry: {item!r}")
            if self.is_category(item):
                raise ValueError(
                    f"Category label {item!r} cannot be used as a required_action; use leaf labels only."
                )
            if not self.is_leaf_action(item):
                raise ValueError(f"Unknown or non-leaf required_action: {item!r}")

    def is_no_more_permissive(self, a: str, b: str) -> bool:
        """``a <= b`` in the configured partial order (delegates to :class:`PartialOrderGraph`)."""
        return self._graph.is_no_more_permissive(a, b)

    def get_reachable_supersets(self, label: str) -> set[str]:
        """All ``x`` with ``label <= x`` (same as :meth:`PartialOrderGraph.reachable_supersets`)."""
        return self._graph.reachable_supersets(label)
