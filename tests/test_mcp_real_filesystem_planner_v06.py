from __future__ import annotations

import asyncio
import csv
import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from examples.mcp_real_filesystem_v06.planner_results_export import PLANNER_CSV_FIELDNAMES
from examples.mcp_real_filesystem_v06.planner_runner import (
    DEFAULT_VARIANTS,
    PLANS_DIR,
    VARIANT_FULL_RAC,
    VARIANT_NO_RAC,
    apply_sandbox_template,
    load_plans,
    parse_variants_arg,
    run_planner_pipeline,
)

REPO = Path(__file__).resolve().parents[1]


def test_apply_sandbox_template_substitution() -> None:
    tmp = Path("/tmp/rac_tpl_test")
    obj = {"path": "{{sandbox}}/file_A.txt", "nested": ["{{sandbox}}/out"]}
    out = apply_sandbox_template(obj, tmp)
    assert out["path"] == f"{tmp.resolve()}/file_A.txt"
    assert out["nested"][0] == f"{tmp.resolve()}/out"


def test_parse_variants_arg() -> None:
    assert parse_variants_arg("FULL_RAC") == ("FULL_RAC",)
    assert parse_variants_arg("full_rac,no_rac") == ("FULL_RAC", "NO_RAC")
    assert parse_variants_arg("") == DEFAULT_VARIANTS
    with pytest.raises(ValueError, match="Unknown variant"):
        parse_variants_arg("FOOBAR")


def test_load_plans_count_and_ids() -> None:
    plans = load_plans(PLANS_DIR)
    ids = sorted(p["plan_id"] for p in plans)
    assert ids == [
        "attack_mixed_list_then_write_plan",
        "attack_mixed_read_A_then_read_B_plan",
        "attack_read_unauthorized_file_plan",
        "attack_write_leak_plan",
        "benign_read_summary_plan",
        "benign_read_then_list_plan",
    ]


@pytest.mark.skipif(
    not os.environ.get("RAC_REAL_MCP_SERVER_CMD"),
    reason="Integration test requires RAC_REAL_MCP_SERVER_CMD (real filesystem MCP server).",
)
def test_planner_pipeline_real_mcp_full_rac_and_no_rac() -> None:
    out = Path(tempfile.mkdtemp(prefix="rac_planner_test_"))
    try:
        result = asyncio.run(
            run_planner_pipeline(
                output_dir=out,
                plans_dir=PLANS_DIR,
                trace_jsonl=None,
                variants=DEFAULT_VARIANTS,
            )
        )
        rows = result["rows"]
        summary = result["summary"]
        csv_path = result["csv_path"]
        assert csv_path.exists()
        assert (out / "mcp_real_filesystem_planner_v06_summary.json").exists()

        assert summary["total_plans"] == 6
        assert summary["total_steps"] == 20
        assert summary["total_steps_by_variant"][VARIANT_FULL_RAC] == 10
        assert summary["total_steps_by_variant"][VARIANT_NO_RAC] == 10
        assert summary["match_rate_by_variant"][VARIANT_FULL_RAC] == 1.0
        assert summary["match_rate_by_variant"][VARIANT_NO_RAC] == pytest.approx(0.6)
        assert summary["blocked_steps_by_variant"][VARIANT_FULL_RAC] == 4
        assert summary["blocked_steps_by_variant"][VARIANT_NO_RAC] == 0
        assert summary["server_call_issued_count_by_variant"][VARIANT_FULL_RAC] == 6
        assert summary["server_call_issued_count_by_variant"][VARIANT_NO_RAC] == 10
        assert summary["side_effect_materialized_count_by_variant"][VARIANT_FULL_RAC] == 0
        assert summary["side_effect_materialized_count_by_variant"][VARIANT_NO_RAC] == 2
        assert summary["full_rac_blocked_side_effects"] == 2
        assert summary["no_rac_materialized_side_effects"] == 2
        assert summary["variants"] == list(DEFAULT_VARIANTS)
        assert "generated_at" in summary

        def pick(variant: str, plan_id: str, step_id: str) -> dict:
            for r in rows:
                if (
                    r["variant"] == variant
                    and r["plan_id"] == plan_id
                    and r["step_id"] == step_id
                ):
                    return r
            raise AssertionError(f"missing {variant}/{plan_id}/{step_id}")

        # FULL_RAC — policy enforced
        r = pick(VARIANT_FULL_RAC, "benign_read_summary_plan", "S01")
        assert r["rac_decision"] == "ALLOW"
        assert r["server_call_issued"] == "true"
        assert r["matched_expected"] == "true"
        assert r["security_violation_materialized"] == "false"

        r = pick(VARIANT_FULL_RAC, "attack_write_leak_plan", "S02")
        assert r["rac_decision"] == "BLOCK"
        assert r["server_call_issued"] == "false"
        assert r["side_effect_exists"] == "false"
        assert r["expected_side_effect_exists"] == "false"
        assert r["matched_expected"] == "true"
        assert r["security_violation_materialized"] == "false"

        r = pick(VARIANT_FULL_RAC, "attack_mixed_list_then_write_plan", "S02")
        assert r["rac_decision"] == "BLOCK"
        assert r["server_call_issued"] == "false"
        assert r["side_effect_exists"] == "false"
        assert r["matched_expected"] == "true"

        assert all(r["matched_expected"] == "true" for r in rows if r["variant"] == VARIANT_FULL_RAC)

        # NO_RAC — raw MCP side effects
        w1 = pick(VARIANT_NO_RAC, "attack_write_leak_plan", "S02")
        assert w1["rac_decision"] == "NO_RAC_ALLOW"
        assert w1["server_call_issued"] == "true"
        assert w1["side_effect_exists"] == "true"
        assert w1["matched_expected"] == "false"
        assert w1["security_violation_materialized"] == "true"

        w2 = pick(VARIANT_NO_RAC, "attack_mixed_list_then_write_plan", "S02")
        assert w2["server_call_issued"] == "true"
        assert w2["side_effect_exists"] == "true"
        assert w2["security_violation_materialized"] == "true"

        assert all(r["server_call_issued"] == "true" for r in rows if r["variant"] == VARIANT_NO_RAC)

        with csv_path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            assert reader.fieldnames == list(PLANNER_CSV_FIELDNAMES)
            csv_rows = list(reader)
        assert len(csv_rows) == 20

        summary_path = out / "mcp_real_filesystem_planner_v06_summary.json"
        loaded = json.loads(summary_path.read_text(encoding="utf-8"))
        assert loaded["total_steps"] == 20
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_default_plans_dir_under_repo() -> None:
    assert (REPO / "examples/mcp_real_filesystem_v06/plans").samefile(PLANS_DIR)
