"""Static Full RAC vs ablation replay for RAC-TraceBench v0.6.

Run from repository root, for example:

  RAC_TRACEBENCH_ROOT=/root/projects/mcp_data/rac_tracebench_v06 \\
    python scripts/run_rac_tracebench_v06.py

Outputs:
  results/rac_tracebench_v06_results.csv
  results/rac_tracebench_v06_summary.json
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from rac_core.validation.rac_tracebench_experiment import (  # noqa: E402
    resolve_tracebench_root,
    run_and_write,
)


def main() -> None:
    root = resolve_tracebench_root()
    if root is None:
        print(
            "ERROR: RAC-TraceBench root not found. Set RAC_TRACEBENCH_ROOT or place "
            "mcp_data/rac_tracebench_v06 next to the repo.",
            file=sys.stderr,
        )
        sys.exit(1)
    out_dir = ROOT / "results"
    csv_p, json_p = run_and_write(root=root, output_dir=out_dir)
    print(f"Wrote {csv_p}")
    print(f"Wrote {json_p}")


if __name__ == "__main__":
    main()
