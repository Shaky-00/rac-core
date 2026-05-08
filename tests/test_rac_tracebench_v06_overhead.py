"""Tests for RAC-TraceBench v0.6 pre-commit overhead microbenchmark."""

from __future__ import annotations

import json

import pytest

from rac_core.validation.rac_tracebench_overhead import (
    CSV_FIELDNAMES,
    build_summary,
    collect_overhead_rows,
    resolve_tracebench_root,
    run_overhead_and_write,
    write_overhead_results,
)


@pytest.fixture(scope="module")
def bench_root():
    root = resolve_tracebench_root()
    if root is None:
        pytest.skip("RAC-TraceBench v0.6 root not found")
    return root


SUMMARY_KEYS = {
    "iterations",
    "total_runs",
    "p50_step_ms",
    "p95_step_ms",
    "p99_step_ms",
    "mean_step_ms",
    "max_step_ms",
    "mean_trace_ms",
    "p95_trace_ms",
    "per_family_mean_ms",
    "per_step_count",
    "generated_at",
}


def test_collect_overhead_small_iterations(bench_root, tmp_path) -> None:
    rows, n_tr = collect_overhead_rows(bench_root, iterations=2)
    assert n_tr == 32
    assert len(rows) >= 32 * 2  # at least one row per trace per iteration (early BLOCK may shorten)
    summary = build_summary(rows, iterations=2, num_traces=n_tr)
    for k in SUMMARY_KEYS:
        assert k in summary
    assert summary["iterations"] == 2
    assert summary["total_runs"] == 64
    assert summary["coarse_grained_measurement_notes"]
    assert "precommit_check_ms" in summary["coarse_grained_measurement_notes"]


def test_write_csv_json_schema(bench_root, tmp_path) -> None:
    rows, n_tr = collect_overhead_rows(bench_root, iterations=1)
    summary = build_summary(rows, iterations=1, num_traces=n_tr)
    csv_p, json_p = write_overhead_results(rows, summary, tmp_path)
    header = csv_p.read_text(encoding="utf-8").splitlines()[0]
    for col in CSV_FIELDNAMES:
        assert col in header
    loaded = json.loads(json_p.read_text(encoding="utf-8"))
    assert loaded["total_step_records"] == len(rows)


def test_run_overhead_and_write_integration(bench_root, tmp_path) -> None:
    csv_p, json_p, summary = run_overhead_and_write(bench_root, tmp_path, iterations=1)
    assert csv_p.is_file() and json_p.is_file()
    assert summary["num_traces"] == 32

