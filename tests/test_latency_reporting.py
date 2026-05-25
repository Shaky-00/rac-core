from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from rac_core.evaluation.reporting import (
    aggregate_component_breakdown,
    aggregate_decision_paths,
    aggregate_predecessor_resolution,
    aggregate_workflow_scaling,
    generate_all_latency_reports,
    plot_component_breakdown,
    plot_predecessor_resolution,
    plot_workflow_scaling,
    read_latency_csv,
    summary_dicts_to_csv,
    summary_dicts_to_latex_tabular,
    summary_dicts_to_markdown,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

pytest.importorskip("matplotlib")


def _mini_workflow_csv() -> str:
    return (
        "scenario,workflow_length,predecessor_count,decision,total_ms,"
        "event_construction_ms,output_anchor_verification_ms,precommit_check_ms,"
        "persistence_ms,metadata_json\n"
        "benign_workflow_scaling_L2,2,,ALLOW,0.10,,,,,{}\n"
        "benign_workflow_scaling_L2,2,,ALLOW,0.12,,,,,{}\n"
        "benign_workflow_scaling_L3,3,,ALLOW,0.09,,,,,{}\n"
    )


def test_aggregate_workflow_scaling() -> None:
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8"
    ) as f:
        f.write(_mini_workflow_csv())
        p = Path(f.name)
    try:
        rows = read_latency_csv(p)
    finally:
        p.unlink(missing_ok=True)
    out = aggregate_workflow_scaling(rows)
    assert len(out) == 2
    by_w = {r["workflow_length"]: r for r in out}
    assert by_w[2]["n"] == 2
    assert by_w[3]["n"] == 1


def test_summary_serialization_roundtrip() -> None:
    rows = [
        {"a": 1, "b": 2.5},
        {"a": 2, "b": 3.1},
    ]
    assert "a" in summary_dicts_to_csv(rows)
    assert "| a |" in summary_dicts_to_markdown(rows)
    assert "\\begin{tabular}" in summary_dicts_to_latex_tabular(rows)


def test_plot_smoke(tmp_path: Path) -> None:
    wf = [
        {
            "workflow_length": 1,
            "n": 2,
            "mean_ms": 0.1,
            "median_ms": 0.1,
            "p95_ms": 0.11,
            "p99_ms": 0.12,
            "min_ms": 0.09,
            "max_ms": 0.13,
        },
        {
            "workflow_length": 5,
            "n": 2,
            "mean_ms": 0.2,
            "median_ms": 0.2,
            "p95_ms": 0.21,
            "p99_ms": 0.22,
            "min_ms": 0.19,
            "max_ms": 0.23,
        },
    ]
    p = tmp_path / "wf.png"
    plot_workflow_scaling(wf, p)
    assert p.is_file() and p.stat().st_size > 100

    pr = [
        {
            "predecessor_count": 1,
            "decision": "ALLOW",
            "blocked_rule": "",
            "n": 2,
            "mean_ms": 0.4,
            "median_ms": 0.4,
            "p95_ms": 0.5,
            "p99_ms": 0.6,
            "min_ms": 0.3,
            "max_ms": 0.7,
        }
    ]
    p2 = tmp_path / "pr.png"
    plot_predecessor_resolution(pr, p2)
    assert p2.is_file()

    bd = [
        {"component": "construct_event", "n": 2, "mean_ms": 0.05, "median_ms": 0.05, "p95_ms": 0.06, "p99_ms": 0.07},
        {"component": "tool_run", "n": 2, "mean_ms": 0.03, "median_ms": 0.03, "p95_ms": 0.04, "p99_ms": 0.05},
        {"component": "verify_anchor", "n": 2, "mean_ms": 0.03, "median_ms": 0.03, "p95_ms": 0.04, "p99_ms": 0.05},
        {"component": "precommit", "n": 2, "mean_ms": 0.17, "median_ms": 0.17, "p95_ms": 0.18, "p99_ms": 0.19},
    ]
    p3 = tmp_path / "bd.png"
    plot_component_breakdown(bd, p3)
    assert p3.is_file()


def test_generate_all_smoke(tmp_path: Path) -> None:
    d = tmp_path / "perf"
    d.mkdir()
    (d / "latency_workflow_scaling.csv").write_text(_mini_workflow_csv(), encoding="utf-8")
    (d / "latency_decision_paths.csv").write_text(
        "scenario,workflow_length,predecessor_count,decision,total_ms,"
        "event_construction_ms,output_anchor_verification_ms,precommit_check_ms,"
        "persistence_ms,metadata_json\n"
        'decision_path_benign_read_summarize,,,ALLOW,0.4,,,,,"{}"\n',
        encoding="utf-8",
    )
    (d / "latency_predecessor_resolution.csv").write_text(
        "scenario,workflow_length,predecessor_count,decision,total_ms,"
        "event_construction_ms,output_anchor_verification_ms,precommit_check_ms,"
        "persistence_ms,metadata_json\n"
        'predecessor_resolution_n1,,1,ALLOW,0.5,,,,,"{""blocked_rule"": null}"\n',
        encoding="utf-8",
    )
    (d / "latency_breakdown.csv").write_text(
        "scenario,workflow_length,predecessor_count,decision,total_ms,"
        "event_construction_ms,output_anchor_verification_ms,precommit_check_ms,"
        "persistence_ms,metadata_json\n"
        'c,,,ALLOW,0.3,0.05,0.03,0.17,,"{""tool_execution_ms"": 0.02}"\n',
        encoding="utf-8",
    )
    out = generate_all_latency_reports(d, log=lambda _: None)
    assert any(p.name == "latency_workflow_scaling_summary.csv" for p in out)
    assert (d / "latency_workflow_scaling.png").is_file()


def test_aggregate_decision_paths_maps_labels() -> None:
    rows = [
        {
            "scenario": "decision_path_forged_predecessor",
            "workflow_length": "",
            "predecessor_count": "",
            "decision": "BLOCK",
            "total_ms": "1.0",
            "event_construction_ms": "",
            "output_anchor_verification_ms": "",
            "precommit_check_ms": "",
            "persistence_ms": "",
            "metadata_json": "{}",
        }
    ]
    out = aggregate_decision_paths(rows)
    assert out[0]["path"] == "forged_predecessor"
    assert out[0]["decision"] == "BLOCK"


