"""Generate component-specific ablation matrix (B / M / A cells).

Run from repository root:
  python scripts/generate_ablation_matrix.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
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


def main() -> None:
    out_dir = ROOT / "artifacts" / "tables"
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

    matrix_rows = build_component_ablation_matrix_rows(
        results,
        trace_order=order,
        trace_labels={n: n for n in order},
        miss_mode_by_trace=miss_map,
        benign_trace_names=benign_names,
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

    write_triplet("ablation_component_matrix", matrix_rows)

    payload = {
        "traces": order,
        "modes": [m.value for m in COMPONENT_ABLATION_MODES],
        "rows": [r.model_dump() for r in matrix_rows],
    }
    json_path = out_dir / "ablation_component_matrix.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json_path)

    bad_fn = False
    for row in matrix_rows:
        if row.case in benign_names:
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
