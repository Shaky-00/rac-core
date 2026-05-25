"""Golden replay tests for RAC-TraceBench v0.6 minimal paired bundle (mcp_data)."""

from __future__ import annotations

import pytest
import yaml

from rac_core.action_semantics.registry import ActionSemanticsRegistry
from rac_core.action_semantics.taxonomy import default_semantics_yaml_path
from rac_core.checker import RACPreCommitChecker
from rac_core.models import DecisionType, VerifiedStructuredOutputAnchor
from rac_core.store import InMemoryBasisStore, InMemoryCausalLineageStore
from rac_core.validation import TraceRunner
from rac_core.verification import verify_observed_access_matches_anchor
from rac_core.validation.rac_tracebench_loader import (
    _tracebench_manifest_action_defaults,
    adapt_tracebench_grant_yaml_root,
    build_tracebench_grant_templates_root,
    convert_trace_case_to_controlled_trace,
    load_oracle_labels,
    load_rac_tracebench,
    load_trace_cases,
    oracle_label_by_trace_id,
    resolve_rac_tracebench_root,
)


def _runner() -> TraceRunner:
    return TraceRunner(
        RACPreCommitChecker(
            lineage_store=InMemoryCausalLineageStore(),
            basis_store=InMemoryBasisStore(),
            action_semantics_registry=ActionSemanticsRegistry.load_from_yaml(
                default_semantics_yaml_path()
            ),
        )
    )


@pytest.fixture(scope="module")
def bench_root():
    root = resolve_rac_tracebench_root()
    if root is None:
        pytest.skip("TraceBench root not found (set RAC_TRACEBENCH_ROOT or install rac-data)")
    return root


@pytest.fixture(scope="module")
def bench_bundle(bench_root):
    return load_rac_tracebench(bench_root)


def test_load_forty_four_traces(bench_bundle) -> None:
    assert len(bench_bundle["traces"]) == 44


def test_load_oracle_labels(bench_bundle) -> None:
    labels = bench_bundle["oracle_labels"]
    assert "labels" in labels
    assert len(labels["labels"]) == 44


def test_oracle_covers_every_trace_id(bench_bundle) -> None:
    by_id = oracle_label_by_trace_id(bench_bundle["oracle_labels"])
    for t in bench_bundle["traces"]:
        tid = t["trace_id"]
        assert tid in by_id, f"missing oracle row for {tid}"


def test_benign_expected_allow(bench_bundle) -> None:
    by_id = oracle_label_by_trace_id(bench_bundle["oracle_labels"])
    row = by_id["TRC-V06-001"]
    assert row["expected_decision"] == "ALLOW"


def test_violation_expected_block(bench_bundle) -> None:
    by_id = oracle_label_by_trace_id(bench_bundle["oracle_labels"])
    n_allow = sum(1 for r in by_id.values() if r["expected_decision"] == "ALLOW")
    n_block = sum(1 for r in by_id.values() if r["expected_decision"] == "BLOCK")
    assert n_allow == 17 and n_block == 27


def test_convert_all_to_controlled_trace(bench_bundle) -> None:
    for case in bench_bundle["traces"]:
        ct = convert_trace_case_to_controlled_trace(case)
        assert ct.name == case["trace_id"]
        assert len(ct.steps) == len(case["steps"])
        assert ct.grant_templates == case["grant_templates"]
        assert ct.initial_basis is not None
        for tid in case["grant_templates"]:
            assert tid in ct.initial_basis.source_templates


def test_tracebench_grant_yaml_adapts_for_expander(bench_root) -> None:
    root_doc = build_tracebench_grant_templates_root(bench_root)
    assert "templates" in root_doc
    t = root_doc["templates"]["internal_analysis_file_a_scope_v06"]
    assert t["actions"] == ["acquire.read_object", "transform.summarize"]
    assert "internal_analysis" in t["purpose_constraints"]
    agg = root_doc["templates"]["internal_analysis_file_a_aggregate_v06"]
    assert agg["actions"] == [
        "acquire.read_object",
        "transform.summarize",
        "transform.aggregate_compare",
    ]
    merge = root_doc["templates"]["internal_analysis_file_a_merge_v06"]
    assert merge["actions"] == [
        "acquire.read_object",
        "transform.summarize",
        "transform.merge",
    ]


