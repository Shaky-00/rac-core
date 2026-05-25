#!/usr/bin/env bash
# RQ3: sanity check on committed real MCP filesystem expected summaries (paper Table IV).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
OUT="$ROOT/artifacts/rq3_mcp_filesystem/results/mcp_case_study_verification.json"
mkdir -p "$(dirname "$OUT")"

if [[ "${1:-}" == "--live" ]]; then
  shift
  exec python3 -m pytest "$ROOT/tests/test_mcp_real_filesystem_v06_guarded.py" -m optional -q "$@"
fi

export RAC_CORE_ROOT="$ROOT"
python3 <<'PY'
import json
import os
from pathlib import Path

root = Path(os.environ["RAC_CORE_ROOT"])
expected_dir = root / "artifacts" / "rq3_mcp_filesystem" / "expected"
checks = {}

def load(name: str) -> dict:
    p = expected_dir / name
    if not p.is_file():
        raise SystemExit(f"Missing RQ3 expected summary: {p}")
    return json.loads(p.read_text(encoding="utf-8"))

direct = load("direct_demo_summary.json")
planner = load("planner_corpus_summary.json")

if direct.get("total_scenarios") != 3:
    raise SystemExit(f"direct_demo: expected total_scenarios=3, got {direct.get('total_scenarios')!r}")
if direct.get("match_rate") != 1.0:
    raise SystemExit(f"direct_demo: expected match_rate=1.0, got {direct.get('match_rate')!r}")
checks["direct_demo_3_scenarios_all_match"] = True

if planner.get("total_plans") != 14:
    raise SystemExit(f"planner_corpus: expected total_plans=14, got {planner.get('total_plans')!r}")
steps = (planner.get("total_steps_by_variant") or {}).get("FULL_RAC")
if steps != 29:
    raise SystemExit(f"planner_corpus: expected FULL_RAC steps=29, got {steps!r}")
if planner.get("full_rac_blocked_side_effects", planner.get("side_effect_materialized_count_by_variant", {}).get("FULL_RAC")) != 0:
    mb = planner.get("side_effect_materialized_count_by_variant", {}).get("FULL_RAC")
    if mb != 0:
        raise SystemExit(f"planner_corpus: expected FULL_RAC unsafe side effects=0, got {mb!r}")
if planner.get("full_rac_llm_norm_stopped") != 5:
    raise SystemExit(f"planner_corpus: expected full_rac_llm_norm_stopped=5, got {planner.get('full_rac_llm_norm_stopped')!r}")
checks["planner_corpus_table_iv_metrics"] = True

out = root / "artifacts" / "rq3_mcp_filesystem" / "results" / "mcp_case_study_verification.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(
    json.dumps(
        {
            "rq": "RQ3",
            "source_expected_dir": str(expected_dir.relative_to(root)),
            "checks": checks,
            "notes": "Validates committed expected summaries for paper Table IV. Live replay: examples/mcp_real_filesystem_v06/",
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
print(f"OK: RQ3 expected summaries verified; wrote {out.relative_to(root)}")
PY
