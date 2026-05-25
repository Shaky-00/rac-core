#!/usr/bin/env bash
# RQ3: optional MCP scenarios. Default checks committed JSON (sanity + structural invariants);
# --live runs in-process MCP tests (environment-dependent).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
OUT="$ROOT/artifacts/results/mcp_case_study_verification.json"
mkdir -p "$ROOT/artifacts/results"

if [[ "${1:-}" == "--live" ]]; then
  shift
  exec python3 -m pytest "$ROOT/tests/test_mcp_live_enforcement_case.py" -q "$@"
fi

export RAC_CORE_ROOT="$ROOT"
python3 <<'PY'
import json
import os
from pathlib import Path

root = Path(os.environ["RAC_CORE_ROOT"])
p = root / "examples" / "mcp_live_enforcement" / "case_outputs" / "mcp_case_study_results.json"
if not p.is_file():
    raise SystemExit(f"Missing committed case study output: {p}")
data = json.loads(p.read_text(encoding="utf-8"))
rows = data.get("rows") or []
if not isinstance(rows, list) or not rows:
    raise SystemExit("rows must be non-empty list")

checks: dict[str, object] = {
    "block_rows_require_no_server_issue": True,
    "summary_missed_block_zero": None,
}

for i, row in enumerate(rows):
    if not isinstance(row, dict):
        raise SystemExit(f"row {i} must be object")
    if row.get("rac_decision") == "BLOCK" and "issued_to_server" in row:
        if row.get("issued_to_server") is not False:
            raise SystemExit(
                f"BLOCK row must have issued_to_server=false when present "
                f"(scenario={row.get('scenario_id')!r} step={row.get('step_id')!r})"
            )

summary = data.get("summary")
if isinstance(summary, dict) and "missed_block" in summary:
    mb = summary.get("missed_block")
    checks["summary_missed_block_zero"] = mb == 0
    if mb != 0:
        raise SystemExit(f"summary.missed_block expected 0, got {mb!r}")

out = root / "artifacts" / "results" / "mcp_case_study_verification.json"
out.write_text(
    json.dumps(
        {
            "source": str(p.relative_to(root)),
            "row_count": len(rows),
            "checks": checks,
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
print(
    f"OK: verified committed MCP case study JSON ({len(rows)} rows); "
    f"wrote {out.relative_to(root)}"
)
PY
