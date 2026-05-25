#!/usr/bin/env bash
# RQ2: expanded TraceBench baseline replay (paper-scale; requires rac-data).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export RAC_DATA_DIR="${RAC_DATA_DIR:-$(cd "$ROOT/.." && pwd)/rac-data}"
if [[ -z "${RAC_TRACEBENCH_ROOT:-}" ]]; then
  if [[ -d "$RAC_DATA_DIR/tracebench/controlled_traces/core" ]]; then
    export RAC_TRACEBENCH_ROOT="$RAC_DATA_DIR/tracebench"
  elif [[ -d "$RAC_DATA_DIR/tracebench/core/controlled_traces/core" ]]; then
    export RAC_TRACEBENCH_ROOT="$RAC_DATA_DIR/tracebench/core"
  fi
fi
OUT="${RQ2_OUTPUT_DIR:-$ROOT/artifacts/rq2_baselines/results}"
mkdir -p "$OUT"

PYTHONPATH=src python3 scripts/run_rac_tracebench_v1.py \
  --root "${RAC_TRACEBENCH_ROOT:?Set RAC_TRACEBENCH_ROOT or install expanded suite under RAC_DATA_DIR/tracebench}" \
  --suite expanded \
  --include-mixed true \
  --variant-group rq2_full \
  --output-dir "$OUT" \
  --rq2-overlay \
  --write-rq2-aux

PYTHONPATH=src python3 scripts/rq2_sanity_check.py --summary "$OUT/rac_tracebench_v1_expanded_rq2_summary.json"

echo "RQ2 outputs: $OUT"
echo "Compare missed-block metrics to artifacts/rq2_baselines/expected/expanded_baselines_summary.json"
