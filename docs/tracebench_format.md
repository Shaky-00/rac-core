# TraceBench JSON format

TraceBench ships in **`rac-data`** under public suite names: **paired**, **core**, **expanded**, and **composite-overlay**.

## Unified bundle layout (`rac-data/tracebench/`)

Typical layout for core and expanded replay:

- `controlled_traces/core/*.json` — 44 core cases (`TB-CORE-*`, 17 ALLOW / 27 BLOCK)
- `controlled_traces/expanded/*.json` — expanded mutants (`TB-EXP-*`)
- `oracle_labels/core_oracle_labels.json`, `expanded_oracle_labels.json`
- `grants/`, `manifests/` — replay templates

Set `RAC_TRACEBENCH_ROOT` to the bundle root (or use `RAC_DATA_DIR` discovery). Run:

```bash
export RAC_DATA_DIR=../rac-data
python3 scripts/run_rac_tracebench_v1.py --suite core
python3 scripts/run_rac_tracebench_v1.py --suite expanded --include-mixed false
```

The loader normalizes case JSON in [`rac_tracebench_v1_adapter.py`](../src/rac_core/validation/rac_tracebench_v1_adapter.py) before `convert_trace_case_to_controlled_trace`. Core cases use `legacy_trace_id` as replay `trace_id` for regression parity with the paired suite.

## Paired suite layout (`rac-data/tracebench/paired/`)

- `controlled_traces/paired/*.json`
- `oracle_labels/paired_oracle_labels.json`

```bash
export RAC_DATA_DIR=../rac-data
export RAC_TRACEBENCH_ROOT=../rac-data/tracebench/paired   # optional explicit override
python3 scripts/run_tracebench.py
```

## Composite overlay

Multi-step composite-drift workflows: `rac-data/tracebench/composite-overlay/` (or legacy `rac-core/data/tracebench_rq2_composite_overlay/` until migrated). Enabled with `--rq2-overlay` on expanded replay scripts.

Installation: [`../data/README.md`](../data/README.md) and [`../../rac-data/README.md`](../../rac-data/README.md).
