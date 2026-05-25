# TraceBench JSON format

TraceBench JSON corpora are **not vendored in `rac-core`**. When an external evaluation bundle is available, layouts use suite names: **paired**, **core**, **expanded**, and **composite-overlay** under `$RAC_DATA_DIR/tracebench/`.

See [`../data/README.md`](../data/README.md) for `RAC_DATA_DIR` configuration.

## Unified bundle layout (`$RAC_DATA_DIR/tracebench/`)

Typical layout for core and expanded replay:

- `controlled_traces/core/*.json` — 44 core cases (`TB-CORE-*`, 17 ALLOW / 27 BLOCK)
- `controlled_traces/expanded/*.json` — expanded mutants (`TB-EXP-*`)
- `oracle_labels/core_oracle_labels.json`, `expanded_oracle_labels.json`
- `grants/`, `manifests/` — replay templates

Set `RAC_TRACEBENCH_ROOT` to the bundle root (or use `RAC_DATA_DIR` discovery). Example (requires external bundle):

```bash
export RAC_DATA_DIR=/path/to/rac-data
python3 scripts/run_rac_tracebench_v1.py --suite core
python3 scripts/run_rac_tracebench_v1.py --suite expanded --include-mixed false
```

The loader normalizes case JSON in [`rac_tracebench_v1_adapter.py`](../src/rac_core/validation/rac_tracebench_v1_adapter.py) before `convert_trace_case_to_controlled_trace`. Core cases use `legacy_trace_id` as replay `trace_id` for regression parity with the paired suite.

## Paired suite layout (`$RAC_DATA_DIR/tracebench/paired/`)

- `controlled_traces/paired/*.json`
- `oracle_labels/paired_oracle_labels.json`

```bash
export RAC_DATA_DIR=/path/to/rac-data
export RAC_TRACEBENCH_ROOT=$RAC_DATA_DIR/tracebench/paired   # optional explicit override
python3 scripts/run_tracebench.py
```

## Composite overlay

Multi-step composite-drift workflows: `$RAC_DATA_DIR/tracebench/composite-overlay/`. Enabled with `--rq2-overlay` on expanded replay (`scripts/run_rq2_tracebench.sh`).
