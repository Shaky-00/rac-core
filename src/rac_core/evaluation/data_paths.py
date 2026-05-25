"""Resolve external dataset locations for artifact evaluation (rac-data layout)."""

from __future__ import annotations

import os
from pathlib import Path

TRACEBENCH_SUITES: tuple[str, ...] = ("paired", "core", "expanded", "composite-overlay")


def repo_root() -> Path:
    """rac-core repository root (parent of ``src/``)."""
    return Path(__file__).resolve().parents[3]


def rac_data_dir() -> Path:
    """Dataset repository root (default: sibling ``../rac-data``)."""
    raw = os.environ.get("RAC_DATA_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return (repo_root().parent / "rac-data").resolve()


def _suite_layout_ok(root: Path, suite: str) -> bool:
    suite = suite.strip().lower()
    if suite == "paired":
        return (root / "controlled_traces" / "paired").is_dir()
    if suite == "core":
        return (root / "controlled_traces" / "core").is_dir()
    if suite == "expanded":
        return (root / "controlled_traces" / "expanded").is_dir()
    if suite == "composite-overlay":
        return (root / "controlled_traces").is_dir() and any(root.glob("controlled_traces/*.json"))
    return False


def _resolve_env_tracebench_root(suite: str) -> Path | None:
    raw = os.environ.get("RAC_TRACEBENCH_ROOT")
    if not raw:
        return None
    root = Path(raw).expanduser().resolve()
    if _suite_layout_ok(root, suite):
        return root
    # Unified bundle root: RAC_TRACEBENCH_ROOT points at parent of controlled_traces/{suite}.
    if _suite_layout_ok(root, "core") or _suite_layout_ok(root, "paired"):
        return root
    return root if root.is_dir() else None


def tracebench_root(suite: str = "paired") -> Path:
    """
    Return the TraceBench bundle root for ``suite``.

    Suites: ``paired``, ``core``, ``expanded``, ``composite-overlay``.

    Resolution order:
    1. ``RAC_TRACEBENCH_ROOT`` when it contains the requested layout.
    2. ``RAC_DATA_DIR/tracebench/<suite>`` (paired / composite-overlay bundles).
    3. ``RAC_DATA_DIR/tracebench`` when it is a unified bundle (``controlled_traces/core``).
    4. Legacy ``rac-core/data/tracebench/<suite>`` install paths.
    """
    suite = (suite or "paired").strip().lower()
    if suite not in TRACEBENCH_SUITES:
        raise ValueError(
            f"Unknown TraceBench suite {suite!r}. Expected one of: {', '.join(TRACEBENCH_SUITES)}."
        )

    env_root = _resolve_env_tracebench_root(suite)
    if env_root is not None and _suite_layout_ok(env_root, suite):
        return env_root
    if env_root is not None and suite in ("core", "expanded") and _suite_layout_ok(env_root, "core"):
        return env_root

    data = rac_data_dir()
    per_suite = data / "tracebench" / suite
    if _suite_layout_ok(per_suite, suite):
        return per_suite

    unified = data / "tracebench"
    if _suite_layout_ok(unified, suite):
        return unified
    if suite in ("core", "expanded") and _suite_layout_ok(unified, "core"):
        return unified

    legacy = repo_root() / "data" / "tracebench" / suite
    if _suite_layout_ok(legacy, suite):
        return legacy
    legacy_unified = repo_root() / "data" / "tracebench"
    if _suite_layout_ok(legacy_unified, suite):
        return legacy_unified
    if suite in ("core", "expanded") and _suite_layout_ok(legacy_unified, "core"):
        return legacy_unified

    raise FileNotFoundError(
        f"TraceBench suite {suite!r} not found. Set RAC_TRACEBENCH_ROOT to a bundle root, "
        f"or install data under RAC_DATA_DIR (default {data}). "
        f"Expected layout: tracebench/paired or tracebench/controlled_traces/{{core,expanded}}."
    )


def tracebench_v1_bundle_root() -> Path | None:
    """Bundle root with ``controlled_traces/core`` (expanded replay scripts)."""
    env = _resolve_env_tracebench_root("core")
    if env is not None and _suite_layout_ok(env, "core"):
        return env
    data = rac_data_dir()
    unified = data / "tracebench"
    if _suite_layout_ok(unified, "core"):
        return unified
    legacy = repo_root() / "data" / "tracebench"
    if _suite_layout_ok(legacy, "core"):
        return legacy
    return None


def composite_overlay_traces_dir() -> Path:
    """Directory of composite-overlay trace JSON files."""
    try:
        root = tracebench_root("composite-overlay")
        traces = root / "controlled_traces"
        if traces.is_dir():
            return traces
    except FileNotFoundError:
        pass
    legacy = repo_root() / "data" / "tracebench_rq2_composite_overlay" / "controlled_traces"
    return legacy


def tracebench_root_candidates() -> list[Path]:
    """Ordered search paths for ``resolve_rac_tracebench_root`` (paired-first)."""
    seen: list[Path] = []
    env = os.environ.get("RAC_TRACEBENCH_ROOT")
    if env:
        seen.append(Path(env).expanduser().resolve())
    data = rac_data_dir()
    for rel in (
        data / "tracebench" / "paired",
        data / "tracebench",
        repo_root() / "data" / "tracebench" / "paired",
        repo_root() / "data" / "tracebench",
    ):
        p = rel.resolve()
        if p not in seen:
            seen.append(p)
    return seen
