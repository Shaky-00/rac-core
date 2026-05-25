# Artifact evaluation guide

This document supplements the root [`README.md`](../README.md) for **artifact evaluators**.

## 0. Preconditions

- **Python** 3.11+ on Linux or macOS (Windows/WSL2 acceptable).
- **Sibling checkout:** `rac-core/` and `rac-data/` under the same parent directory.
- **TraceBench paired suite** installed at `../rac-data/tracebench/paired/` with `controlled_traces/paired/`, or set **`RAC_TRACEBENCH_ROOT`** to the bundle root.

```bash
export RAC_DATA_DIR="$(cd .. && pwd)/rac-data"
```

If `scripts/check_env.sh` warns about missing TraceBench data, static replay commands will fail until `rac-data` is populated.

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

**Outputs** (under `artifacts/results/`):

- `tracebench_paired_results.csv` / `tracebench_paired_summary.json` (full sweep via `run_tracebench.py`)
- `tracebench_paired_baselines_{results.csv,summary.json}` or `tracebench_paired_ablations_*` for split runs
- `tracebench_paired_benign_summary.{json,csv}`

See [`tracebench_result_notes.md`](tracebench_result_notes.md) for field semantics.

**Failures:** missing bundle → set `RAC_DATA_DIR` / `RAC_TRACEBENCH_ROOT`; parse errors → corrupt bundle.

## 3. RQ2 — Baselines vs RAC_WITHOUT ablations

```bash
bash scripts/run_ablation.sh --baselines
bash scripts/run_ablation.sh --ablations
```

Expanded suite (paper-scale): `bash scripts/run_rq2_tracebench.sh` (requires `rac-data/tracebench/` with `controlled_traces/expanded/`).

## 4. RQ3 — MCP case study (optional)

**Default** — sanity check on committed `examples/mcp_live_enforcement/case_outputs/mcp_case_study_results.json`:

```bash
bash scripts/run_mcp_case_study.sh
```

**Live replay** (environment-dependent):

```bash
bash scripts/run_mcp_case_study.sh --live
```

**Filesystem MCP demo** — `examples/mcp_real_filesystem_v06/` (may need Node + `RAC_REAL_MCP_SERVER_CMD`); not part of `run_all.sh` by default.

## 5. RQ4 — Latency

### 5a. Synthetic microbenchmark

```bash
bash scripts/run_latency.sh --quick
```

Outputs under `artifacts/results/performance/` (not regression-locked).

### 5b. TraceBench instrumented overhead

Requires expanded TraceBench under `RAC_DATA_DIR`.

```bash
bash scripts/run_tracebench_overhead.sh --iterations 100
```

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

Full suite (excluding optional MCP demos): `python3 -m pytest tests -m "not optional" -q`

## 8. Reference outputs

`artifacts/expected/summaries/` — small reference JSON. Oracle alignment should match when the TraceBench bundle matches this revision.

Deterministic planner JSON under `examples/llm_plans/` — no raw model prompts or provider responses in this artifact.

## 9. Optional figures

`scripts/paper_optional/` (matplotlib). Inputs from `artifacts/results/` or `artifacts/expected/`; outputs under `artifacts/generated/`.
