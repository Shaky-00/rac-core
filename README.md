# RAC-Core — minimal anonymous artifact

**Runtime Authorization Consistency (RAC)** prototype: a controller-side **pre-commit** checker over typed authorization events for MCP-shaped agentic workflows (manifests/grants, lineage, optional structured output anchors).

## Scope (read first)

- **This repository is `rac-core` only** (implementation, tests, runnable scripts, and small reference summaries). It does **not** bundle the full TraceBench JSON corpus.
- **Datasets live in `rac-data`** (sibling checkout). Set **`RAC_DATA_DIR`** (default `../rac-data`) or override a single bundle with **`RAC_TRACEBENCH_ROOT`** (see `data/README.md` and `../rac-data/README.md`).
- **TraceBench** is an **oracle-labeled conformance suite** (controlled traces + independent oracle labels). It is **not** a measurement of real-world attack prevalence.
- **Latency numbers** from `scripts/run_latency.sh` are **environment-dependent**, in-process measurements of the **checking path** (adapter → verifier → checker). They are **not** end-to-end production latency and are **not** regression-locked in this repository.
- **Missed-block rates in the paper** use **27 oracle-BLOCK traces** as the denominator for the paired core suite. The machine summary field `false_negative_by_variant` uses **all 44 traces** as the denominator; see `docs/tracebench_result_notes.md`.

Optional paper figures are regenerated locally via `scripts/paper_optional/` and `bash scripts/run_latency.sh`.

## Layout

| Path | Role |
|------|------|
| `src/rac_core/` | Checker, adapter, stores, validation, evaluation |
| `tests/` | Core tests; `pytest -m optional` enables MCP demo / stress corpora tests |
| `scripts/*.sh`, `scripts/run_*.py` | **Minimal reproduction** entry points |
| `scripts/paper_optional/` | Optional helpers (matplotlib); writes under `artifacts/generated/` |
| `data/` | Pointers to external datasets (no full TraceBench vendored here) |
| `artifacts/results/` | **Runtime outputs** (gitignored) |
| `artifacts/expected/summaries/` | Small reference **JSON** snapshots |
| `examples/` | MCP demos; deterministic planner JSON under `examples/llm_plans/` |

## Environment

- Python **3.11+** (see `pyproject.toml`).
- `python3 -m pip install -r requirements.txt && python3 -m pip install -e .`
- **matplotlib**: only for `scripts/paper_optional/` (`pip install -e ".[dev]"`).

## Minimal reviewer path (~5 minutes)

Clone **`rac-core`** and **`rac-data`** as siblings, populate `rac-data/tracebench/paired/` per the data README, then:

```bash
cd rac-core
export RAC_DATA_DIR="$(cd .. && pwd)/rac-data"
python3 -m pip install -r requirements.txt && python3 -m pip install -e .

bash scripts/check_env.sh
bash scripts/check_artifact.sh

# TraceBench paired suite (baselines only; requires data under RAC_DATA_DIR)
PYTHONPATH=src python3 scripts/run_tracebench.py \
  --output-dir artifacts/results/reviewer_smoke \
  --variant-group baselines

# MCP case study sanity (committed JSON; no live servers)
bash scripts/run_mcp_case_study.sh

# Latency microbenchmark (quick grid)
bash scripts/run_latency.sh --quick
```

Full static sweep (longer): `bash scripts/run_all.sh` (optional `--quick-latency`, `--with-mcp`).

Per-RQ commands: `run_tracebench.sh`, `run_ablation.sh`, `run_latency.sh`, `run_tracebench_overhead.sh`, `run_mcp_case_study.sh` (see `docs/artifact_guide.md`).

## Outputs

- Fresh runs write under **`artifacts/results/`** (e.g. `tracebench_paired_baselines_summary.json` from `run_tracebench.py`).
- **`artifacts/expected/summaries/`** holds reference JSON for optional diffing when the TraceBench bundle matches this revision.

## License

See `LICENSE` (anonymous placeholder).
