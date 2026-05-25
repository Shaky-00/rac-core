#!/usr/bin/env bash
# TraceBench paired suite: baseline or ablation variant subsets (same checker pipeline).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p "$ROOT/artifacts/results"
GROUP=full
forward=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --baselines) GROUP=baselines ;;
    --ablations) GROUP=ablations ;;
    *) forward+=("$1") ;;
  esac
  shift
done
exec python3 "$ROOT/scripts/run_tracebench.py" --output-dir "$ROOT/artifacts/results" --variant-group "$GROUP" "${forward[@]}"
