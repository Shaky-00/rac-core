# Data directory — external evaluation bundle interface

This repository **does not vendor** the full evaluation data bundle. The `data/` tree documents how replay scripts locate external inputs via environment variables.

## Blind review scope

During blind review, **`rac-core` alone** supports mechanism inspection, `check_artifact` smoke tests, RQ3 expected-summary verification, and latency quick checks. **TraceBench replay** (RQ1 paired smoke, RQ2 expanded replay, paper-scale overhead) requires a separate evaluation bundle on disk.

## Expected sibling layout

```text
parent/
├── rac-core/     # implementation, tests, scripts (this repository)
└── rac-data/     # evaluation bundle (not included in this repository)
```

Configure the bundle root:

```bash
export RAC_DATA_DIR=/path/to/rac-data
```

Optional single-bundle override:

```bash
export RAC_TRACEBENCH_ROOT=/path/to/tracebench/paired
```

If the bundle is absent, `scripts/check_env.sh` warns and TraceBench drivers exit with an explicit error.

## TraceBench (paired suite)

When the external bundle is available, install the **paired** conformance layout so the root contains:

- `controlled_traces/paired/*.json`
- `oracle_labels/paired_oracle_labels.json`
- `manifests/sample_tool_manifests_v06.yaml` (filename retained for replay compatibility)
- `grants/*.yaml`

**Preferred location:** `$RAC_DATA_DIR/tracebench/paired/`

**Expanded / core suites** (RQ2 and paper-scale overhead): under `$RAC_DATA_DIR/tracebench/` with `controlled_traces/core/`, `controlled_traces/expanded/`, and `composite-overlay/` as described in [`docs/tracebench_format.md`](../docs/tracebench_format.md).

## Planner replay / MCP demos

- Normalized planner workflows (when used beyond committed fixtures): `$RAC_DATA_DIR/planner-replay/normalized/`
- Filesystem case-study planner JSON shipped in-repo: `examples/mcp_real_filesystem_v06/plans/` (see [`docs/artifact_guide.md`](../docs/artifact_guide.md))
