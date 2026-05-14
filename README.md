# RAC-Core — minimal anonymous artifact

**Runtime Authorization Consistency (RAC) v0.6** prototype: a controller-side **pre-commit** checker over typed authorization events for MCP-shaped agentic workflows (manifests/grants, lineage, optional output anchors).

This repository is a **slim anonymous artifact**: it does **not** ship historical static figures, large raw logs, or a top-level experiment export tree named `results`. Reviewers reproduce metrics by **running** the bundled scripts; a few **reference JSON summaries** live under `artifacts/expected/summaries/` for optional diffing.

## Layout

| Path | Role |
|------|------|
| `src/rac_core/` | Checker, adapter, stores, validation, evaluation |
| `tests/` | Core tests; `pytest -m optional` enables MCP demo / stress corpora tests |
| `scripts/*.sh`, `scripts/run_*.py` | **Minimal reproduction** entry points |
| `scripts/paper_optional/` | Optional helpers to regenerate tables or figures from summaries (matplotlib; not required for evaluation) |
| `data/` | Install location for the RAC-TraceBench v0.6 JSON bundle (`data/README.md`) |
| `artifacts/results/` | **Runtime outputs** (gitignored except `.gitkeep`) |
| `artifacts/expected/summaries/` | Small reference **JSON** snapshots |
| `artifacts/expected/data/` | Optional small auxiliary files (see `.gitignore` allowlist) |
| `artifacts/generated/` | Outputs from `scripts/paper_optional/` (gitignored) |
| `examples/` | MCP demos; normalized planner-style replay fixtures under `examples/llm_plans/`; `mcp_live_enforcement` supports offline checks |

## Environment

- Python **3.11+** (see `pyproject.toml`; older versions may warn in `check_env.sh`).
- `python3 -m pip install -r requirements.txt && python3 -m pip install -e .`
- **matplotlib**: only for `scripts/paper_optional/` (`pip install -e ".[dev]"`).

## Minimal reviewer path

```bash
bash scripts/check_env.sh
bash scripts/check_artifact.sh          # smoke + latency CLI tests
export RAC_TRACEBENCH_ROOT=/path/to/rac_tracebench_v06   # if not under data/ or sibling mcp_data/
bash scripts/run_all.sh                 # optional: --quick-latency, --with-mcp
```

Per-RQ commands are unchanged in spirit: `run_tracebench.sh`, `run_ablation.sh`, `run_latency.sh`, `run_tracebench_overhead.sh`, `run_mcp_case_study.sh` (see `docs/artifact_guide.md`).

## Outputs

- Fresh runs write under **`artifacts/results/`** (and `artifacts/results/performance/` for synthetic latency).
- **`artifacts/expected/summaries/`** holds reference JSON only; semantic metrics should match when the TraceBench bundle and code revision align. Latency ms values may float.

## Optional derived outputs

Not part of the minimal artifact path. See `scripts/paper_optional/README.md`. Inputs resolve from `artifacts/results/` first, then `artifacts/expected/`.

## License

See `LICENSE` (anonymous placeholder).
