# RAC v0.6 — implementation vs specification (index)

This repository is a **prototype implementation** of Runtime Authorization Consistency (RAC) v0.6. The full normative *RAC Technical Specification v0.6* is **not** vendored here. This file is an **implementation index**: where major mechanisms live in code, and which specification-sized items are intentionally incomplete in this artifact.

## End-to-end pipeline (spec §3 style)

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
| Explicit action coverage | `action_semantics/coverage.py`, `checker/precommit.py` (`_check_action_coverage_v06`) | `tests/test_precommit_action_coverage_v06.py`, `tests/test_action_coverage_checker.py` |

## Reference action semantics vs taxonomy

The specification positions the action taxonomy as **reference action semantics** (coverage organization), **not** as a classifier target for the checker. This codebase mirrors that split: `ActionSemanticsRegistry` supplies **leaf labels + partial order** from YAML; taxonomy-shaped traces are used for **controlled evaluation coverage**. `RACPreCommitChecker` enforces **no-more-permissive** consistency (actions, resources, purpose, delegation, conditions, anchors, lineage), not taxonomy category classification.

## Feature matrix (selected items)

| Design item | Implementation | Tests | Notes |
|-------------|----------------|-------|-------|
| `TypedAuthorizationEvent` | `models/event.py` | `tests/test_core_objects.py`, `tests/test_event_adapter.py`, `tests/test_event_required_actions_bridge.py` | Includes `required_actions`, `input_anchors`, etc. |
| Event-level `effect` field | Not a first-class event field | — | `EffectProfile` exists on manifests; **no** standalone `EffectBoundaryPreservation` path on events (see gaps). |
| `GrantEnvelope` | `models/grant.py` | core + controlled-trace tests | |
| `ToolManifest` / `authorization_profile` | `models/manifest.py`, `adapter/profile_validator.py` | `tests/test_manifest_*.py` | Coarse `operation` / `resource_arg` coexist with richer profiles. |
| `VerifiedStructuredOutputAnchor` | `models/anchor.py` | `tests/test_output_anchor_verification.py`, … | `verified_by_controller`; store constraints. |
| Controller-side output verification | `store/lineage_store.py`, `verification/output_anchor.py` | `tests/test_lineage_store.py`, … | `output_anchor_integrity_precheck` on replay paths. |
| Resource origin verification | `verification/resource_origin.py`, `precommit.py` | `tests/test_resource_origin_verification.py` | e.g. `RESOURCE_ORIGIN_UNVERIFIABLE`. |
| `AuthorizationBasis` | `models/basis.py` | `tests/test_basis_store.py`, `tests/test_basis_profile_bridge.py` | |
| Basis propagation / tightening | `checker/basis_tightening.py`, `precommit.py` | `tests/test_basis_tightening.py` | |
| Action partial order | `action_semantics/partial_order.py`, `registry.py`, `checker/action_lattice.py` | `tests/test_action_semantics_registry.py` | Unlisted pairs are incomparable (conservative). |
| NoMorePermissive: action coverage | `precommit.py` `_check_action_coverage_v06` | `tests/test_precommit_action_coverage_v06.py` | Leaf `required_actions` only. |
| NoMorePermissive: resource / purpose / delegation / condition | `precommit.py` `_check_consistency`, `checker/conditions.py` | `tests/test_precommit_checker.py`, `tests/test_condition_tightening.py` | e.g. `RESOURCE_EXPANSION`, `PURPOSE_DRIFT`. |
| `ProvenanceSupport` / `origin_anchors` | `models/basis.py` fields | — | **Gap:** no dedicated `precommit` rule tying inputs to `basis.origin_anchors`. |
| Lineage / advisory hints | `lineage_store.resolve_predecessor` | `tests/test_lineage_store.py` | Hints do not create causality; runtime lineage wins (`warnings`). |
| Single predecessor; multi → `BLOCK` | `lineage_store.py` | `tests/test_lineage_store.py`, `tests/test_precommit_checker.py`, TraceBench | `MULTI_PREDECESSOR_UNSUPPORTED`; no `ConservativeMerge`. |
| Decisions `ALLOW` / `BLOCK` / `ALLOW_WITH_ALERT` | `models/decision.py`, `precommit.py` | — | Checker returns **ALLOW/BLOCK only**; `ALLOW_WITH_ALERT` exists on the enum without alert policy. |
| Controlled traces / evaluation | `validation/trace.py`, `rac_tracebench_*.py`, `taxonomy_traces.py` | `tests/test_controlled_trace_validation.py`, `tests/test_rac_tracebench_v06_*.py`, … | Paired traces + oracle labels live in the external TraceBench bundle. |

## Documented gaps (prototype scope)

Items called out in the specification (or in no-more-permissive formulas) that are **not fully implemented** in this artifact:

1. **Event-level `effect` + `EffectBoundaryPreservation`** — no standalone `event.effect` field; no `EFFECT_BOUNDARY_VIOLATION` decision path.
2. **`ProvenanceSupport` / `origin_anchors`** — fields exist on `AuthorizationBasis`; no separate enforcement rule in `precommit`.
3. **`ALLOW_WITH_ALERT`** — enumerated but not implemented as a distinct runtime outcome with policy.

## Related documentation

- [`authorization_event_mapper.md`](authorization_event_mapper.md) — MCP-side mapping into canonical authorization events.
- [`mcp_case_study_plan.md`](mcp_case_study_plan.md) — MCP live-enforcement case study outline.
