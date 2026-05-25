# Artifacts layout

Runtime experiment outputs are **gitignored**. Only small **expected** reference summaries are committed.

| Path | Role |
|------|------|
| `rq1_tracebench/` | RQ1 paired/core TraceBench conformance |
| `rq2_baselines/` | RQ2 expanded baseline comparison (paper-scale) |
| `rq3_mcp_filesystem/` | RQ3 real MCP filesystem enforcement (Table IV) |
| `rq4_latency/` | RQ4 checking-path latency (quick + full replay scripts) |
| `expected/summaries/` | Compatibility aliases → same JSON as per-RQ `expected/` |
| `results/` | Default output root for `scripts/run_*.sh` (empty except `.gitkeep`) |
| `generated/` | Reserved; not used in the minimal public artifact |

Each `rq*/results/` directory is for fresh runs from the matching scripts. Do not commit large CSV/JSON outputs.
