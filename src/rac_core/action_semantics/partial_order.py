"""Explicit partial order for leaf action labels (v0.6).

An edge ``a -> b`` means ``a <= b`` (``a`` is no-more-permissive-than ``b``):
if a basis allows ``b``, a manifest ``required_action`` of ``a`` is covered when ``a <= b``.

Unlisted pairs are incomparable by default (no edge, no inference).
Reflexivity: ``a <= a`` for every known label in the graph universe.
"""

from __future__ import annotations

from collections import deque
from typing import Iterable


class PartialOrderGraph:
    """Directed graph encoding the ``<=`` relation on a fixed universe of labels."""

    __slots__ = ("_universe", "_succ")

    def __init__(self, universe: set[str]) -> None:
        self._universe = frozenset(universe)
        self._succ: dict[str, set[str]] = {u: set() for u in self._universe}

    def add_edge(self, a: str, b: str) -> None:
        """Add ``a <= b`` (``a`` no-more-permissive-than ``b``)."""
        if a not in self._universe or b not in self._universe:
            raise ValueError(
                f"add_edge({a!r}, {b!r}): both endpoints must belong to the graph universe."
            )
        self._succ[a].add(b)

    def validate_no_unknown_labels(self, labels: Iterable[str]) -> None:
        unknown = sorted(set(labels) - set(self._universe))
        if unknown:
            raise ValueError(f"Unknown labels for this partial order: {unknown}")

    def is_no_more_permissive(self, a: str, b: str) -> bool:
        """Return True iff ``a <= b`` (reflexive, transitive closure of declared edges)."""
        self.validate_no_unknown_labels((a, b))
        if a == b:
            return True
        return b in self.reachable_supersets(a)

    def reachable_supersets(self, a: str) -> set[str]:
        """All ``x`` such that ``a <= x`` (including ``a``)."""
        self.validate_no_unknown_labels((a,))
        seen: set[str] = set()
        q: deque[str] = deque()
        seen.add(a)
        q.append(a)
        while q:
            u = q.popleft()
            for v in self._succ.get(u, ()):
                if v not in seen:
                    seen.add(v)
                    q.append(v)
        return seen
