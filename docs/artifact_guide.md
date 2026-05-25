# Artifact evaluation guide

This document supplements the root [`README.md`](../README.md) for **artifact evaluators**.

## 0. What this repository provides

- **In-repo:** RAC implementation, tests, replay scripts, committed expected summaries, MCP case-study code and fixtures.
- **External:** Full TraceBench and expanded evaluation corpora via `RAC_DATA_DIR` (not vendored here). See [`../data/README.md`](../data/README.md).

During blind review, start with the **rac-core-only** commands in the README; add `RAC_DATA_DIR` only when you have the separate evaluation bundle.

## 0.1 Preconditions

- **Python 3.11+** on Linux or macOS (Windows/WSL2 acceptable).

```bash
cd rac-core
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
```

## 1. Environment check

```bash
bash scripts/check_env.sh
```

Reports import health and whether a TraceBench layout is visible under `RAC_DATA_DIR` (warning only if absent).

## 2. RQ1 — Controlled TraceBench coverage / oracle match

**Requires** external paired bundle at `$RAC_DATA_DIR/tracebench/paired/` (or `RAC_TRACEBENCH_ROOT`).

```bash
export RAC_DATA_DIR=/path/to/rac-data
bash scripts/run_tracebench.sh
```

Runs `scripts/run_tracebench.py` with `--variant-group full` (FULL_RAC, baselines, history-aware variants, RAC_WITHOUT ablations).

**Outputs:** `artifacts/results/` (e.g. `tracebench_paired_summary.json`).

**Reference (in-repo):** `artifacts/rq1_tracebench/expected/paired_core_summary.json` — 44-case paired/core expected summary. Replay requires external paired data; compare `false_negative_by_variant` for FULL_RAC (=0) and oracle-alignment counts in the CSV companion.

**Metric note:** Paper missed-block plots for the core suite use **27 oracle-BLOCK** traces as the denominator. JSON field `false_negative_by_variant` uses **44** traces (`missed / 44`). Do not equate the two rates.

## 3. RQ2 — Baseline coverage on expanded TraceBench

**Requires** expanded bundle and composite overlay under `RAC_DATA_DIR` (see [`tracebench_format.md`](tracebench_format.md)).

```bash
export RAC_DATA_DIR=/path/to/rac-data
bash scripts/run_ablation.sh --baselines
bash scripts/run_ablation.sh --ablations
bash scripts/run_rq2_tracebench.sh
```

**Reference (in-repo):** `artifacts/rq2_baselines/expected/expanded_baselines_summary.json` — paper-level counts for cross-check (1248 workflows; Static+History **509/1008** missed-block, **50.5%** rate). Full replay requires the expanded data bundle; the committed JSON supports verification without re-running 1,248 workflows.

## 4. RQ3 — MCP filesystem case study (Table IV)

### Default — expected-summary verification

```bash
bash scripts/run_mcp_case_study.sh
```

This **validates committed expected summaries** for the direct filesystem demo and the planner corpus case study. It **does not** contact a live MCP filesystem server. The summaries correspond to the reported direct and planner-corpus filesystem enforcement results (Table IV).

**Reference (in-repo):** `artifacts/rq3_mcp_filesystem/expected/direct_demo_summary.json`, `planner_corpus_summary.json`

**Fixtures (in-repo):** `examples/mcp_real_filesystem_v06/plans/` (14 deterministic planner JSON workflows).

### Optional — live replay (environment-dependent)

Live replay requires Node/npx and the MCP filesystem server package. Results may vary with server binary and sandbox paths.

```bash
bash scripts/run_mcp_case_study.sh --live
# or: python3 examples/mcp_real_filesystem_v06/run_real_filesystem_case.py
```

Use live mode only when the optional dependencies are available; it is not required for artifact smoke review.

## 5. RQ4 — Latency

### 5a. Quick checks (rac-core only)

```bash
bash scripts/run_latency.sh --quick
```

Synthetic microbenchmarks plus a small instrumented subset. Outputs under `artifacts/results/performance/` (environment-dependent; not regression-locked).

**Reference (in-repo):** `artifacts/rq4_latency/expected/quick_tracebench_overhead_summary.json` — **quick-latency expected only** (32-trace subset × 100 iterations). This is **not** the paper’s full **1248×20** TraceBench overhead run and **not** a substitute for Fig. 5.

### 5b. Paper-scale TraceBench overhead

**Requires** expanded TraceBench under `RAC_DATA_DIR`.

```bash
export RAC_DATA_DIR=/path/to/rac-data
bash scripts/run_tracebench_overhead.sh --iterations 100
```

## 6. Aggregate runner

Requires `RAC_DATA_DIR` for TraceBench portions:

```bash
bash scripts/run_all.sh
bash scripts/run_all.sh --quick-latency
bash scripts/run_all.sh --with-mcp    # optional live MCP tests
```

## 7. Smoke tests (rac-core only)

```bash
bash scripts/check_artifact.sh
python3 -m pytest tests/test_artifact_smoke.py tests/test_latency_evaluation.py -q
```

Full suite (excluding optional MCP): `python3 -m pytest tests -m "not optional" -q`

## 8. Reference outputs

| RQ | Expected summary | Role |
|----|------------------|------|
| RQ1 | `artifacts/rq1_tracebench/expected/paired_core_summary.json` | Paired/core 44-case summary; replay needs external paired data |
| RQ2 | `artifacts/rq2_baselines/expected/expanded_baselines_summary.json` | Paper Fig. 4 counts; full replay needs expanded bundle |
| RQ3 | `artifacts/rq3_mcp_filesystem/expected/*.json` | Table IV reference; default script verifies JSON only |
| RQ4 | `artifacts/rq4_latency/expected/quick_tracebench_overhead_summary.json` | Quick latency reference; not full paper overhead |

Compatibility copies: `artifacts/expected/summaries/`.

No raw model prompts or provider responses are included in this artifact.
