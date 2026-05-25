# RQ4 — Checking-path latency

**Expected file:** `expected/quick_tracebench_overhead_summary.json`

- **Type:** **Quick-latency expected only** — 32-trace subset × 100 iterations (see `label` / `description` fields in the JSON).
- **Not:** The paper’s full **1248 workflows × 20 iterations** overhead study (Fig. 5). Do not treat this file as the complete Fig. 5 experiment.
- **Rac-core only:** `bash scripts/run_latency.sh --quick` — synthetic microbenchmarks + small instrumented replay; writes to `artifacts/results/performance/` (environment-dependent).

**Paper-scale replay (requires `RAC_DATA_DIR`):**

```bash
export RAC_DATA_DIR=/path/to/rac-data
bash scripts/run_tracebench_overhead.sh
```
