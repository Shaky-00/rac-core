# RAC mechanism — implementation mapping

This repository is a **prototype implementation** of Runtime Authorization Consistency (RAC). The full normative RAC technical specification is **not** vendored here. This file indexes where major mechanisms live in code and which specification-sized items are intentionally incomplete in this artifact.

## End-to-end pipeline

`Trusted Event Construction → Output Anchor Verification → Resource Origin Verification → Runtime-resolved Causal Lineage → Authorization Basis Propagation → Pre-commit Consistency Checking`

| Stage | Primary code locations |
|-------|------------------------|
| Trusted event construction | `src/rac_core/adapter/event_adapter.py` (`EventAdapter.construct_event`), `adapter/profile_validator.py` |
| Output anchor verification | `verification/output_anchor.py`, `store/lineage_store.py`, `checker/precommit.py` (`require_verified_output_anchor`) |
| Resource origin verification | `verification/resource_origin.py`, `checker/precommit.py` |
| Runtime causal lineage | `store/lineage_store.py` (`resolve_predecessor`, `append_step`), `models/lineage.py` |
| Basis propagation | `store/basis_store.py`, `models/basis.py`, `checker/basis_tightening.py`, `checker/precommit.py` |
| Pre-commit consistency | `checker/precommit.py` (`RACPreCommitChecker.check`) |

## Authorization semantics compilation path

`Grant Template Expansion → Compiled Grant → Tool Manifest Authorization Profile → Leaf Action Label Normalization → Explicit Action Coverage Check`

| Step | Code | Tests (representative) |
|------|------|-------------------------|
| Grant template / profile expansion | `action_semantics/grant_template.py`, `configs/default_grant_templates.yaml` | `tests/test_grant_profile_expander.py`, `tests/test_basis_profile_bridge.py` |
| Manifest `authorization_profile` | `models/manifest.py`, `adapter/profile_validator.py` | `tests/test_manifest_authorization_profile.py`, `tests/test_manifest_profile_validator.py` |
| Leaf labels + partial order | `action_semantics/registry.py`, `partial_order.py`, `configs/default_action_semantics.yaml` | `tests/test_action_semantics_registry.py` |
| Explicit action coverage | `action_semantics/coverage.py`, `checker/precommit.py` | `tests/test_precommit_action_coverage_v06.py`, `tests/test_action_coverage_checker.py` |

## Reference action semantics vs taxonomy

The specification positions the action taxonomy as **reference action semantics** (coverage organization), **not** as a classifier target for the checker. `RACPreCommitChecker` enforces **no-more-permissive** consistency (actions, resources, purpose, delegation, conditions, anchors, lineage), not taxonomy category classification.

## Feature matrix (selected items)

| Design item | Implementation | Tests | Notes |
|-------------|----------------|-------|-------|
| `TypedAuthorizationEvent` | `models/event.py` | `tests/test_core_objects.py`, `tests/test_event_adapter.py` | |
| `GrantEnvelope` | `models/grant.py` | core + controlled-trace tests | |
| `ToolManifest` / `authorization_profile` | `models/manifest.py`, `adapter/profile_validator.py` | `tests/test_manifest_*.py` | |
| `VerifiedStructuredOutputAnchor` | `models/anchor.py` | `tests/test_output_anchor_verification.py` | |
| Resource origin verification | `verification/resource_origin.py`, `precommit.py` | `tests/test_resource_origin_verification.py` | |
| `AuthorizationBasis` | `models/basis.py` | `tests/test_basis_store.py` | |
| Basis propagation / tightening | `checker/basis_tightening.py` | `tests/test_basis_tightening.py` | |
| Controlled traces / evaluation | `validation/trace.py`, `rac_tracebench_*.py` | `tests/test_controlled_trace_validation.py`, `tests/test_rac_tracebench_v06_*.py` | Traces live in external `rac-data`. |

## Documented gaps (prototype scope)

1. **Event-level `effect` + `EffectBoundaryPreservation`** — no standalone `event.effect` field; no `EFFECT_BOUNDARY_VIOLATION` decision path.
2. **`ProvenanceSupport` / `origin_anchors`** — fields exist on `AuthorizationBasis`; no separate enforcement rule in `precommit`.
3. **`ALLOW_WITH_ALERT`** — enumerated but not implemented as a distinct runtime outcome with policy.

## Related documentation

- [`authorization_event_mapper.md`](authorization_event_mapper.md) — MCP-side mapping into canonical authorization events.
- [`mcp_case_study_plan.md`](mcp_case_study_plan.md) — Real MCP filesystem enforcement outline (RQ3).
