# Artifact evaluation guide

This document supplements the root [`README.md`](../README.md) for **artifact evaluators**.

## 0. Preconditions

- **Python** 3.11+ on Linux or macOS (Windows/WSL2 acceptable).
- **Sibling checkout:** `rac-core/` and `rac-data/` under the same parent directory.
- **TraceBench paired suite** at `../rac-data/tracebench/paired/` with `controlled_traces/paired/`, or set **`RAC_TRACEBENCH_ROOT`**.

```bash
export RAC_DATA_DIR="$(cd .. && pwd)/rac-data"
```

## 1. Environment check

```bash
bash scripts/check_env.sh
python3 -m pip install -r requirements.txt
python3 -m pip install -e .
```

## 2. RQ1 — Controlled TraceBench coverage / oracle match

```bash
bash scripts/run_tracebench.sh
```

Runs `scripts/run_tracebench.py` with `--variant-group full` (FULL_RAC, baselines, history-aware variants, RAC_WITHOUT ablations).

**Outputs:** `artifacts/results/` (e.g. `tracebench_paired_summary.json`).

**Reference:** `artifacts/rq1_tracebench/expected/paired_core_summary.json`

See [`tracebench_result_notes.md`](tracebench_result_notes.md).

## 3. RQ2 — Baseline coverage on expanded TraceBench

```bash
bash scripts/run_ablation.sh --baselines
bash scripts/run_ablation.sh --ablations
```

Paper-scale expanded suite:

```bash
bash scripts/run_rq2_tracebench.sh
```

Requires `rac-data/tracebench/` with `controlled_traces/expanded/` and composite overlay under `tracebench/composite-overlay/`.

**Reference:** `artifacts/rq2_baselines/expected/expanded_baselines_summary.json`

## 4. RQ3 — Real MCP filesystem enforcement (Table IV)

**Default** — sanity check on committed expected summaries:

```bash
bash scripts/run_mcp_case_study.sh
```

**Live replay** (Node/npx + MCP filesystem server):

```bash
bash scripts/run_mcp_case_study.sh --live
# or: python3 examples/mcp_real_filesystem_v06/run_real_filesystem_case.py
```

**Fixtures:** `examples/mcp_real_filesystem_v06/plans/` (14 deterministic planner JSON workflows).

## 5. RQ4 — Latency

### 5a. Synthetic microbenchmark (quick)

```bash
bash scripts/run_latency.sh --quick
```

Outputs under `artifacts/results/performance/` (environment-dependent; not regression-locked).

### 5b. TraceBench instrumented overhead (paper-scale)

Requires expanded TraceBench under `RAC_DATA_DIR`.

```bash
bash scripts/run_tracebench_overhead.sh --iterations 100
```

**Quick reference only:** `artifacts/rq4_latency/expected/quick_tracebench_overhead_summary.json` (32-trace subset, not full 1248×20 paper run).

## 6. Aggregate runner

```bash
bash scripts/run_all.sh
bash scripts/run_all.sh --quick-latency
bash scripts/run_all.sh --with-mcp
```

## 7. Smoke tests

```bash
bash scripts/check_artifact.sh
python3 -m pytest tests/test_artifact_smoke.py tests/test_latency_evaluation.py -q
```

Full suite (excluding optional MCP): `python3 -m pytest tests -m "not optional" -q`

## 8. Reference outputs

| RQ | Expected summary |
|----|------------------|
| RQ1 | `artifacts/rq1_tracebench/expected/paired_core_summary.json` |
| RQ2 | `artifacts/rq2_baselines/expected/expanded_baselines_summary.json` |
| RQ3 | `artifacts/rq3_mcp_filesystem/expected/direct_demo_summary.json`, `planner_corpus_summary.json` |
| RQ4 | `artifacts/rq4_latency/expected/quick_tracebench_overhead_summary.json` |

Compatibility copies: `artifacts/expected/summaries/`.

Deterministic planner JSON under `examples/llm_plans/` and `examples/mcp_real_filesystem_v06/plans/` — no raw model prompts or provider responses in this artifact.