def test_adapt_tracebench_roundtrip_preserves_templates_shape(bench_root) -> None:
    raw = yaml.safe_load(
        (bench_root / "grants" / "sample_grant_templates_v06.yaml").read_text(encoding="utf-8")
    )
    doc = adapt_tracebench_grant_yaml_root(raw)
    assert doc == adapt_tracebench_grant_yaml_root(doc)


def _final_replay_decision(result) -> DecisionType:
    assert result.step_results
    return result.step_results[-1].decision.decision


def test_replay_matches_oracle_expected_decision(bench_bundle) -> None:
    """All traces: final step decision matches oracle expected_decision."""
    by_oracle = oracle_label_by_trace_id(bench_bundle["oracle_labels"])
    runner = _runner()
    for case in bench_bundle["traces"]:
        tid = case["trace_id"]
        oracle = by_oracle[tid]["expected_decision"]
        want = DecisionType.ALLOW if oracle == "ALLOW" else DecisionType.BLOCK
        ct = convert_trace_case_to_controlled_trace(case)
        result = runner.run(ct)
        got = _final_replay_decision(result)
        assert got == want, f"{tid}: oracle {oracle} replay {got}"


def test_trc_v06_008_output_anchor_integrity_block(bench_bundle) -> None:
    case = next(c for c in bench_bundle["traces"] if c["trace_id"] == "TRC-V06-008")
    result = _runner().run(convert_trace_case_to_controlled_trace(case))
    s02 = next(sr for sr in result.step_results if sr.name == "S02")
    assert s02.decision.decision == DecisionType.BLOCK
    assert "OUTPUT_ANCHOR_MISMATCH" in s02.observed_rules
    v0 = s02.decision.violations[0]
    assert v0.metadata.get("OutputAnchorIntegrity") is True


def test_benign_trace_no_output_anchor_mismatch_rule(bench_bundle) -> None:
    case = next(c for c in bench_bundle["traces"] if c["trace_id"] == "TRC-V06-001")
    result = _runner().run(convert_trace_case_to_controlled_trace(case))
    for sr in result.step_results:
        assert "OUTPUT_ANCHOR_MISMATCH" not in sr.observed_rules


def test_verify_observed_access_matches_anchor_ok_without_observed() -> None:
    a = VerifiedStructuredOutputAnchor(
        anchor_id="a1",
        producer_event_id="e1",
        content_hash="h1",
        resource_ids={"file_A"},
        verified_by_controller=True,
        session_id="s1",
    )
    ok, reason = verify_observed_access_matches_anchor(a)
    assert ok and reason is None


def test_verify_observed_access_detects_extra_resource() -> None:
    a = VerifiedStructuredOutputAnchor(
        anchor_id="a1",
        producer_event_id="e1",
        content_hash="sha256:CLAIMED",
        resource_ids={"file_A"},
        verified_by_controller=True,
        session_id="s1",
        metadata={
            "observed_access": {
                "bytes_read_from_resources": ["file_B"],
                "observed_summary_sha256": "sha256:CLAIMED",
            }
        },
    )
    ok, reason = verify_observed_access_matches_anchor(a)
    assert ok is False
    assert reason is not None and "file_B" in reason


def test_trc_v06_002_action_escalation_rule(bench_bundle) -> None:
    case = next(c for c in bench_bundle["traces"] if c["trace_id"] == "TRC-V06-002")
    result = _runner().run(convert_trace_case_to_controlled_trace(case))
    blocked = next(sr for sr in result.step_results if sr.name == "S03")
    rules = " ".join(blocked.observed_rules)
    assert blocked.decision.decision == DecisionType.BLOCK
    assert "ACTION_ESCALATION" in rules


def test_trc_v06_004_resource_origin_blocks_file_b(bench_bundle) -> None:
    case = next(c for c in bench_bundle["traces"] if c["trace_id"] == "TRC-V06-004")
    result = _runner().run(convert_trace_case_to_controlled_trace(case))
    blocked = next(sr for sr in result.step_results if sr.name == "S03")
    assert blocked.decision.decision == DecisionType.BLOCK
    assert "RESOURCE_ORIGIN_UNVERIFIABLE" in blocked.observed_rules
    v0 = blocked.decision.violations[0]
    meta = v0.metadata or {}
    failed = meta.get("failed_resource_ids")
    assert failed is not None and "file_B" in failed


