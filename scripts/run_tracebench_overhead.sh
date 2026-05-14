#!/usr/bin/env bash
# TraceBench instrumented replay overhead (RQ4 / appendix; requires TraceBench bundle).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p "$ROOT/artifacts/results"
exec python3 "$ROOT/scripts/run_rac_tracebench_overhead.py" --output-dir "$ROOT/artifacts/results" "$@"
