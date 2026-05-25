# RAC-Core — minimal anonymous artifact

**Runtime Authorization Consistency (RAC)** prototype: a controller-side **pre-commit** checker over typed authorization events for MCP-shaped agentic workflows (manifests/grants, lineage, optional structured output anchors).

## Scope (read first)

- **This repository is `rac-core` only** (implementation, tests, runnable scripts, and small reference summaries). It does **not** bundle the full TraceBench JSON corpus.
- **Datasets live in `rac-data`** (sibling checkout). Set **`RAC_DATA_DIR`** (default `../rac-data`) or override a single bundle with **`RAC_TRACEBENCH_ROOT`** (see `data/README.md`).
- **TraceBench** is an **oracle-labeled conformance suite** (controlled traces + independent oracle labels). It is **not** a measurement of real-world attack prevalence.
- **Latency numbers** from `scripts/run_latency.sh` are **environment-dependent**, in-process measurements of the **checking path**. They are **not** end-to-end production latency.
- **Missed-block rates in the paper** use **27 oracle-BLOCK traces** as the denominator for the paired core suite. The machine summary field `false_negative_by_variant` uses **all 44 traces** as the denominator; see `docs/tracebench_result_notes.md`.

## Layout

| Path | Role |
|------|------|
| `src/rac_core/` | Checker, adapter, stores, validation, evaluation |
| `tests/` | Core tests; `pytest -m optional` enables live MCP filesystem tests |
| `scripts/*.sh`, `scripts/run_*.py` | **Minimal reproduction** entry points |
| `data/` | Pointers to external datasets (no full TraceBench vendored here) |
| `artifacts/rq*/` | Per-RQ expected summaries + gitignored `results/` |
| `examples/mcp_real_filesystem_v06/` | RQ3 real MCP filesystem demo (Table IV) |
| `examples/llm_plans/` | Small taxonomy planner JSON fixtures |

## Environment

- Python **3.11+** (see `pyproject.toml`).
- `python3 -m pip install -r requirements.txt && python3 -m pip install -e .`

## Minimal reviewer path (~5 minutes)

Clone **`rac-core`** and **`rac-data`** as siblings, populate `rac-data/tracebench/paired/` per the data README, then:

```bash
cd rac-core
export RAC_DATA_DIR="$(cd .. && pwd)/rac-data"
python3 -m pip install -r requirements.txt && python3 -m pip install -e .

bash scripts/check_env.sh
bash scripts/check_artifact.sh

PYTHONPATH=src python3 scripts/run_tracebench.py \
  --output-dir artifacts/results/reviewer_smoke \
  --variant-group baselines

bash scripts/run_mcp_case_study.sh

bash scripts/run_latency.sh --quick
```

Full static sweep (longer): `bash scripts/run_all.sh` (optional `--quick-latency`, `--with-mcp` for live filesystem tests).

Per-RQ commands: see `docs/artifact_guide.md` and `artifacts/README.md`.

## Outputs

- Fresh runs write under **`artifacts/results/`** or **`artifacts/rq*/results/`** (gitignored).
- Small reference JSON under **`artifacts/rq*/expected/`** and **`artifacts/expected/summaries/`**.

## License

See `LICENSE` (anonymous placeholder).
