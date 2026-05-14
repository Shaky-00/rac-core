# Data directory (TraceBench and replays)

## RAC-TraceBench v0.6 (controlled JSON bundle)

Static TraceBench experiments expect a directory layout ending with:

- `controlled_traces/paired/*.json`
- `oracle_labels/paired_oracle_labels.json`
- `manifests/sample_tool_manifests_v06.yaml`
- `grants/*.yaml` (as shipped with the bundle)

**Install location (pick one):**

1. `data/tracebench/rac_tracebench_v06/` under this repository root (recommended for artifact layout), or  
2. `mcp_data/rac_tracebench_v06/` next to the repository (sibling directory layout), or  
3. Any path exported as `RAC_TRACEBENCH_ROOT` (highest precedence).

The TraceBench JSON bundle is **not** vendored in this repository; install it using the instructions bundled with the evaluation materials for this artifact. If the bundle is absent, TraceBench scripts exit with an error after `scripts/check_env.sh` warns.

## Planner replay / MCP case study

Optional deterministic planner fixtures for filesystem MCP demos live under `examples/mcp_real_filesystem_v06/plans/` (see `docs/artifact_guide.md`).
