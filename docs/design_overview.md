# Design overview (anonymous artifact)

This repository implements **Runtime Authorization Consistency (RAC)** as a controller-side pre-commit checker over typed authorization events, trusted manifests and grants, causal lineage, and optional structured output anchors for MCP-shaped agentic workflows.

## Normative specification

This artifact does not ship the full external RAC technical specification text. The prototype follows the paper’s pre-commit pipeline: trusted event construction, anchor and resource-origin verification, controller-resolved lineage, authorization-basis propagation/tightening, and no-more-permissive consistency checking. Blocked steps are not persisted to lineage or basis stores (see `src/rac_core/checker/precommit.py`).

## Code map

| Area | Path |
|------|------|
| Pre-commit checker | `src/rac_core/checker/precommit.py` |
| Event adapter | `src/rac_core/adapter/event_adapter.py` |
| Output anchor / resource origin | `src/rac_core/verification/` |
| Lineage / basis stores | `src/rac_core/store/` |
| Controlled traces & TraceBench harness | `src/rac_core/validation/` |
| Latency microbenchmarks | `src/rac_core/evaluation/latency.py` |
| MCP filesystem case study (optional live) | `examples/mcp_real_filesystem_v06/` |

For runnable evaluation steps, expected summaries, and data-bundle requirements, see [`artifact_guide.md`](artifact_guide.md).
