"""Runtime overhead microbenchmark for RAC-TraceBench (pre-commit path).

Run from repository root, for example:

  export RAC_TRACEBENCH_ROOT=/path/to/rac_tracebench_v1
  python scripts/run_rac_tracebench_overhead.py --suite core --iterations 100

Outputs (default paired/core suite; historical output filenames):
  artifacts/results/rac_tracebench_v06_overhead.csv
  artifacts/results/rac_tracebench_v06_overhead_summary.json
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
    p = argparse.ArgumentParser(description="RAC-TraceBench pre-commit overhead microbenchmark")
    p.add_argument(
        "--iterations",
        type=int,
        default=100,
        help="Number of full passes over all TraceBench traces (default: 100)",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "results",
        help="Directory for CSV and JSON (default: <repo>/artifacts/results)",
    )
    p.add_argument(
        "--root",
        type=Path,
        default=None,
        help="RAC-TraceBench root (overrides RAC_TRACEBENCH_ROOT)",
    )
    p.add_argument(
        "--suite",
        choices=("core", "expanded", "all"),
        default="core",
        help="TraceBench suite (default: core — 44-case RQ1 conformance traces)",
    )
    p.add_argument(
        "--include-mixed",
        choices=("true", "false"),
        default="true",
        help="Include mixed_drift cases when suite=expanded (default: true)",
    )
    p.add_argument(
        "--rq2-overlay",
        action="store_true",
        help="Include rac-core composite overlay cases (expanded runs only)",
    )
    p.add_argument(
        "--skip-oracle-verify",
        action="store_true",
        help="Do not require Full RAC to match oracle before timing",
    )
    p.add_argument("--csv-name", type=str, default="rac_tracebench_v06_overhead.csv")
    p.add_argument("--json-name", type=str, default="rac_tracebench_v06_overhead_summary.json")
    p.add_argument("--trace-csv-name", type=str, default=None)
    p.add_argument("--summary-csv-name", type=str, default=None)
    args = p.parse_args()
    if args.iterations < 1:
        print("ERROR: --iterations must be >= 1", file=sys.stderr)
        sys.exit(2)

    root = resolve_tracebench_root(args.root)
    if root is None:
        print(
            "ERROR: TraceBench bundle not found. Set RAC_TRACEBENCH_ROOT or install suites under\n"
            "  RAC_DATA_DIR (default ../rac-data-review). Use --root to pass a path.",
            file=sys.stderr,
        )
        sys.exit(1)

    include_mixed = args.include_mixed.lower() == "true"
    print(
        f"[overhead] starting suite={args.suite} iterations={args.iterations} "
        f"output_dir={args.output_dir.resolve()}",
        flush=True,
    )
    csv_p, json_p, summary = run_overhead_and_write(
        bench_root=root,
        output_dir=args.output_dir.resolve(),
        iterations=args.iterations,
        suite=args.suite,
        include_mixed=include_mixed,
        include_rq2_overlay=args.rq2_overlay,
        verify_oracle=not args.skip_oracle_verify,
        csv_name=args.csv_name,
        json_name=args.json_name,
        trace_csv_name=args.trace_csv_name,
        summary_csv_name=args.summary_csv_name,
    )
    print(f"Wrote {csv_p}", flush=True)
    print(f"Wrote {json_p}", flush=True)
    if args.trace_csv_name:
        print(f"Wrote {args.output_dir.resolve() / args.trace_csv_name}")
    if args.summary_csv_name:
        print(f"Wrote {args.output_dir.resolve() / args.summary_csv_name}")
    print(
        f"traces={summary['num_traces']} iterations={summary['iterations']} "
        f"step_records={summary['total_step_records']}"
    )


if __name__ == "__main__":
    main()
