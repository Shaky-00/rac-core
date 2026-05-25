"""Static Full RAC vs ablation replay for TraceBench paired suite.

Run from repository root, for example:

  export RAC_DATA_DIR=../rac-data
  export RAC_TRACEBENCH_ROOT=../rac-data/tracebench/paired   # optional
  python scripts/run_rac_tracebench_v06.py --output-dir artifacts/results

Outputs (default names when --variant-group full):
  rac_tracebench_v06_results.csv
  rac_tracebench_v06_summary.json
"""

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
    p = argparse.ArgumentParser(description="TraceBench paired-suite static replay (FULL_RAC, baselines, ablations)")
    p.add_argument(
        "--root",
        type=Path,
        default=None,
        help="RAC-TraceBench bundle root (overrides RAC_TRACEBENCH_ROOT)",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "results",
        help="Directory for CSV and JSON summaries (default: <repo>/artifacts/results)",
    )
    p.add_argument(
        "--variant-group",
        choices=("full", "baselines", "ablations"),
        default="full",
        help="full: all variants; baselines: FULL_RAC / NO_RAC / ENTRY_ONLY / static / history; "
        "ablations: RAC_WITHOUT_* only",
    )
    args = p.parse_args()

    root = resolve_tracebench_root(args.root)
    if root is None:
        print(
            "ERROR: TraceBench paired suite not found. Set RAC_TRACEBENCH_ROOT or install under\n"
            "  RAC_DATA_DIR/tracebench/paired (default ../rac-data/tracebench/paired).\n"
            "Use --root to pass an explicit path.",
            file=sys.stderr,
        )
        sys.exit(1)

    out_dir = args.output_dir.expanduser().resolve()
    plan = tracebench_variant_plan(args.variant_group)
    if args.variant_group == "full":
        csv_name, json_name = "rac_tracebench_v06_results.csv", "rac_tracebench_v06_summary.json"
    elif args.variant_group == "baselines":
        csv_name, json_name = "rac_tracebench_v06_baselines_results.csv", "rac_tracebench_v06_baselines_summary.json"
    else:
        csv_name, json_name = "rac_tracebench_v06_ablations_results.csv", "rac_tracebench_v06_ablations_summary.json"

    csv_p, json_p = run_and_write(
        root=root,
        output_dir=out_dir,
        variant_plan=plan,
        csv_name=csv_name,
        json_name=json_name,
    )
    print(f"Wrote {csv_p}")
    print(f"Wrote {json_p}")


if __name__ == "__main__":
    main()
