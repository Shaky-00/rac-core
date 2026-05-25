#!/usr/bin/env bash
# RQ1 / controlled TraceBench: static replay, CSV + JSON summaries.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p "$ROOT/artifacts/results"
exec python3 "$ROOT/scripts/run_tracebench.py" --output-dir "$ROOT/artifacts/results" --variant-group full "$@"
