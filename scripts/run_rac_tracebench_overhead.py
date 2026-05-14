"""Runtime overhead microbenchmark for RAC-TraceBench v0.6 (pre-commit path).

Run from repository root, for example:

  RAC_TRACEBENCH_ROOT=/root/projects/mcp_data/rac_tracebench_v06 \\
    python scripts/run_rac_tracebench_overhead.py --iterations 100

Outputs:
  results/rac_tracebench_v06_overhead.csv
  results/rac_tracebench_v06_overhead_summary.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from rac_core.validation.rac_tracebench_overhead import (  # noqa: E402
    resolve_tracebench_root,
    run_overhead_and_write,
)


def main() -> None:
    p = argparse.ArgumentParser(description="RAC-TraceBench v0.6 pre-commit overhead microbenchmark")
    p.add_argument(
        "--iterations",
        type=int,
        default=100,
        help="Number of full passes over all TraceBench traces (default: 100)",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "results",
        help="Directory for CSV and JSON (default: <repo>/results)",
    )
    p.add_argument(
        "--root",
        type=Path,
        default=None,
        help="RAC-TraceBench root (overrides RAC_TRACEBENCH_ROOT)",
    )
    args = p.parse_args()
    if args.iterations < 1:
        print("ERROR: --iterations must be >= 1", file=sys.stderr)
        sys.exit(2)

    root = resolve_tracebench_root(args.root)
    if root is None:
        print(
            "ERROR: RAC-TraceBench root not found. Set RAC_TRACEBENCH_ROOT or place "
            "mcp_data/rac_tracebench_v06 next to the repo. Use --root to pass a path.",
            file=sys.stderr,
        )
        sys.exit(1)

    csv_p, json_p, _summary = run_overhead_and_write(
        bench_root=root,
        output_dir=args.output_dir.resolve(),
        iterations=args.iterations,
    )
    print(f"Wrote {csv_p}")
    print(f"Wrote {json_p}")


if __name__ == "__main__":
    main()
