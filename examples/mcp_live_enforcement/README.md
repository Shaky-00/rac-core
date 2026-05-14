# MCP-Native Live Enforcement Case Study (Stage M1)

This example implements a minimal but end-to-end MCP-native case study where RAC runs at the guarded MCP client boundary before each `tools/call`.

## What this demonstrates

- Four stub MCP servers are implemented with the official Python MCP SDK (`mcp`) over stdio transport.
- Tools are intentionally stubbed, but the MCP client/server call boundary is real.
- The guarded client maps pending MCP calls into canonical authorization events via a deterministic manifest-driven AEM.
- RAC checks run before invoking `session.call_tool(...)`.
- If RAC returns `BLOCK`, the client does not send the MCP call and records `issued_to_server=false`.

## Servers and tools

- `document_server`: `read_report`, `search_reports`
- `analysis_server`: `summarize_report`, `extract_metrics`, `compare_reports`
- `workspace_server`: `create_internal_report`, `save_internal_report`
- `communication_server`: `send_email`

`create_internal_report` and `save_internal_report` are modeled as **internal derived artifact handling** in this case study:

- consumes authorized `summary_id` / `metrics_id` / internal report artifact IDs
- produces or persists internal report artifacts
- `external_effect=false`
- no external disclosure and no new source-resource access

When mapped into the current RAC action lattice, AEM normalizes this semantic class to a derived/compute action (manifest-driven), not a write-like escalation action.

Each server writes a call log (`traces/server_call_logs/*.jsonl`) so blocked calls can be verified as not reaching the server.

## Why stub tools are acceptable here

The goal is not business logic realism; it is enforcement realism at MCP call boundaries. Tool handlers return structured mock payloads (`status`, `artifact_id`, `resources`, `output_type`) to support deterministic scenario replay and auditing.

## Install

From repo root:

```bash
.venv/bin/python -m pip install -r examples/mcp_live_enforcement/requirements-mcp.txt
```

If your environment already has `mcp` installed (for example from `examples/mcp_official_sdk`), this command is still safe.

## Run

```bash
.venv/bin/python examples/mcp_live_enforcement/client/scenario_runner.py --all
```

Outputs:

- `examples/mcp_live_enforcement/traces/mcp_guarded_trace.jsonl`
- `examples/mcp_live_enforcement/case_outputs/mcp_case_study_results.json`

## Evidence for pre-call enforcement

A blocked step must satisfy both:

1. Trace row has `issued_to_server=false`.
2. Corresponding server tool call is absent in `traces/server_call_logs/*.jsonl`.

## Current scope and next step

- Current scope: scripted scenarios only (deterministic pending calls).
- Extensions should route additional pending-call sources through the same guarded client + AEM surface without changing RAC core checker logic.

## Structured content note

This implementation returns JSON text payloads via MCP `TextContent`. If your installed MCP SDK/runtime supports richer `structuredContent` handling in your environment, you can swap response encoding without changing the enforcement flow.
