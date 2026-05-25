#!/usr/bin/env bash
# Aggregate entry point: core static experiments (TraceBench + baselines/ablations + latency).
# MCP live scenarios are optional (--with-mcp). TraceBench requires the JSON bundle (see data/README.md).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export RAC_DATA_DIR="${RAC_DATA_DIR:-$(cd "$ROOT/.." && pwd)/rac-data}"

WITH_MCP=0
LATENCY_ARGS=()
for a in "$@"; do
  case "$a" in
    --with-mcp) WITH_MCP=1 ;;
    --quick-latency) LATENCY_ARGS+=(--quick) ;;
    *) ;;
  esac
done

tb_root="${RAC_TRACEBENCH_ROOT:-}"
if [[ -z "$tb_root" ]]; then
  if [[ -d "$RAC_DATA_DIR/tracebench/paired/controlled_traces/paired" ]]; then
    export RAC_TRACEBENCH_ROOT="$RAC_DATA_DIR/tracebench/paired"
  elif [[ -d "$RAC_DATA_DIR/tracebench/controlled_traces/paired" ]]; then
    export RAC_TRACEBENCH_ROOT="$RAC_DATA_DIR/tracebench"
  elif [[ -d "$ROOT/data/tracebench/paired/controlled_traces/paired" ]]; then
    export RAC_TRACEBENCH_ROOT="$ROOT/data/tracebench/paired"
  fi
fi

if [[ ! -d "${RAC_TRACEBENCH_ROOT:-}/controlled_traces/paired" ]]; then
  echo "ERROR: TraceBench paired suite not found. Set RAC_TRACEBENCH_ROOT or install under:" >&2
  echo "  $RAC_DATA_DIR/tracebench/paired/" >&2
  echo "See data/README.md and ../rac-data/README.md" >&2
  exit 1
fi

bash "$ROOT/scripts/run_tracebench.sh"
bash "$ROOT/scripts/run_ablation.sh" --baselines
bash "$ROOT/scripts/run_ablation.sh" --ablations
bash "$ROOT/scripts/run_tracebench_overhead.sh" --iterations 100

if [[ ${#LATENCY_ARGS[@]} -eq 0 ]]; then
  echo "NOTE: running full latency grid (can take several minutes). Re-run with --quick-latency for a shorter path."
  bash "$ROOT/scripts/run_latency.sh"
else
  bash "$ROOT/scripts/run_latency.sh" "${LATENCY_ARGS[@]}"
fi

if [[ "$WITH_MCP" -eq 1 ]]; then
  if ! bash "$ROOT/scripts/run_mcp_case_study.sh" --live; then
    echo "WARN: optional MCP live pytest failed (see messages above); core TraceBench outputs are unaffected." >&2
  fi
else
  bash "$ROOT/scripts/run_mcp_case_study.sh"
fi

echo "run_all: done"
