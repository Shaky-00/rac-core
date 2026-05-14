# Authorization Event Mapper (AEM)

This document describes the **pre-call mapping layer** at the MCP client or gateway boundary: how a pending `tools/call` becomes a **canonical authorization event** consumed by the RAC checker. It supplements the code map in [`design_overview.md`](design_overview.md) and the implementation index in [`rac_v06_alignment.md`](rac_v06_alignment.md); it is **not** a substitute for the external RAC v0.6 technical specification.

## Role

The Authorization Event Mapper (AEM) sits **before** `session.call_tool(...)` reaches an MCP server. Given `tool_name`, `arguments`, session context, and a **trusted** tool manifest entry, it constructs a normalized authorization event for `RACPreCommitChecker`.

AEM targets **live MCP calls**, not offline synthetic trace replay. TraceBench exercises the checker through its own adapters; AEM is the bridge for MCP-shaped runtimes.

## Why it exists

- MCP exposes concrete tool names and JSON arguments, not a uniform authorization vocabulary.
- Different servers use different parameter names and tool granularity; the checker still needs a stable canonical event.
- Enforcement must occur **before** side effects: otherwise a `BLOCK` decision cannot prevent server mutations.

## Control flow

1. A guarded MCP client holds a pending `tools/call`.
2. AEM reads `tool_name`, `arguments`, session context, and the trusted manifest row.
3. AEM emits a canonical `TypedAuthorizationEvent` (and related basis context as required by the adapter).
4. RAC runs pre-commit checks on that event.
5. On `ALLOW`, the client forwards the call to the MCP server.
6. On `BLOCK`, the client does **not** send `tools/call`, and records `issued_to_server=false`.

## Inputs

- Pending MCP `tools/call` (`tool_name`, `arguments`).
- Trusted manifest row, minimally including `canonical_action` and `resource_args`; optionally `artifact_args`, `recipient_args`, anchor flags, `external_effect`, `output_anchor_type`, `action_relation_class`.
- Session grant / basis / lineage state and any verified anchors the controller trusts.

## Outputs

- Normalized action and resource / artifact / recipient references.
- Purpose, delegation, and runtime conditions as required by the checker.
- `input_anchors` and expected output-anchor metadata.
- `mapping_warnings` for non-fatal normalization issues.

These fields are **checker-facing**, not benchmark-schema-specific.

## Mapping rules (summary)

- Every field listed under `resource_args` should be extracted; do not silently drop secondary resource keys.
- `artifact_args` reference predecessor artifacts; `recipient_args` capture disclosure targets.
- When `consumes_anchor=true`, inputs must resolve to a verified anchor the controller accepts.
- When `produces_anchor=true`, outputs must declare trackable artifact types for lineage.
- When `external_effect=true`, canonical events must retain side-effect and recipient detail for policy checks.

## Trust boundary

- Unstructured tool summaries, planner free text, or other narrative channel content are **not** authorization evidence.
- AEM must not treat synthetic benchmark rationales or offline human annotations as runtime grants.
- Evidence should come from session state, grants/basis, trusted manifests, controller-observed arguments, verified anchors, lineage, and resource registries.

## Relationship to RAC

- AEM: pending MCP call → canonical authorization event.
- RAC: no-more-permissive consistency on that event.
- Guarded client: enforces the decision at the wire.

Outcome mapping:

- `ALLOW` → MCP server call proceeds (`issued_to_server=true` when applicable).
- `BLOCK` → no MCP server call; `issued_to_server=false`.

## Example tool surface

Representative MCP tools used in demos include `read_report`, `search_reports`, `summarize_report`, `extract_metrics`, `create_internal_report`, `save_internal_report`, and `send_email`. Variation across tools should be captured in the manifest mapping, not with tool-name special cases inside the checker core.
