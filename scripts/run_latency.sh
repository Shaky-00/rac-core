#!/usr/bin/env bash
# RQ4: synthetic latency microbenchmarks (p50 / p95 / p99 in JSON + CSV).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p "$ROOT/artifacts/results/performance"
exec python3 "$ROOT/scripts/run_latency_evaluation.py" --output-dir "$ROOT/artifacts/results/performance" "$@"
