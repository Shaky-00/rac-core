# Official MCP Python SDK Case Study

This case study integrates RAC at the MCP client-side pre-call boundary using the official MCP Python SDK over stdio transport.

## What this demonstrates

- RAC checks are executed before each MCP `tools/call`.
- MCP protocol is unchanged.
- MCP server tool logic is unchanged and remains security-agnostic.
- When RAC returns `BLOCK`, the client does not call MCP `tools/call`.
- This is a deterministic local case study only (no live LLM planner, no production trace).

## Files

- `mcp_demo_server.py`: minimal official MCP SDK server with 4 tools.
- `rac_mcp_adapter.py`: maps MCP tool-call intents into RAC events.
- `guarded_mcp_client.py`: pre-call guard that invokes RAC before MCP SDK calls.
- `run_mcp_sdk_case_study.py`: runs deterministic allow/block scenarios and writes artifacts.

## Run

```bash
python examples/mcp_official_sdk/run_mcp_sdk_case_study.py
```

## Artifacts

- `artifacts/tables/mcp_sdk_case_study.csv`
- `artifacts/tables/mcp_sdk_case_study.json`
- `artifacts/tables/mcp_sdk_case_study.md`
- `artifacts/tables/mcp_sdk_case_study.tex`
