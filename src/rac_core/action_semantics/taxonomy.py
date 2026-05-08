"""v0.6 action taxonomy helpers (categories vs leaf labels)."""

from __future__ import annotations

from pathlib import Path

# Category keys match YAML `taxonomy` top-level keys (lowercase).
CANONICAL_CATEGORY_PREFIXES: tuple[str, ...] = (
    "meta",
    "acquire",
    "transform",
    "mutate",
    "disclose",
    "authority",
    "execute",
    "transaction",
)


def default_semantics_yaml_path() -> Path:
    """Path to bundled default semantics config (repo-root ``configs/``)."""
    # .../src/rac_core/action_semantics/taxonomy.py -> repo root
    return Path(__file__).resolve().parents[3] / "configs" / "default_action_semantics.yaml"
