# RAC-Core — minimal anonymous artifact

**Runtime Authorization Consistency (RAC)** prototype: a controller-side **pre-commit** checker over typed authorization events for MCP-shaped agentic workflows (manifests/grants, lineage, optional structured output anchors).

## Artifact scope (read first)

| Repository | Role |
|------------|------|
| **rac-core** (this repo) | Core implementation, tests, replay scripts, committed expected summaries |
| **rac-data-review** (sibling) | Minimal anonymous review data bundle — **44-case paired TraceBench** suite |

Clone both as **sibling directories**. The full expanded TraceBench corpus, planner replay archives, and paper-scale latency runs are **not** in this anonymous submission; they may be provided during **formal artifact evaluation** if the paper is accepted.

### What reviewers can do (smoke path)

1. Inspect `src/rac_core/`.
2. Run `scripts/check_artifact.sh` (no data bundle required).
3. Run **RQ3 expected-summary verification** (`scripts/run_mcp_case_study.sh`) — no live MCP server.
4. Run **latency quick checks** (`scripts/run_latency.sh --quick`).
5. With **rac-data-review**, replay the **44-case paired** TraceBench suite and compare against committed expected summaries under `artifacts/rq*/expected/`.

### What reviewers cannot fully reproduce here

- RQ2 expanded suite (~1,248 workflows) — use committed `artifacts/rq2_baselines/expected/expanded_baselines_summary.json` for cross-check only.
- Paper Fig. 4 / Fig. 5 regeneration and full **1248×20** overhead runs.

## Sibling layout and `RAC_DATA_DIR`

```text
parent/
├── rac-core/            # this repository
└── rac-data-review/     # minimal anonymous data bundle (required for TraceBench replay)
```

```bash
export RAC_DATA_DIR="$(cd ../rac-data-review && pwd)"
```

If unset, `scripts/check_env.sh` prefers `../rac-data-review` when present, else `../rac-data`. See [`data/README.md`](data/README.md).

## Environment

- **Python 3.11+** (see `pyproject.toml`).

```bash
cd rac-core
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
```

## Quick start — rac-core only (no data bundle)

```bash
bash scripts/check_env.sh
bash scripts/check_artifact.sh
bash scripts/run_mcp_case_study.sh   # expected-summary verification only
bash scripts/run_latency.sh --quick
```

`run_mcp_case_study.sh` does **not** start a live MCP filesystem server by default.

## Quick start — with rac-data-review

```bash
export RAC_DATA_DIR="$(cd ../rac-data-review && pwd)"
bash scripts/check_env.sh

PYTHONPATH=src python3 scripts/run_tracebench.py \
  --output-dir artifacts/results/reviewer_smoke \
  --variant-group baselines
```

Paper-scale commands (expanded suite, composite overlay, full overhead) are in [`docs/artifact_guide.md`](docs/artifact_guide.md) and need additional data not shipped in the anonymous bundle.

## Layout

| Path | Role |
|------|------|
| `src/rac_core/` | Checker, adapter, stores, validation, evaluation |
| `tests/` | Core tests; `pytest -m optional` for live MCP |
| `scripts/` | Reviewer entry points (`check_*`, `run_tracebench.py`, `run_latency.sh`, …) |
| `artifacts/rq*/expected/` | Committed reference summaries (cross-check paper counts) |
| `examples/mcp_real_filesystem_v06/` | RQ3 filesystem case-study code and planner fixtures |

## Metric notes

- **TraceBench** is an oracle-labeled **conformance** suite, not a prevalence study.
- Paper missed-block rates on the 44-case core suite use **27 oracle-BLOCK** traces as the denominator. JSON field `false_negative_by_variant` uses **44** (`missed / 44`).

## Further reading

- [`docs/artifact_guide.md`](docs/artifact_guide.md) — per-RQ commands
- [`docs/design_overview.md`](docs/design_overview.md) — code map
- [`docs/tracebench_format.md`](docs/tracebench_format.md) — bundle layout

## License

See `LICENSE` (anonymous placeholder).
