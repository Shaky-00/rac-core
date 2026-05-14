# Artifact evaluation guide

This document supplements the root [`README.md`](../README.md) for **artifact evaluators**: how to run experiments, where outputs land, and how to recover from common failures.

## 0. Preconditions

- **Python** 3.11+ on Linux or macOS (Windows/WSL2 is acceptable if paths and line endings behave normally).
- **Repository root** as the working directory for all commands unless noted.
- **TraceBench bundle** unpacked so that `controlled_traces/paired/` exists under one of:
  - `data/tracebench/rac_tracebench_v06/`
  - `mcp_data/rac_tracebench_v06/` (sibling-style layout under the parent of the repo is also searched; see loader)
  - or path exported as `RAC_TRACEBENCH_ROOT`

If `scripts/check_env.sh` prints a TraceBench warning, static TraceBench commands will fail until the bundle is installed.

## 1. Environment check

```bash
bash scripts/check_env.sh
python3 -m pip install -r requirements.txt
python3 -m pip install -e .
```

Import errors: ensure `pip install -e .` was run from the repository root (`src/` layout).

## 2. RQ1 — Controlled TraceBench coverage / oracle match

**Command**

```bash
bash scripts/run_tracebench.sh
```

**What it does**  
Runs `scripts/run_rac_tracebench_v06.py` with `--variant-group full` (FULL_RAC, baselines, history-aware variants, and all `RAC_WITHOUT_*` ablations).

**Outputs** (under `artifacts/results/` by default)

- `rac_tracebench_v06_results.csv`
- `rac_tracebench_v06_summary.json`
- `rac_tracebench_v06_benign_summary.{json,csv}`

**Interpretation**  
`matched_oracle` per row; summary JSON exposes `match_rate_by_variant`, `false_negative_by_variant`, and `per_family_results`. FULL_RAC should match oracle labels for all traces when the TraceBench bundle matches this repository revision. Field-level notes: [`tracebench_result_notes.md`](tracebench_result_notes.md).

**Failures**

- `RAC-TraceBench root not found` → install bundle or set `RAC_TRACEBENCH_ROOT`.
- JSON/YAML parse errors → bundle corrupted or wrong version.

## 3. RQ2 — Baselines vs RAC_WITHOUT ablations

The same checker and replay pipeline are used; **variant subsets** only change which columns are emitted (semantic per variant unchanged).

**Baselines (including history-aware comparisons)**

```bash
bash scripts/run_ablation.sh --baselines
```

**RAC_WITHOUT ablations only**

```bash
bash scripts/run_ablation.sh --ablations
```

**Outputs**

- `rac_tracebench_v06_baselines_{results.csv,summary.json}`
- `rac_tracebench_v06_ablations_{results.csv,summary.json}`

For a single combined table, use `bash scripts/run_tracebench.sh` (full sweep).

## 4. RQ3 — MCP case study (optional)

**Deterministic check (no live MCP servers)** — validates committed JSON from a prior guarded run:

```bash
bash scripts/run_mcp_case_study.sh
```

Writes `artifacts/results/mcp_case_study_verification.json`.

**Live in-process replay** (Python `mcp` package; exercises `examples/mcp_live_enforcement`):

```bash
bash scripts/run_mcp_case_study.sh --live
```

**Node / official MCP filesystem server**  
Real filesystem demos under `examples/mcp_real_filesystem_v06/` may require Node and an MCP server binary; those paths are **not** part of `scripts/run_all.sh` by default. See `examples/mcp_real_filesystem_v06/README.md` and environment variables `RAC_REAL_MCP_SERVER_CMD` in tests.

## 5. RQ4 — Latency

### 5a. Synthetic microbenchmark (no TraceBench)

```bash
bash scripts/run_latency.sh --quick
```

Omit `--quick` for the full grid (longer). Outputs under `artifacts/results/performance/`: `latency_*.csv` and `.json` with per-scenario samples and aggregated summaries (including p50 / p95 / p99 where applicable).

### 5b. TraceBench instrumented replay overhead

Requires the TraceBench bundle.

```bash
bash scripts/run_tracebench_overhead.sh --iterations 100
```

Writes `rac_tracebench_v06_overhead.csv` and `rac_tracebench_v06_overhead_summary.json` under `artifacts/results/`.

## 6. Aggregate runner

```bash
bash scripts/run_all.sh              # core static path + overhead + latency (full grid)
bash scripts/run_all.sh --quick-latency
bash scripts/run_all.sh --with-mcp    # additionally runs live MCP pytest (may fail if environment lacks deps)
```

If `--with-mcp` fails, inspect stderr; core TraceBench outputs from earlier steps are still valid.

## 7. Smoke tests

```bash
bash scripts/check_artifact.sh
# or
python3 -m pytest tests/test_artifact_smoke.py tests/test_latency_evaluation.py -q
```

Full suite excluding optional MCP/stress demos:

```bash
python3 -m pytest tests -m "not optional" -q
```

## 8. Reference outputs

Under `artifacts/expected/summaries/` are small reference summary JSON files. Latency-related numbers may float; oracle alignment and missed-block **counts** derived from decisions should be stable for the same bundle and revision.

The planner-style corpus under `examples/llm_plans/` is provided as **normalized deterministic JSON** for replay. This artifact does **not** ship raw model prompts or provider responses.

## 9. Optional derived tables and figures

Optional helpers live under `scripts/paper_optional/` (see `scripts/paper_optional/README.md`). They may require **matplotlib** and read inputs from `artifacts/results/` or `artifacts/expected/`, writing to `artifacts/generated/`. They are **not** part of the minimal artifact evaluation path.
