"""Write Stage 7A demo controller report tables (Markdown, CSV, LaTeX).

Run from repository root:
  python scripts/generate_demo_report.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from rac_core.demo.reporting import generate_demo_controller_results


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    out_dir = repo_root / "artifacts" / "tables"
    paths = generate_demo_controller_results(out_dir)
    for p in paths:
        print(p)


if __name__ == "__main__":
    main()
