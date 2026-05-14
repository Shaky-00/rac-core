#!/usr/bin/env python3
"""Stage 9A: run latency / overhead benchmarks and write JSON + CSV under artifacts/performance/."""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path
from typing import TextIO

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from rac_core.evaluation.cli_config import (
    LatencyEvalConfig,
    build_latency_eval_config,
    format_latency_eval_config,
)
from rac_core.evaluation.latency import (
    LatencySample,
    LatencySummary,
    run_component_breakdown_benchmark,
    run_decision_path_benchmark,
    run_predecessor_resolution_benchmark,
    run_workflow_length_benchmark,
    samples_to_csv,
    write_json,
    write_text,
)


def _payload(
    samples: list[LatencySample], summaries: list[LatencySummary]
) -> dict:
    return {
        "samples": [asdict(s) for s in samples],
        "summaries": [asdict(s) for s in summaries],
    }


def run_latency_evaluation(
    cfg: LatencyEvalConfig,
    *,
    out_dir: Path,
    log: TextIO,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    log.write(format_latency_eval_config(cfg))
    log.flush()

    def _phase(i: int, total: int, title: str) -> None:
        log.write(f"[{i}/{total}] {title}\n")
        log.flush()

    def _done(i: int, total: int, csv_name: str) -> None:
        log.write(f"[{i}/{total}] Done: {csv_name}\n\n")
        log.flush()

    total_phases = 4

    # [1/4] Workflow length scaling
    _phase(1, total_phases, "Running workflow length benchmark...")
    wf_samples: list[LatencySample] = []
    wf_summaries: list[LatencySummary] = []
    for L in cfg.workflow_lengths:
        log.write(
            f"  - length={L} repeats={cfg.repeats} warmup={cfg.warmup}\n"
        )
        log.flush()
        s, summ = run_workflow_length_benchmark(
            lengths=[L], repeats=cfg.repeats, warmup=cfg.warmup
        )
        wf_samples.extend(s)
        wf_summaries.extend(summ)
    write_json(out_dir / "latency_workflow_scaling.json", _payload(wf_samples, wf_summaries))
    write_text(out_dir / "latency_workflow_scaling.csv", samples_to_csv(wf_samples))
    _done(1, total_phases, "latency_workflow_scaling.csv")

    # [2/4] Decision paths
    _phase(2, total_phases, "Running decision path benchmark...")
    log.write(f"  - repeats={cfg.repeats} warmup={cfg.warmup}\n")
    log.flush()
    dp_s, dp_sum = run_decision_path_benchmark(repeats=cfg.repeats, warmup=cfg.warmup)
    write_json(out_dir / "latency_decision_paths.json", _payload(dp_s, dp_sum))
    write_text(out_dir / "latency_decision_paths.csv", samples_to_csv(dp_s))
    _done(2, total_phases, "latency_decision_paths.csv")

    # [3/4] Predecessor resolution
    _phase(3, total_phases, "Running predecessor resolution benchmark...")
    pr_samples: list[LatencySample] = []
    pr_summaries: list[LatencySummary] = []
    for n in cfg.predecessor_counts:
        log.write(
            f"  - predecessor_count={n} repeats={cfg.repeats} warmup={cfg.warmup}\n"
        )
        log.flush()
        s, summ = run_predecessor_resolution_benchmark(
            predecessor_counts=[n], repeats=cfg.repeats, warmup=cfg.warmup
        )
        pr_samples.extend(s)
        pr_summaries.extend(summ)
    write_json(out_dir / "latency_predecessor_resolution.json", _payload(pr_samples, pr_summaries))
    write_text(out_dir / "latency_predecessor_resolution.csv", samples_to_csv(pr_samples))
    _done(3, total_phases, "latency_predecessor_resolution.csv")

    # [4/4] Component breakdown
    _phase(4, total_phases, "Running component breakdown benchmark...")
    log.write(f"  - repeats={cfg.repeats} warmup={cfg.warmup}\n")
    log.flush()
    bd_s, bd_sum = run_component_breakdown_benchmark(
        repeats=cfg.repeats, warmup=cfg.warmup
    )
    write_json(out_dir / "latency_breakdown.json", _payload(bd_s, bd_sum))
    write_text(out_dir / "latency_breakdown.csv", samples_to_csv(bd_s))
    _done(4, total_phases, "latency_breakdown.csv")

    written = [
        out_dir / "latency_workflow_scaling.json",
        out_dir / "latency_workflow_scaling.csv",
        out_dir / "latency_decision_paths.json",
        out_dir / "latency_decision_paths.csv",
        out_dir / "latency_predecessor_resolution.json",
        out_dir / "latency_predecessor_resolution.csv",
        out_dir / "latency_breakdown.json",
        out_dir / "latency_breakdown.csv",
    ]
    log.write("Wrote:\n")
    for p in written:
        log.write(f"  {p}\n")
    log.flush()


def main(argv: list[str] | None = None) -> None:
    """Entry point. ``argv`` defaults to ``sys.argv[1:]`` via :func:`build_latency_eval_config`."""
    cfg = build_latency_eval_config(argv)
    out_dir = cfg.output_dir
    if out_dir is None:
        out_dir = REPO_ROOT / "artifacts" / "performance"
    else:
        out_dir = out_dir.expanduser().resolve()
    run_latency_evaluation(cfg, out_dir=out_dir, log=sys.stdout)


if __name__ == "__main__":
    main()