def test_trc_v06_010_multi_predecessor_unsupported(bench_bundle) -> None:
    case = next(c for c in bench_bundle["traces"] if c["trace_id"] == "TRC-V06-010")
    result = _runner().run(convert_trace_case_to_controlled_trace(case))
    blocked = next(sr for sr in result.step_results if sr.name == "S03")
    assert blocked.decision.decision == DecisionType.BLOCK
    assert "MULTI_PREDECESSOR_UNSUPPORTED" in blocked.observed_rules


def test_loader_preserves_observed_access_metadata(bench_bundle) -> None:
    case = next(c for c in bench_bundle["traces"] if c["trace_id"] == "TRC-V06-008")
    ct = convert_trace_case_to_controlled_trace(case)
    step2 = next(s for s in ct.steps if s.name == "S02")
    assert step2.output_anchor is not None
    assert "observed_access" in step2.output_anchor.metadata


def test_load_trace_cases_directory(bench_root) -> None:
    traces = load_trace_cases(bench_root / "controlled_traces" / "paired")
    assert len(traces) == 44


def test_load_oracle_labels_path(bench_root) -> None:
    doc = load_oracle_labels(bench_root / "oracle_labels" / "paired_oracle_labels.json")
    assert len(doc["labels"]) == 44


def test_trc_v06_011_delegation_only_blocks_full_rac(bench_bundle) -> None:
    case = next(c for c in bench_bundle["traces"] if c["trace_id"] == "TRC-V06-011")
    result = _runner().run(convert_trace_case_to_controlled_trace(case))
    s02 = next(sr for sr in result.step_results if sr.name == "S02")
    assert s02.decision.decision == DecisionType.BLOCK
    assert "DELEGATION_AMPLIFICATION" in s02.observed_rules


def test_trc_v06_012_lineage_producer_mismatch_blocks(bench_bundle) -> None:
    case = next(c for c in bench_bundle["traces"] if c["trace_id"] == "TRC-V06-012")
    result = _runner().run(convert_trace_case_to_controlled_trace(case))
    s02 = next(sr for sr in result.step_results if sr.name == "S02")
    assert s02.decision.decision == DecisionType.BLOCK
    assert "LINEAGE_INVALID" in s02.observed_rules


def test_trc_v06_013_multi_predecessor_aggregate_blocks(bench_bundle) -> None:
    case = next(c for c in bench_bundle["traces"] if c["trace_id"] == "TRC-V06-013")
    result = _runner().run(convert_trace_case_to_controlled_trace(case))
    s03 = next(sr for sr in result.step_results if sr.name == "S03")
    assert s03.decision.decision == DecisionType.BLOCK
    assert "MULTI_PREDECESSOR_UNSUPPORTED" in s03.observed_rules


def test_trc_v06_017_finalize_metadata_benign_allow(bench_bundle) -> None:
    case = next(c for c in bench_bundle["traces"] if c["trace_id"] == "TRC-V06-017")
    ct = convert_trace_case_to_controlled_trace(case)
    s02 = next(s for s in ct.steps if s.name == "S02")
    assert s02.output_anchor is not None
    assert s02.output_anchor.metadata.get("finalize_internal_review") is True
    result = _runner().run(ct)
    assert _final_replay_decision(result) == DecisionType.ALLOW


def test_trc_v06_028_missing_producer_event_id_blocks(bench_bundle) -> None:
    case = next(c for c in bench_bundle["traces"] if c["trace_id"] == "TRC-V06-028")
    result = _runner().run(convert_trace_case_to_controlled_trace(case))
    s02 = next(sr for sr in result.step_results if sr.name == "S02")
    assert s02.decision.decision == DecisionType.BLOCK
    assert "LINEAGE_INVALID" in s02.observed_rules


def test_trc_v06_029_orphan_anchor_blocks(bench_bundle) -> None:
    case = next(c for c in bench_bundle["traces"] if c["trace_id"] == "TRC-V06-029")
    result = _runner().run(convert_trace_case_to_controlled_trace(case))
    s02 = next(sr for sr in result.step_results if sr.name == "S02")
    assert s02.decision.decision == DecisionType.BLOCK
    assert "LINEAGE_INVALID" in s02.observed_rules


def test_tracebench_manifest_yaml_maps_tools_to_actions(bench_root) -> None:
    m = _tracebench_manifest_action_defaults(bench_root)
    assert m["post_status_webhook"] == ["disclose.publish_status"]
    assert m["publish_release_discussion"] == ["disclose.publish_artifact"]
    assert m["aggregate_cross_section"] == ["transform.aggregate_compare"]
