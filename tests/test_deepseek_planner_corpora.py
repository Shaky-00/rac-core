"""Tests for DeepSeek offline corpus generation (no live API in pytest)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GEN_SCRIPT = REPO / "scripts" / "generate_deepseek_planner_plans.py"
NORM_SCRIPT = REPO / "scripts" / "normalize_deepseek_planner_plans.py"
FIXTURE_RAW = (
    REPO
    / "examples/mcp_real_filesystem_v06/llm_generation/raw_outputs"
    / "fixture_benign_read_and_summarize.json"
)


def test_generate_dry_run_succeeds_without_api_key() -> None:
    env = {k: v for k, v in os.environ.items() if k != "DEEPSEEK_API_KEY"}
    env.pop("DEEPSEEK_API_KEY", None)
    out = Path(tempfile.mkdtemp(prefix="rac_ds_dry_"))
    try:
        r = subprocess.run(
            [
                sys.executable,
                str(GEN_SCRIPT),
                "--dry-run",
                "--limit",
                "1",
                "--output-dir",
                str(out),
            ],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert r.returncode == 0, r.stderr + r.stdout
        assert (out / "prompts").is_dir()
        assert any((out / "prompts").glob("*.txt"))
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_generate_without_key_non_dry_run_exits_2() -> None:
    env = {k: v for k, v in os.environ.items() if k != "DEEPSEEK_API_KEY"}
    env.pop("DEEPSEEK_API_KEY", None)
    out = Path(tempfile.mkdtemp(prefix="rac_ds_fail_"))
    try:
        r = subprocess.run(
            [sys.executable, str(GEN_SCRIPT), "--limit", "1", "--output-dir", str(out)],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert r.returncode == 2
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_normalizer_skips_fixtures_by_default() -> None:
    raw_dir = Path(tempfile.mkdtemp(prefix="rac_norm_skip_"))
    norm_dir = Path(tempfile.mkdtemp(prefix="rac_norm_mid_"))
    plans_dir = Path(tempfile.mkdtemp(prefix="rac_norm_plans_"))
    report = Path(tempfile.mkdtemp(prefix="rac_norm_rep_")) / "normalization_report.json"
    try:
        shutil.copy(FIXTURE_RAW, raw_dir / FIXTURE_RAW.name)
        r = subprocess.run(
            [
                sys.executable,
                str(NORM_SCRIPT),
                "--raw-dir",
                str(raw_dir),
                "--normalized-dir",
                str(norm_dir),
                "--plans-dir",
                str(plans_dir),
                "--report",
                str(report),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert r.returncode == 0, r.stderr + r.stdout
        assert not list(plans_dir.glob("llm_norm_*.json"))
        rep = json.loads(report.read_text(encoding="utf-8"))
        assert rep["valid_normalized_plans"] == 0
        assert rep["fixture_outputs_seen"] == 1
        assert rep["fixture_outputs_skipped"] == 1
        assert rep["real_api_outputs_processed"] == 0
    finally:
        shutil.rmtree(raw_dir, ignore_errors=True)
        shutil.rmtree(norm_dir, ignore_errors=True)
        shutil.rmtree(plans_dir, ignore_errors=True)
        shutil.rmtree(report.parent, ignore_errors=True)


def test_normalizer_include_fixtures_processes_fixture() -> None:
    raw_dir = Path(tempfile.mkdtemp(prefix="rac_norm_in_"))
    norm_dir = Path(tempfile.mkdtemp(prefix="rac_norm_mid_"))
    plans_dir = Path(tempfile.mkdtemp(prefix="rac_norm_plans_"))
    report = Path(tempfile.mkdtemp(prefix="rac_norm_rep_")) / "normalization_report.json"
    try:
        shutil.copy(FIXTURE_RAW, raw_dir / FIXTURE_RAW.name)
        r = subprocess.run(
            [
                sys.executable,
                str(NORM_SCRIPT),
                "--include-fixtures",
                "--raw-dir",
                str(raw_dir),
                "--normalized-dir",
                str(norm_dir),
                "--plans-dir",
                str(plans_dir),
                "--report",
                str(report),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert r.returncode == 0, r.stderr + r.stdout
        out_plan = plans_dir / "llm_norm_benign_read_and_summarize.json"
        assert out_plan.exists()
        data = json.loads(out_plan.read_text(encoding="utf-8"))
        assert data["plan_id"] == "llm_norm_benign_read_and_summarize"
        assert set(data.keys()) <= {
            "plan_id",
            "description",
            "expected_final_decision",
            "grant_extra_resource_ids",
            "steps",
        }
        assert all(
            set(s.keys()) <= {"step_id", "tool_name", "arguments", "expected_decision"} for s in data["steps"]
        )
        rep = json.loads(report.read_text(encoding="utf-8"))
        assert rep["valid_normalized_plans"] == 1
        assert rep.get("manual_semantic_edit") is False
        assert rep["fixture_outputs_skipped"] == 0
        assert rep["real_api_outputs_processed"] == 0
        assert rep["fixture_outputs_processed_in_run"] == 1
        assert "normalized_plan_output_dir" in rep and "replay_plan_output_dir" in rep
    finally:
        shutil.rmtree(raw_dir, ignore_errors=True)
        shutil.rmtree(norm_dir, ignore_errors=True)
        shutil.rmtree(plans_dir, ignore_errors=True)
        shutil.rmtree(report.parent, ignore_errors=True)


def test_normalizer_clean_output_removes_stale_llm_norm() -> None:
    raw_dir = Path(tempfile.mkdtemp(prefix="rac_norm_cl_"))
    norm_dir = Path(tempfile.mkdtemp(prefix="rac_norm_clm_"))
    plans_dir = Path(tempfile.mkdtemp(prefix="rac_norm_clp_"))
    report = Path(tempfile.mkdtemp(prefix="rac_norm_clr_")) / "normalization_report.json"
    try:
        shutil.copy(FIXTURE_RAW, raw_dir / FIXTURE_RAW.name)
        junk = plans_dir / "llm_norm_stale_should_delete.json"
        junk.write_text('{"plan_id":"x"}', encoding="utf-8")
        r = subprocess.run(
            [
                sys.executable,
                str(NORM_SCRIPT),
                "--include-fixtures",
                "--clean-output",
                "--raw-dir",
                str(raw_dir),
                "--normalized-dir",
                str(norm_dir),
                "--plans-dir",
                str(plans_dir),
                "--report",
                str(report),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert r.returncode == 0, r.stderr + r.stdout
        assert not junk.exists()
        assert (plans_dir / "llm_norm_benign_read_and_summarize.json").exists()
    finally:
        shutil.rmtree(raw_dir, ignore_errors=True)
        shutil.rmtree(norm_dir, ignore_errors=True)
        shutil.rmtree(plans_dir, ignore_errors=True)
        shutil.rmtree(report.parent, ignore_errors=True)


def test_plan_normalization_validate_committed_llm_plan() -> None:
    from examples.mcp_real_filesystem_v06.llm_generation.plan_normalization import (
        strip_runner_only_plan,
        validate_plan_with_temp_sandbox,
    )

    p = REPO / "examples/mcp_real_filesystem_v06/plans/llm_norm_unauthorized_write_leak.json"
    plan = json.loads(p.read_text(encoding="utf-8"))
    assert not validate_plan_with_temp_sandbox(plan)
    strip_runner_only_plan(plan)


def test_build_planner_summary_llm_norm_variant_metrics() -> None:
    from examples.mcp_real_filesystem_v06.planner_results_export import build_planner_summary

    rows = [
        {
            "variant": "FULL_RAC",
            "plan_id": "llm_norm_test",
            "matched_expected": "true",
            "rac_decision": "BLOCK",
            "server_call_issued": "false",
            "tool_name": "write_file",
            "side_effect_exists": "false",
            "expected_decision": "BLOCK",
            "security_violation_materialized": "false",
        },
        {
            "variant": "NO_RAC",
            "plan_id": "llm_norm_test",
            "matched_expected": "false",
            "rac_decision": "NO_RAC_ALLOW",
            "server_call_issued": "true",
            "tool_name": "write_file",
            "side_effect_exists": "true",
            "expected_decision": "BLOCK",
            "security_violation_materialized": "true",
        },
    ]
    s = build_planner_summary(
        rows,
        total_plans=1,
        variants=["FULL_RAC", "NO_RAC"],
        server_command="test",
        notes="n",
    )
    assert "llm_norm_match_rate_by_variant" in s
    assert s["llm_norm_match_rate_by_variant"]["FULL_RAC"] == 1.0
    assert s["llm_norm_blocked_steps_by_variant"]["FULL_RAC"] == 1
    assert s["llm_norm_side_effect_materialized_count_by_variant"]["NO_RAC"] == 1
