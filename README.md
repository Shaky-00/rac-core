# RAC-Core — minimal anonymous artifact

**Runtime Authorization Consistency (RAC)** prototype: a controller-side **pre-commit** checker over typed authorization events for MCP-shaped agentic workflows (manifests/grants, lineage, optional structured output anchors).

## Artifact scope (read first)

This repository provides the **RAC core implementation**, **code-level smoke tests**, **replay scripts**, **committed expected summaries**, and a **data-bundle interface** (`RAC_DATA_DIR` / `RAC_TRACEBENCH_ROOT`).

It does **not** vendor the full evaluation data bundle (TraceBench JSON corpora, expanded suites, or planner replay archives). TraceBench replay commands read traces from an **external directory** configured through `RAC_DATA_DIR` (see [`data/README.md`](data/README.md)).

**Without the external data bundle**, reviewers can still:

- inspect the mechanism implementation under `src/rac_core/`;
- run `scripts/check_artifact.sh` and related unit tests;
- run **RQ3 expected-summary verification** (`scripts/run_mcp_case_study.sh`);
- run **latency quick checks** (`scripts/run_latency.sh --quick`).

**With the external data bundle** (sibling layout below), reviewers can additionally run TraceBench paired replay and other data-dependent drivers documented in [`docs/artifact_guide.md`](docs/artifact_guide.md).

During blind review, this artifact link is intended for **code inspection and smoke-level checks**; full TraceBench replay requires the separate evaluation bundle.

## External data layout

Expected sibling checkout (data bundle supplied separately):

```text
parent/
├── rac-core/          # this repository
└── rac-data/          # evaluation bundle (not included here)
```

Set `export RAC_DATA_DIR=/path/to/rac-data` (default if unset: `../rac-data` relative to this repo). See [`data/README.md`](data/README.md) for required directory names.

## What is included vs external

| Included in `rac-core` | External via `RAC_DATA_DIR` |
|------------------------|-----------------------------|
| Checker, adapter, stores, validation harness | TraceBench paired / core / expanded JSON |
| Tests and smoke scripts | Composite-drift overlay (RQ2 paper-scale) |
| Expected summary JSON under `artifacts/rq*/expected/` | Planner replay corpora (if used beyond committed fixtures) |
| MCP filesystem demo code + planner JSON under `examples/` | — |

- **TraceBench** is an **oracle-labeled conformance suite** (controlled traces + independent oracle labels). It is **not** a measurement of real-world attack prevalence.
- **Latency numbers** from `scripts/run_latency.sh` are **environment-dependent**, in-process measurements of the **checking path**. They are **not** end-to-end production latency.
- **Paper missed-block rates** on the 44-case paired core suite normalize by **27 oracle-BLOCK** traces. The field `false_negative_by_variant` in paired summary JSON uses **all 44 traces** as the denominator (`missed / 44`). Compare oracle-alignment counts, not raw rates, when cross-checking RQ1.

## Layout

| Path | Role |
|------|------|
| `src/rac_core/` | Checker, adapter, stores, validation, evaluation |
| `tests/` | Core tests; `pytest -m optional` enables live MCP filesystem tests |
| `scripts/*.sh`, `scripts/run_*.py` | Reproduction entry points |
| `data/` | Data-bundle interface (no full TraceBench vendored here) |
| `artifacts/rq*/` | Per-RQ expected summaries + gitignored `results/` |
| `examples/mcp_real_filesystem_v06/` | RQ3 filesystem case-study code and planner fixtures |
| `examples/llm_plans/` | Small taxonomy planner JSON fixtures |

## Environment

- **Python 3.11+** (see `pyproject.toml`).

```bash
python3.11 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```

## Quick start — commands that run from `rac-core` only

No `RAC_DATA_DIR` required:

```bash
cd rac-core
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .

bash scripts/check_env.sh          # warns if external bundle absent
bash scripts/check_artifact.sh     # code-level smoke tests

bash scripts/run_mcp_case_study.sh # RQ3: expected-summary verification (Table IV reference JSON)
bash scripts/run_latency.sh --quick
```

`scripts/run_mcp_case_study.sh` **does not** start a live MCP filesystem server by default; it validates committed expected summaries for the direct demo and planner corpus case study. Optional live replay is documented in [`docs/artifact_guide.md`](docs/artifact_guide.md).

## Quick start — commands that require `RAC_DATA_DIR`

Point `RAC_DATA_DIR` at the external evaluation bundle (paired TraceBench at minimum):

```bash
export RAC_DATA_DIR=/path/to/rac-data

PYTHONPATH=src python3 scripts/run_tracebench.py \
  --output-dir artifacts/results/reviewer_smoke \
  --variant-group baselines
```

Paper-scale commands (expanded suite, composite overlay, full overhead replay) are listed in [`docs/artifact_guide.md`](docs/artifact_guide.md) and require additional bundle paths under `rac-data/tracebench/`.

## Figures and reference outputs

This artifact does **not** ship scripts to regenerate paper Fig. 4 / Fig. 5. Reviewers can cross-check committed **expected summaries** under `artifacts/rq*/expected/` against reported counts. See [`artifacts/README.md`](artifacts/README.md).

Fresh experiment outputs write under **`artifacts/results/`** or **`artifacts/rq*/results/`** (gitignored). Do not commit generated CSV/JSON from local runs.

## Further reading

- [`docs/artifact_guide.md`](docs/artifact_guide.md) — per-RQ commands and expected files
- [`docs/design_overview.md`](docs/design_overview.md) — code map
- [`docs/tracebench_format.md`](docs/tracebench_format.md) — bundle layout when data is available

## License

See `LICENSE` (anonymous placeholder).
