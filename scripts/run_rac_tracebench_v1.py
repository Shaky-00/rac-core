"""Static replay for RAC-TraceBench v1 (core / expanded suites)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from rac_core.validation.rac_tracebench_experiment import (  # noqa: E402
    resolve_tracebench_root,
    run_and_write,
    tracebench_variant_plan,
)


def main() -> None:
    p = argparse.ArgumentParser(description="RAC-TraceBench v1 static replay")
    p.add_argument("--root", type=Path, default=None, help="Bundle root (RAC_TRACEBENCH_ROOT)")
    p.add_argument("--output-dir", type=Path, default=ROOT / "artifacts" / "results")
    p.add_argument(
        "--suite",
        choices=("core", "expanded", "all"),
        default="core",
        help="Which v1 suite to run (default: core)",
    )
    p.add_argument(
        "--include-mixed",
        choices=("true", "false"),
        default="false",
        help="Include family=mixed_drift cases (RQ2 default: true via run_rq2_tracebench.sh)",
    )
    p.add_argument(
        "--variant-group",
        choices=("full", "baselines", "ablations", "rq2_full", "rq2_main", "rq2_diagnostic"),
        default="full",
    )
    p.add_argument(
        "--rq2-overlay",
        action="store_true",
        help="Merge rac-core composite-drift overlay cases (RQ2 expanded runs)",
    )
    p.add_argument(
        "--write-rq2-aux",
        action="store_true",
        help="Write rq2_summary.json and rq2_component_diagnostic.csv",
    )
    args = p.parse_args()

    root = resolve_tracebench_root(args.root)
    if root is None:
        print("ERROR: RAC-TraceBench v1 root not found.", file=sys.stderr)
        sys.exit(1)

    include_mixed = args.include_mixed.lower() == "true"
    plan = tracebench_variant_plan(args.variant_group)
    suffix = args.suite
    if args.suite == "expanded":
        if args.rq2_overlay:
            suffix = "expanded_rq2"
        elif not include_mixed:
            suffix = "expanded_no_mixed"
        else:
            suffix = "expanded"
    csv_name = f"rac_tracebench_v1_{suffix}_results.csv"
    json_name = f"rac_tracebench_v1_{suffix}_summary.json"

    out_dir = args.output_dir.expanduser().resolve()
    csv_p, json_p = run_and_write(
        root=root,
        output_dir=out_dir,
        variant_plan=plan,
        csv_name=csv_name,
        json_name=json_name,
        suite=args.suite,
        include_mixed=include_mixed,
        include_rq2_overlay=args.rq2_overlay,
        write_rq2_aux=args.write_rq2_aux,
    )
    print(f"Wrote {csv_p}")
    print(f"Wrote {json_p}")


if __name__ == "__main__":
    main()
