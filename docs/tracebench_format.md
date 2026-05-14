# TraceBench JSON format (RAC-TraceBench v0.6)

This artifact uses the **RAC-TraceBench v0.6** bundle: JSON trace cases under `controlled_traces/paired/`, paired oracle labels, grant templates, and tool manifest defaults. The loader normalizes grants and attaches manifest-derived default required actions in [`rac_tracebench_loader.py`](../src/rac_core/validation/rac_tracebench_loader.py).

## On-disk layout (bundle root)

- `controlled_traces/paired/*.json` — one object per trace case (`trace_id`, `trace_family`, `steps`, …).  
- `oracle_labels/paired_oracle_labels.json` — `labels` map keyed by `trace_id` with `expected_decision` and `expected_violation_types`.  
- `manifests/sample_tool_manifests_v06.yaml` — tool → default required actions for TraceBench replay.  
- `grants/*.yaml` — grant templates consumed when constructing per-trace initial basis.

## Runtime mapping

Each JSON step is converted to a `ControlledTrace` / `TraceStep` via `convert_trace_case_to_controlled_trace`. Metadata under `rac_tracebench` records trace family, pair id, and step ids for reporting.

For installation paths and missing-data behavior, see [`../data/README.md`](../data/README.md).
