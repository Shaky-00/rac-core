# Design overview (anonymous artifact)

This repository implements **Runtime Authorization Consistency (RAC) v0.6** as a controller-side pre-commit checker over typed authorization events, trusted manifests and grants, causal lineage, and optional structured output anchors for MCP-shaped agentic workflows.

## Normative specification

This artifact does not ship the full external RAC v0.6 technical specification text. Implementation-to-spec mapping and documented gaps are summarized in [`docs/rac_v06_alignment.md`](rac_v06_alignment.md).

## Code map

| Area | Path |
|------|------|
| Checker | `src/rac_core/checker/precommit.py` |
| Event adapter | `src/rac_core/adapter/event_adapter.py` |
| Stores | `src/rac_core/store/` |
| Controlled traces & TraceBench harness | `src/rac_core/validation/` |
| Latency microbenchmarks | `src/rac_core/evaluation/latency.py` |
| MCP demos (optional) | `examples/` |

For runnable evaluation steps and troubleshooting, see [`artifact_guide.md`](artifact_guide.md).
