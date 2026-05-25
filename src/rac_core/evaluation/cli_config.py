"""CLI configuration for Stage 9A latency evaluation (no benchmark execution)."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

DEFAULT_WORKFLOW_LENGTHS: tuple[int, ...] = (1, 5, 10, 20, 50, 100, 200)
QUICK_WORKFLOW_LENGTHS: tuple[int, ...] = (1, 5, 10)

DEFAULT_PREDECESSOR_COUNTS: tuple[int, ...] = (1, 2, 4, 8, 16, 32)
QUICK_PREDECESSOR_COUNTS: tuple[int, ...] = (1, 2)

DEFAULT_REPEATS = 100
DEFAULT_WARMUP = 10
QUICK_REPEATS = 5
QUICK_WARMUP = 1


@dataclass(frozen=True)
class LatencyEvalConfig:
    quick: bool
    workflow_lengths: tuple[int, ...]
    predecessor_counts: tuple[int, ...]
    repeats: int
    warmup: int
    output_dir: Path | None


def _parse_csv_ints(value: str, *, flag: str) -> tuple[int, ...]:
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if not parts:
        raise argparse.ArgumentTypeError(f"{flag} must list at least one integer")
    out: list[int] = []
    for p in parts:
        try:
            out.append(int(p, 10))
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"{flag} must be comma-separated integers; invalid entry {p!r}"
            ) from exc
    return tuple(out)


def build_latency_eval_config(argv: list[str] | None = None) -> LatencyEvalConfig:
    """Parse CLI argv into a frozen config (same rules as ``run_latency_evaluation.py``).

    Pass an explicit list (e.g. ``[]``) from tests; if ``argv`` is ``None``, uses
    ``sys.argv[1:]`` like argparse.
    """
    import sys

    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser(description="RAC latency evaluation (Stage 9A).")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Use small workflow/predecessor grids and fewer repeats.",
    )
    parser.add_argument("--repeats", type=int, default=None)
    parser.add_argument("--warmup", type=int, default=None)
    parser.add_argument(
        "--lengths",
        type=str,
        default=None,
        metavar="N,N,...",
        help="Override workflow lengths (comma-separated integers).",
    )
    parser.add_argument(
        "--predecessor-counts",
        type=str,
        default=None,
        dest="predecessor_counts",
        metavar="N,N,...",
        help="Override predecessor fan-in counts (comma-separated integers).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for latency JSON/CSV (default: <repo>/artifacts/results/performance).",
    )
    ns = parser.parse_args(argv)

    if ns.quick:
        workflow_lengths = QUICK_WORKFLOW_LENGTHS
        predecessor_counts = QUICK_PREDECESSOR_COUNTS
        repeats = QUICK_REPEATS
        warmup = QUICK_WARMUP
    else:
        workflow_lengths = DEFAULT_WORKFLOW_LENGTHS
        predecessor_counts = DEFAULT_PREDECESSOR_COUNTS
        repeats = DEFAULT_REPEATS
        warmup = DEFAULT_WARMUP

    if ns.repeats is not None:
        repeats = ns.repeats
    if ns.warmup is not None:
        warmup = ns.warmup
    if ns.lengths is not None:
        workflow_lengths = _parse_csv_ints(ns.lengths, flag="--lengths")
    if ns.predecessor_counts is not None:
        predecessor_counts = _parse_csv_ints(
            ns.predecessor_counts, flag="--predecessor-counts"
        )

    if repeats < 0 or warmup < 0:
        raise SystemExit("repeats and warmup must be non-negative")

    return LatencyEvalConfig(
        quick=ns.quick,
        workflow_lengths=workflow_lengths,
        predecessor_counts=predecessor_counts,
        repeats=repeats,
        warmup=warmup,
        output_dir=ns.output_dir,
    )


def format_latency_eval_config(cfg: LatencyEvalConfig) -> str:
    lines = [
        "Latency evaluation configuration:",
        f"  quick: {cfg.quick}",
        f"  workflow_lengths: {list(cfg.workflow_lengths)}",
        f"  predecessor_counts: {list(cfg.predecessor_counts)}",
        f"  repeats: {cfg.repeats}",
        f"  warmup: {cfg.warmup}",
        f"  output_dir: {cfg.output_dir}",
    ]
    return "\n".join(lines) + "\n"
