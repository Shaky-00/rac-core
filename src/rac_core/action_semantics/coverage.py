"""Action coverage (v0.6): required leaf actions vs allowed basis labels."""

from __future__ import annotations

from typing import Iterable

from rac_core.action_semantics.registry import ActionSemanticsRegistry


def action_covered(
    required_action: str,
    allowed_action_labels: set[str],
    registry: ActionSemanticsRegistry,
) -> bool:
    """True iff some allowed label ``u`` satisfies ``required_action == u`` or ``required_action <= u``."""
    registry.validate_required_actions([required_action])
    for allowed in allowed_action_labels:
        if not registry.is_leaf_action(allowed):
            raise ValueError(
                f"allowed_action_labels must contain only leaf action labels; got {allowed!r}"
            )
        if required_action == allowed:
            return True
        if registry.is_no_more_permissive(required_action, allowed):
            return True
    return False


def all_actions_covered(
    required_actions: Iterable[str],
    allowed_action_labels: set[str],
    registry: ActionSemanticsRegistry,
) -> bool:
    """True iff every required action is covered (see :func:`action_covered`)."""
    req_list = list(required_actions)
    registry.validate_required_actions(req_list)
    return all(action_covered(r, allowed_action_labels, registry) for r in req_list)
