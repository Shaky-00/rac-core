"""Optional helper for regenerating derived tables from replayed planner-style plan summaries.

Run from repository root:
  python3 scripts/paper_optional/generate_llm_plan_report.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from rac_core.demo.llm_reporting import generate_llm_plan_report_results


def main() -> None:
    out_dir = ROOT / "artifacts" / "generated" / "tables"
    paths = generate_llm_plan_report_results(out_dir)
    for p in paths:
        print(p)


if __name__ == "__main__":
    main()
