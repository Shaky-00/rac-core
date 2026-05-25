#!/usr/bin/env python3
"""Reviewer-facing entry point for TraceBench paired-suite static replay."""

from __future__ import annotations

import argparse
import runpy
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_TARGET = Path(__file__).resolve().parent / "run_rac_tracebench_v06.py"

# Legacy filenames from run_rac_tracebench_v06.py → neutral reviewer-facing names.
_NEUTRAL_NAMES: dict[str, str] = {
    "rac_tracebench_v06_results.csv": "tracebench_paired_results.csv",
    "rac_tracebench_v06_summary.json": "tracebench_paired_summary.json",
    "rac_tracebench_v06_baselines_results.csv": "tracebench_paired_baselines_results.csv",
    "rac_tracebench_v06_baselines_summary.json": "tracebench_paired_baselines_summary.json",
    "rac_tracebench_v06_ablations_results.csv": "tracebench_paired_ablations_results.csv",
    "rac_tracebench_v06_ablations_summary.json": "tracebench_paired_ablations_summary.json",
    "rac_tracebench_v06_benign_summary.csv": "tracebench_paired_benign_summary.csv",
    "rac_tracebench_v06_benign_summary.json": "tracebench_paired_benign_summary.json",
}


def _parse_output_dir(argv: list[str]) -> Path:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--output-dir", type=Path, default=_ROOT / "artifacts" / "results")
    args, _ = p.parse_known_args(argv[1:])
    return args.output_dir.expanduser().resolve()


def _publish_neutral_outputs(out_dir: Path) -> list[Path]:
    published: list[Path] = []
    for legacy, neutral in _NEUTRAL_NAMES.items():
        src = out_dir / legacy
        if not src.is_file():
            continue
        dst = out_dir / neutral
        shutil.copy2(src, dst)
        published.append(dst)
    return published


def main() -> None:
    argv = sys.argv[:]
    out_dir = _parse_output_dir(argv)
    argv[0] = str(_TARGET)
    runpy.run_path(str(_TARGET), run_name="__main__", init_globals={"__name__": "__main__"})
    published = _publish_neutral_outputs(out_dir)
    for p in published:
        print(f"Wrote {p}")


if __name__ == "__main__":
    main()
