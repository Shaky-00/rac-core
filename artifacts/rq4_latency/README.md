# RQ4 — Checking-path latency

**Quick (synthetic + small replay):** `bash scripts/run_latency.sh --quick` → `artifacts/results/performance/`

**Paper-scale (expanded TraceBench replay):** `bash scripts/run_tracebench_overhead.sh` → `artifacts/results/`

**Expected:** `quick_tracebench_overhead_summary.json` is a **32-trace quick reference only**, not the paper full-suite run (1248 workflows × 20 iterations).
