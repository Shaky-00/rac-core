#!/usr/bin/env bash
# RQ3: optional MCP scenarios. Default checks committed results; --live runs in-process MCP tests.
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
out = root / "artifacts" / "results" / "mcp_case_study_verification.json"
out.write_text(
    json.dumps({"source": str(p.relative_to(root)), "row_count": len(rows)}, indent=2) + "\n",
    encoding="utf-8",
)
print(f"OK: verified committed MCP case study JSON ({len(rows)} rows); wrote {out.relative_to(root)}")
PY
