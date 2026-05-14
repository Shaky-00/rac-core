#!/usr/bin/env bash
# Smoke tests for artifact evaluators: env + pytest (TraceBench-heavy tests skip if bundle missing).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
bash "$ROOT/scripts/check_env.sh"
exec python3 -m pytest "$ROOT/tests/test_artifact_smoke.py" "$ROOT/tests/test_latency_evaluation.py" -q --tb=short "$@"
