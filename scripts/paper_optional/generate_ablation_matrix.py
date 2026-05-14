"""Generate component-specific ablation matrix (B / M / A cells).

Run from repository root:
  python scripts/generate_ablation_matrix.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from rac_core.validation import to_csv, to_latex_tabular, to_markdown_table
from rac_core.validation.ablation import AblationRunner, COMPONENT_ABLATION_MODES
from rac_core.validation.component_ablation_cases import (
    build_component_ablation_cases,
    component_attack_checker_factory,
)
from rac_core.validation.reporting import build_component_ablation_matrix_rows


class FinalAblationMatrixRow(BaseModel):
    case: str
    FULL: str
    m_origin: str
    m_lineage: str
    m_purpose: str
    m_action: str
    m_cond: str
    m_deleg: str
    m_anchor: str


class FinalAblationSummaryRow(BaseModel):
    mode: str
    blocked: int
    missed: int
    allowed: int


CASE_LABELS: dict[str, str] = {
    "o1_origin_only_unverifiable_text": "O1",
    "l1_lineage_only_forged_hash": "L1",
    "p1_purpose_only_external": "P1",
    "a1_action_only_external_email": "A1",
    "c1_condition_only_tenant_change": "C1",
    "d1_delegation_only_introduced": "D1",
    "an1_anchor_only_unverified_output": "AN1",
    "benign_control_single_read": "Benign",
}

MODE_COLUMN_MAP: tuple[tuple[str, str], ...] = (
    ("full", "FULL"),
    ("wo_origin", "m_origin"),
    ("wo_lineage", "m_lineage"),
    ("wo_purpose", "m_purpose"),
    ("wo_action", "m_action"),
    ("wo_conditions", "m_cond"),
    ("wo_delegation", "m_deleg"),
    ("wo_anchor", "m_anchor"),
)


def main() -> None:
    out_dir = ROOT / "artifacts" / "generated" / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)

    traces = build_component_ablation_cases()
    order = [t.name for t in traces]
    miss_map: dict[str, str | None] = {}
    benign_names: set[str] = set()
    for t in traces:
        mm = t.metadata.get("miss_mode")
        miss_map[t.name] = str(mm) if mm is not None else None
        if str(t.metadata.get("component", "")) == "control":
            benign_names.add(t.name)

    runner = AblationRunner(checker_factory=component_attack_checker_factory)
    results = runner.run_suite(traces, list(COMPONENT_ABLATION_MODES))

    matrix_rows_raw = build_component_ablation_matrix_rows(
        results,
        trace_order=order,
        trace_labels=CASE_LABELS,
        miss_mode_by_trace=miss_map,
        benign_trace_names=benign_names,
    )
    matrix_rows: list[FinalAblationMatrixRow] = []
    for row in matrix_rows_raw:
        dumped = row.model_dump()
        matrix_rows.append(
            FinalAblationMatrixRow(
                case=row.case,
                **{label: dumped[field] for field, label in MODE_COLUMN_MAP},
            )
        )

    summary_rows: list[FinalAblationSummaryRow] = []
    for field, label in MODE_COLUMN_MAP:
        blocked = sum(1 for row in matrix_rows_raw if row.model_dump()[field] == "B")
        missed = sum(1 for row in matrix_rows_raw if row.model_dump()[field] == "M")
        allowed = sum(1 for row in matrix_rows_raw if row.model_dump()[field] == "A")
        mode_label = "FULL" if field == "full" else f"-{field.split('_', 1)[1].title()}"
        summary_rows.append(
            FinalAblationSummaryRow(
                mode=mode_label, blocked=blocked, missed=missed, allowed=allowed
            )
        )

    def write_triplet(base: str, rows: list) -> None:
        for ext, fn_write in (
            ("md", to_markdown_table),
            ("csv", to_csv),
            ("tex", lambda r: to_latex_tabular(r)),
        ):
            p = out_dir / f"{base}.{ext}"
            p.write_text(fn_write(rows), encoding="utf-8")
            print(p)

    write_triplet("ablation_matrix", matrix_rows)
    write_triplet("ablation_summary", summary_rows)

    payload = {
        "traces": [CASE_LABELS.get(name, name) for name in order],
        "modes": [m.value for m in COMPONENT_ABLATION_MODES],
        "rows": [r.model_dump() for r in matrix_rows],
        "summary": [r.model_dump() for r in summary_rows],
    }
    json_path = out_dir / "ablation_summary.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json_path)

    bad_fn = False
    for row in matrix_rows:
        if row.case == "Benign":
            continue
        for k, v in row.model_dump().items():
            if k == "case":
                continue
            if v == "FN":
                bad_fn = True
                print(f"ERROR: false negative cell {row.case}.{k}={v}", file=sys.stderr)
    if bad_fn:
        sys.exit(1)


if __name__ == "__main__":
    main()
