# MCP live enforcement case study (outline)

This document sketches the **MCP-native live enforcement** path: RAC at the client/gateway boundary, operating on pending `tools/call` before server side effects. It aligns with the demo layout under `examples/` and the mapper notes in [`authorization_event_mapper.md`](authorization_event_mapper.md). Normative detail remains in the external RAC v0.6 specification; code locations are indexed in [`rac_v06_alignment.md`](rac_v06_alignment.md).

## Objective

- RAC runs at the MCP client or gateway edge.
- Each pending `tools/call` is checked **before** the server executes.
- Only `ALLOW` decisions lead to a real MCP server invocation.
- On `BLOCK`, the call is dropped and `issued_to_server=false` is recorded.

## Stub MCP servers

The case study relies on **in-repo stub MCP servers** with deterministic behavior so enforcement can be observed without depending on external synthetic trace bundles for the live path.

## Tool coverage

Illustrative tools:

- `read_report`, `search_reports`, `summarize_report`, `extract_metrics`
- `create_internal_report`, `save_internal_report`, `send_email`

They exercise read/search, summarization, structured extraction, internal write, and external disclosure paths.

## Guarded client flow

1. Application forms a pending MCP tool call.
2. The client captures the pending `tools/call` before `session.call_tool(...)`.
3. AEM maps the call plus manifest to a canonical authorization event.
4. RAC evaluates the event.
5. The client forwards or suppresses the MCP call based on the decision.

## Enforcement semantics

- `ALLOW` → invoke MCP server; record `issued_to_server=true` when auditing.
- `BLOCK` → do not invoke MCP server; record `issued_to_server=false`.

The evidentiary bar is empirical: on `BLOCK`, **no** server-side mutation attributable to that call should occur.

## Audit record

Each pending call should log MCP-native fields:

- Raw tool name, arguments, and session identifiers.
- Canonical authorization event from AEM.
- RAC decision and `issued_to_server`.
- If the server ran, bounded response metadata safe for logs.

## Representative scenarios

- Benign read of an authorized report.
- Resource drift: authorized read of A followed by attempted read of B.
- Benign derivation: `read_report` → `summarize_report`.
- Unauthorized disclosure: `summarize_report` → `send_email`.
- Internal writes that policy permits.
- Search constrained to an allowed corpus.
- Metric extraction followed by attempted disclosure.

## Evaluation mix

Together with controlled TraceBench runs, taxonomy-aligned drift traces, component ablations, and latency/overhead harnesses, this MCP path demonstrates **runtime** enforcement on a realistic tool surface without conflating live MCP checks with offline oracle replay.
