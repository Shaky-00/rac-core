#!/usr/bin/env python3
"""Stage 9B: build paper-style latency summaries and figures from raw CSV artifacts."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from rac_core.evaluation.reporting import generate_all_latency_reports


def main() -> None:
    perf_dir = REPO_ROOT / "artifacts" / "performance"
    required = [
        perf_dir / "latency_workflow_scaling.csv",
        perf_dir / "latency_decision_paths.csv",
        perf_dir / "latency_predecessor_resolution.csv",
        perf_dir / "latency_breakdown.csv",
    ]
    missing = [p for p in required if not p.is_file()]
    if missing:
        print("Missing input CSV(s); run latency evaluation first:", file=sys.stderr)
        for p in missing:
            print(f"  {p}", file=sys.stderr)
        raise SystemExit(1)

    paths = generate_all_latency_reports(perf_dir, log=print)
    print("Generated:")
    for p in paths:
        print(f"  {p}")


if __name__ == "__main__":
    main()
