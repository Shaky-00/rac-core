from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from rac_core.evaluation.cli_config import (
    DEFAULT_PREDECESSOR_COUNTS,
    DEFAULT_WORKFLOW_LENGTHS,
    QUICK_PREDECESSOR_COUNTS,
    QUICK_REPEATS,
    QUICK_WARMUP,
    QUICK_WORKFLOW_LENGTHS,
    build_latency_eval_config,
)
from rac_core.evaluation.latency import (
    LatencySample,
    percentile,
    run_component_breakdown_benchmark,
    run_decision_path_benchmark,
    run_predecessor_resolution_benchmark,
    run_workflow_length_benchmark,
    samples_to_csv,
    summarize_latency,
    write_json,
    write_text,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_latency_cli_default_config() -> None:
    cfg = build_latency_eval_config([])
    assert cfg.quick is False
    assert cfg.workflow_lengths == DEFAULT_WORKFLOW_LENGTHS
    assert cfg.predecessor_counts == DEFAULT_PREDECESSOR_COUNTS
    assert cfg.repeats == 100
    assert cfg.warmup == 10


def test_latency_cli_quick_config() -> None:
    cfg = build_latency_eval_config(["--quick"])
    assert cfg.quick is True
    assert cfg.workflow_lengths == QUICK_WORKFLOW_LENGTHS
    assert cfg.predecessor_counts == QUICK_PREDECESSOR_COUNTS
    assert cfg.repeats == QUICK_REPEATS
    assert cfg.warmup == QUICK_WARMUP


def test_latency_cli_overrides() -> None:
    cfg = build_latency_eval_config(
        [
            "--repeats",
            "20",
            "--warmup",
            "2",
            "--lengths",
            "1,3",
            "--predecessor-counts",
            "1,4",
        ]
    )
    assert cfg.quick is False
    assert cfg.workflow_lengths == (1, 3)
    assert cfg.predecessor_counts == (1, 4)
    assert cfg.repeats == 20
    assert cfg.warmup == 2


def test_latency_cli_quick_with_repeat_override() -> None:
    cfg = build_latency_eval_config(["--quick", "--repeats", "7"])
    assert cfg.quick is True
    assert cfg.repeats == 7
    assert cfg.workflow_lengths == QUICK_WORKFLOW_LENGTHS


def test_run_latency_script_quick_stdout_smoke() -> None:
    script = REPO_ROOT / "scripts" / "run_latency_evaluation.py"
    r = subprocess.run(
        [sys.executable, str(script), "--quick"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "Latency evaluation configuration" in out
    assert "quick: True" in out
    assert "Running workflow length benchmark" in out
    assert "[1/4] Done: latency_workflow_scaling.csv" in out
    assert "workflow_lengths: [1, 5, 10]" in out
    assert "predecessor_counts: [1, 2]" in out


def test_percentile_reasonable() -> None:
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    p50 = percentile(xs, 0.5)
    assert 2.5 <= p50 <= 3.5
    p95 = percentile(xs, 0.95)
    assert 4.5 <= p95 <= 5.0


def test_summarize_latency_basic() -> None:
    samples = [
        LatencySample(scenario="s1", decision="ALLOW", total_ms=10.0),
        LatencySample(scenario="s1", decision="ALLOW", total_ms=20.0),
        LatencySample(scenario="s1", decision="ALLOW", total_ms=30.0),
    ]
    s = summarize_latency(samples, "s1")
    assert s.n == 3
    assert s.mean_ms == 20.0
    assert s.min_ms == 10.0
    assert s.max_ms == 30.0
    assert s.p95_ms >= s.median_ms


def test_workflow_length_benchmark_quick_smoke() -> None:
    samples, summaries = run_workflow_length_benchmark(
        lengths=[1, 2], repeats=2, warmup=0
    )
    assert samples and summaries
    assert all(s.decision in ("ALLOW", "BLOCK") for s in samples)
    assert len(summaries) == 2


def test_decision_path_benchmark_quick_smoke() -> None:
    samples, summaries = run_decision_path_benchmark(repeats=2, warmup=0)
    scenarios = {s.scenario for s in samples}
    assert any("benign_read_summarize" in x for x in scenarios)
    assert any("action_escalation" in x for x in scenarios)
    assert any("resource_expansion" in x for x in scenarios)
    assert samples and summaries


def test_predecessor_resolution_benchmark_quick_smoke() -> None:
    samples, summaries = run_predecessor_resolution_benchmark(
        predecessor_counts=[1, 2], repeats=2, warmup=0
    )
    assert samples and summaries
    assert len(summaries) == 2


def test_csv_json_export_smoke(tmp_path: Path) -> None:
    samples = [
        LatencySample(
            scenario="t",
            decision="ALLOW",
            total_ms=1.5,
            metadata={"k": 1},
        )
    ]
    csv_path = tmp_path / "x.csv"
    write_text(csv_path, samples_to_csv(samples))
    assert csv_path.is_file() and csv_path.stat().st_size > 0
    json_path = tmp_path / "x.json"
    write_json(json_path, {"samples": [asdict(samples[0])]})
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["samples"]


def test_component_breakdown_benchmark_quick_smoke() -> None:
    samples, summaries = run_component_breakdown_benchmark(repeats=2, warmup=0)
    assert samples
    assert summaries
    assert any(s.metadata.get("tool_execution_ms") is not None for s in samples)
