"""Generate benign false-positive suite validation tables.

Run from repository root:
  python scripts/generate_benign_fp_tables.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from pydantic import BaseModel

from rac_core.models import DecisionType
from rac_core.validation import TraceRunner, format_decision, to_csv, to_latex_tabular, to_markdown_table
from rac_core.validation.benign_fp_traces import build_benign_fp_checker, build_benign_fp_traces


class BenignFpValidationRow(BaseModel):
    case_id: str
    case_name: str
    num_steps: int
    observed_decision: str
    match: str


class BenignFpSummaryRow(BaseModel):
    suite: str
    total: int
    allowed: int
    blocked: int


def _last_decision(result) -> DecisionType:
    if not result.step_results:
        return DecisionType.BLOCK
    return result.step_results[-1].decision.decision


def main() -> None:
    out_dir = ROOT / "artifacts" / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)

    traces = build_benign_fp_traces()
    val_rows: list[BenignFpValidationRow] = []
    blocked = 0

    for i, trace in enumerate(traces):
        checker = build_benign_fp_checker()
        runner = TraceRunner(checker)
        result = runner.run(trace)
        obs = _last_decision(result)
        if obs != DecisionType.ALLOW:
            blocked += 1
        val_rows.append(
            BenignFpValidationRow(
                case_id=f"FP{i + 1:02d}",
                case_name=trace.name,
                num_steps=len(trace.steps),
                observed_decision=format_decision(obs),
                match="✓" if obs == DecisionType.ALLOW else "✗",
            )
        )

    summary_rows = [
        BenignFpSummaryRow(
            suite="benign_fp",
            total=len(traces),
            allowed=len(traces) - blocked,
            blocked=blocked,
        )
    ]

    def write_triplet(base: str, rows: list) -> None:
        for ext, fn_write in (
            ("md", to_markdown_table),
            ("csv", to_csv),
            ("tex", lambda r: to_latex_tabular(r)),
        ):
            p = out_dir / f"{base}.{ext}"
            p.write_text(fn_write(rows), encoding="utf-8")
            print(p)

    write_triplet("benign_fp_validation", val_rows)
    write_triplet("benign_fp_summary", summary_rows)
    json_path = out_dir / "benign_fp_summary.json"
    json_path.write_text(
        json.dumps(
            {
                "summary_rows": [r.model_dump() for r in summary_rows],
                "validation_rows": [r.model_dump() for r in val_rows],
                "blocked_count": blocked,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json_path)

    if blocked:
        print(f"ERROR: {blocked} benign trace(s) observed BLOCK (expected all ALLOW).", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
