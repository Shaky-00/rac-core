# RAC + real filesystem MCP (stdio)

Minimal run (after `pip install 'mcp>=1.0,<2.0'` and a Node/npx MCP filesystem server):

```bash
export RAC_REAL_MCP_SERVER_CMD=npx
export RAC_REAL_MCP_SERVER_ARGS='-y @modelcontextprotocol/server-filesystem'
python3 examples/mcp_real_filesystem_v06/run_real_filesystem_case.py
```

The script creates a temp sandbox, appends its path as the last server argv token, runs benign read / blocked read / blocked write, and writes `traces/mcp_real_filesystem_v06_trace.jsonl`.

Results (default `--output-dir` = `artifacts/results/`):

- `mcp_real_filesystem_v06_results.csv`
- `mcp_real_filesystem_v06_summary.json`

Sanity check (no live server): `bash scripts/run_mcp_case_study.sh`

Planner fixtures for this artifact are under `examples/mcp_real_filesystem_v06/plans/` in rac-core.
