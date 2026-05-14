"""Resolve experiment inputs for optional helper scripts (outputs live under ``artifacts/``)."""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def pick_input(filename: str) -> Path:
    """Prefer fresh ``artifacts/results/``, then ``artifacts/expected/summaries|data``."""
    root = repo_root()
    for sub in (
        ("artifacts", "results"),
        ("artifacts", "expected", "summaries"),
        ("artifacts", "expected", "data"),
    ):
        p = root.joinpath(*sub, filename)
        if p.is_file():
            return p
    raise FileNotFoundError(
        f"Missing {filename!r}. Run core TraceBench/overhead scripts to populate "
        f"artifacts/results/, or add the file under artifacts/expected/summaries/ or "
        f"artifacts/expected/data/."
    )


def try_pick_input(filename: str) -> Path | None:
    try:
        return pick_input(filename)
    except FileNotFoundError:
        return None


class MergedResultPath:
    """Emulates ``results / \"name\"`` but resolves via :func:`pick_input`."""

    def __truediv__(self, name: str) -> Path:
        return pick_input(name)


class OptionalMergedResultPath:
    """Returns a non-resolving path under ``.missing_inputs/`` when absent."""

    def __truediv__(self, name: str) -> Path:
        p = try_pick_input(name)
        if p is not None:
            return p
        return repo_root() / ".missing_inputs" / name
