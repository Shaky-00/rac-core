"""Write Stage 8A replayed LLM plan report tables (Markdown, CSV, LaTeX).

Run from repository root:
  python scripts/generate_llm_plan_report.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from rac_core.demo.llm_reporting import generate_llm_plan_report_results


def main() -> None:
    out_dir = ROOT / "artifacts" / "tables"
    paths = generate_llm_plan_report_results(out_dir)
    for p in paths:
        print(p)


if __name__ == "__main__":
    main()
