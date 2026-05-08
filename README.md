# rac-core

**Runtime Authorization Consistency (RAC)** — reference **v0.6 prototype** implementation for research and evaluation.

This repository tracks a **controller-side pre-commit checker** over typed authorization events, trusted manifests/grants, causal lineage, and optional structured output anchors. The normative Chinese spec is **`RAC_技术规格_v0.6.md`** (e.g. your ACSAC `tech_spec` tree); you may **copy** it into `docs/RAC_技术规格_v0.6.md` for a repo-local citation. Implementation-to-design mapping and **documented gaps** vs that spec live in [`docs/rac_v06_alignment.md`](docs/rac_v06_alignment.md).

Per v0.6, the bundled YAML action configuration is **Reference Action Semantics** (not a universal threat taxonomy). Evaluation traces under `validation/taxonomy_traces.py` are for **coverage organization**; the checker implements **NoMorePermissive**-style rules, not taxonomy-as-target detection.

## Core entry points

| Component | Role |
|-----------|------|
| [`RACPreCommitChecker`](src/rac_core/checker/precommit.py) | Main pre-call decision: lineage resolution, resource-origin checks, basis inheritance/tightening, consistency rules → `Decision` |
| [`EventAdapter`](src/rac_core/adapter/event_adapter.py) | Builds [`TypedAuthorizationEvent`](src/rac_core/models/event.py) from pending tool call + trusted manifests |
| Stores | [`InMemoryCausalLineageStore`](src/rac_core/store/lineage_store.py), [`InMemoryBasisStore`](src/rac_core/store/basis_store.py) |

## Decision policy (prototype scope)

- **`RACPreCommitChecker`** returns **`ALLOW`** or **`BLOCK`** only.
- [`DecisionType.ALLOW_WITH_ALERT`](src/rac_core/models/decision.py) exists as a **reserved** enum value for reporting compatibility; there is **no** alert policy engine in this prototype.

## Lineage / predecessors

- **Conservative single-predecessor model**: if input anchors resolve to **more than one distinct producer event**, the checker returns **`MULTI_PREDECESSOR_UNSUPPORTED`** (merge / join of multiple predecessors is **not** in scope).

## Evaluation assets (paper-oriented)

- Controlled traces and taxonomy scenarios (`src/rac_core/validation/`)
- Component ablation (`src/rac_core/validation/ablation.py`, `component_ablation_cases.py`)
- Latency / overhead microbenchmarks (`src/rac_core/evaluation/latency.py`, `validation/rac_tracebench_overhead.py`)
- MCP official SDK guarded demo (`examples/mcp_official_sdk/`) and related case studies

The older synthetic **external** trace benchmark path has been **retired**. This repository does **not** depend on the external trace repository previously referenced at `/root/projects/agent-auth-trace-bench`.

## Supplementary design notes

- [`docs/authorization_event_mapper.md`](docs/authorization_event_mapper.md) — Authorization Event Mapper (AEM) at the MCP client boundary
- [`docs/mcp_case_study_plan.md`](docs/mcp_case_study_plan.md) — MCP live enforcement case study plan

## Minimal reproduction

```bash
# from repository root; Python >= 3.11
python3 -m pip install -e ".[dev]"
python3 -m pytest tests -q
```

**Optional** RAC-TraceBench v0.6 JSON replay (skipped in CI if bundle absent): set `RAC_TRACEBENCH_ROOT` to the trace bundle root so `tests/test_rac_tracebench_v06_*.py` runs.

**Optional** real filesystem MCP integration tests: set `RAC_REAL_MCP_SERVER_CMD` (see `tests/test_mcp_real_filesystem_v06_guarded.py`).

Static TraceBench replay + CSV/JSON summaries:

```bash
python3 scripts/run_rac_tracebench_v06.py --help
```

Overhead microbenchmark:

```bash
python3 scripts/run_rac_tracebench_overhead.py --help
```

Committed experiment inputs under `results/` can be turned into figures/tables per [`artifacts/README_experiment_artifacts.md`](artifacts/README_experiment_artifacts.md).
