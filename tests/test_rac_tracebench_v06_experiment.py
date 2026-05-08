"""Tests for RAC-TraceBench v0.6 static ablation experiment harness."""

from __future__ import annotations

import json

import pytest

from rac_core.validation.ablation import AblationMode
from rac_core.validation.rac_tracebench_experiment import (
    CSV_FIELDNAMES,
    build_experiment_rows,
    resolve_tracebench_root,
    run_and_write,
    run_trace_variant,
)
from rac_core.validation.rac_tracebench_loader import convert_trace_case_to_controlled_trace, load_rac_tracebench


def test_rac_without_delegation_allows_011_isolation(bench_root) -> None:
    bundle = load_rac_tracebench(bench_root)
    case = next(c for c in bundle["traces"] if c["trace_id"] == "TRC-V06-011")
    trace = convert_trace_case_to_controlled_trace(case)
    d_full, *_ = run_trace_variant(trace, variant="FULL_RAC", mode=AblationMode.FULL_RAC)
    d_wo, _b, rules, _reason, _ = run_trace_variant(
        trace, variant="RAC_WITHOUT_DELEGATION", mode=AblationMode.RAC_WITHOUT_DELEGATION
    )
    assert d_full.value == "BLOCK"
    assert d_wo.value == "ALLOW"
    assert "DELEGATION_AMPLIFICATION" not in rules


def test_rac_without_lineage_differs_from_full_on_012(bench_root) -> None:
    bundle = load_rac_tracebench(bench_root)
    case = next(c for c in bundle["traces"] if c["trace_id"] == "TRC-V06-012")
    trace = convert_trace_case_to_controlled_trace(case)
    d_full, *_ = run_trace_variant(trace, variant="FULL_RAC", mode=AblationMode.FULL_RAC)
    d_wo, _b, rules, _reason, _ = run_trace_variant(
        trace, variant="RAC_WITHOUT_LINEAGE", mode=AblationMode.RAC_WITHOUT_LINEAGE
    )
    assert d_full.value == "BLOCK"
    assert d_wo.value == "ALLOW"
    assert "LINEAGE_INVALID" not in rules


def test_trc_v06_013_full_rac_blocks_multi_not_action(bench_root) -> None:
    bundle = load_rac_tracebench(bench_root)
    case = next(c for c in bundle["traces"] if c["trace_id"] == "TRC-V06-013")
    trace = convert_trace_case_to_controlled_trace(case)
    _d, blocked, rules, _reason, _ = run_trace_variant(
        trace, variant="FULL_RAC", mode=AblationMode.FULL_RAC
    )
    assert blocked == "S03"
    assert "MULTI_PREDECESSOR_UNSUPPORTED" in rules
    assert "ACTION_ESCALATION" not in rules


@pytest.fixture(scope="module")
def bench_root():
    root = resolve_tracebench_root()
    if root is None:
        pytest.skip("RAC-TraceBench v0.6 root not found")
    return root


def test_experiment_writes_csv_and_json(bench_root, tmp_path) -> None:
    csv_p, json_p = run_and_write(root=bench_root, output_dir=tmp_path)
    assert csv_p.is_file() and json_p.is_file()
    text = csv_p.read_text(encoding="utf-8")
    header = text.splitlines()[0]
    for col in CSV_FIELDNAMES:
        assert col in header
    summary = json.loads(json_p.read_text(encoding="utf-8"))
    assert "match_rate_by_variant" in summary
    assert "supported_variants" in summary
    assert "STATIC_TOOL_ALLOWLIST" in summary["supported_variants"]
    assert summary["total_traces"] == 32
    assert "FULL_RAC" in summary["variants"]
    assert summary.get("unsupported_variants") == []


def test_full_rac_matches_oracle_all_traces(bench_root) -> None:
    rows, _summary = build_experiment_rows(root=bench_root)
    full = [r for r in rows if r["variant"] == "FULL_RAC"]
    assert len(full) == 32
    assert all(r["matched_oracle"] == "true" for r in full)


def test_csv_row_count(bench_root) -> None:
    rows, _ = build_experiment_rows(root=bench_root)
    assert len(rows) == 32 * 11


def test_rac_without_output_anchor_differs_from_full_on_008(bench_root) -> None:
    bundle = load_rac_tracebench(bench_root)
    case = next(c for c in bundle["traces"] if c["trace_id"] == "TRC-V06-008")
    trace = convert_trace_case_to_controlled_trace(case)
    d_full, *_ = run_trace_variant(trace, variant="FULL_RAC", mode=AblationMode.FULL_RAC)
    d_wo, *_ = run_trace_variant(
        trace, variant="RAC_WITHOUT_OUTPUT_ANCHOR", mode=AblationMode.RAC_WITHOUT_ANCHOR
    )
    assert d_full.value == "BLOCK"
    assert d_wo.value == "ALLOW"


def test_rac_without_action_differs_from_full_on_action_escalation(bench_root) -> None:
    bundle = load_rac_tracebench(bench_root)
    case = next(c for c in bundle["traces"] if c["trace_id"] == "TRC-V06-002")
    trace = convert_trace_case_to_controlled_trace(case)
    d_full, *_ = run_trace_variant(trace, variant="FULL_RAC", mode=AblationMode.FULL_RAC)
    d_wo, *_ = run_trace_variant(
        trace, variant="RAC_WITHOUT_ACTION", mode=AblationMode.RAC_WITHOUT_ACTION
    )
    assert d_full.value == "BLOCK"
    assert d_wo.value == "ALLOW"


def test_static_tool_allowlist_differs_from_full_on_non_action_trace(bench_root) -> None:
    """TRC-V06-004 is resource-origin / not action escalation; static allowlist stays permissive on tools."""
    bundle = load_rac_tracebench(bench_root)
    case = next(c for c in bundle["traces"] if c["trace_id"] == "TRC-V06-004")
    trace = convert_trace_case_to_controlled_trace(case)
    d_full, *_ = run_trace_variant(trace, variant="FULL_RAC", mode=AblationMode.FULL_RAC)
    d_static, _b, _rules, reason, _ms = run_trace_variant(
        trace, variant="STATIC_TOOL_ALLOWLIST", mode=AblationMode.STATIC_TOOL_ALLOWLIST
    )
    assert d_full.value == "BLOCK"
    assert d_static.value == "ALLOW"
    assert reason and "skipped_by_baseline" in reason


def test_static_tool_allowlist_blocks_unknown_tool(bench_root) -> None:
    bundle = load_rac_tracebench(bench_root)
    case = next(c for c in bundle["traces"] if c["trace_id"] == "TRC-V06-002")
    trace = convert_trace_case_to_controlled_trace(case)
    d_static, _, rules, reason, _ = run_trace_variant(
        trace, variant="STATIC_TOOL_ALLOWLIST", mode=AblationMode.STATIC_TOOL_ALLOWLIST
    )
    assert d_static.value == "BLOCK"
    assert "STATIC_TOOL_ALLOWLIST_DENY" in rules
    assert "baseline=static_tool_allowlist" in reason


def test_summary_false_positive_rates_defined(bench_root) -> None:
    _rows, summary = build_experiment_rows(root=bench_root)
    assert "false_positive_by_variant" in summary
    assert "false_negative_by_variant" in summary
    assert "block_rate_by_variant" in summary
    assert isinstance(summary["per_family_results"], dict)
