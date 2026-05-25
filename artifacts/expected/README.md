# Expected summaries (compatibility entry)

Per-RQ canonical copies live under `artifacts/rq*/expected/`. This directory mirrors the same small JSON files for paths that reference `artifacts/expected/summaries/`.

These files are **reference summaries for cross-checking paper metrics**. They do not imply that full evaluation data is vendored in `rac-core`.

| File | Canonical path | Notes |
|------|----------------|-------|
| `tracebench_paired_core_summary.json` | `../rq1_tracebench/expected/paired_core_summary.json` | RQ1 paired 44-case; replay needs external paired data |
| `tracebench_expanded_baselines_summary.json` | `../rq2_baselines/expected/expanded_baselines_summary.json` | RQ2 Fig. 4 counts; full replay needs expanded bundle |
| `mcp_filesystem_direct_demo_summary.json` | `../rq3_mcp_filesystem/expected/direct_demo_summary.json` | RQ3 direct demo; default script verifies JSON only |
| `mcp_filesystem_planner_corpus_summary.json` | `../rq3_mcp_filesystem/expected/planner_corpus_summary.json` | RQ3 planner corpus; Table IV reference |
| `quick_tracebench_overhead_summary.json` | `../rq4_latency/expected/quick_tracebench_overhead_summary.json` | RQ4 **quick** latency only; not full 1248×20 run |

See `artifacts/rq*/README.md` for details.
