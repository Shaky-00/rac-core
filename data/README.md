# Data directory

This repository **does not vendor** full TraceBench or planner corpora. Install datasets in the sibling **`rac-data`** repository and point **`RAC_DATA_DIR`** at it (default: `../rac-data`).

## TraceBench (paired suite)

Unpack the **paired** conformance bundle so the root contains:

- `controlled_traces/paired/*.json`
- `oracle_labels/paired_oracle_labels.json`
- `manifests/sample_tool_manifests_v06.yaml` (filename retained for replay compatibility)
- `grants/*.yaml`

**Preferred location:** `../rac-data/tracebench/paired/`

**Override:** `export RAC_TRACEBENCH_ROOT=/absolute/path/to/bundle/root` (highest priority).

**Expanded / core suites:** install under `../rac-data/tracebench/` with `controlled_traces/core/` and `controlled_traces/expanded/` (see `../rac-data/README.md`).

If data is absent, `scripts/check_env.sh` warns and TraceBench drivers exit with an error.

## Planner replay / MCP demos

- Normalized planner workflows: `../rac-data/planner-replay/normalized/`
- Filesystem demo fixtures: `examples/mcp_real_filesystem_v06/plans/` (see `docs/artifact_guide.md`)
