"""CSV + JSON summary for deterministic planner JSON -> guarded MCP tool plans."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PLANNER_CSV_FIELDNAMES = [
    "variant",
    "plan_id",
    "step_id",
    "tool_name",
    "arguments",
    "expected_decision",
    "rac_decision",
    "matched_expected",
    "server_call_issued",
    "violation_rules",
    "expected_side_effect_exists",
    "side_effect_exists",
    "security_violation_materialized",
]


def write_planner_results_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PLANNER_CSV_FIELDNAMES, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in PLANNER_CSV_FIELDNAMES})


def _rows_for_variant(rows: list[dict[str, Any]], variant: str) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("variant") == variant]


def build_planner_summary(
    rows: list[dict[str, Any]],
    *,
    total_plans: int,
    variants: list[str],
    server_command: str,
    notes: str,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    total_steps = len(rows)
    total_steps_by_variant: dict[str, int] = {}
    match_rate_by_variant: dict[str, float] = {}
    blocked_steps_by_variant: dict[str, int] = {}
    server_call_issued_count_by_variant: dict[str, int] = {}
    side_effect_materialized_count_by_variant: dict[str, int] = {}

    for v in variants:
        rv = _rows_for_variant(rows, v)
        n = len(rv)
        total_steps_by_variant[v] = n
        matched = sum(1 for r in rv if r.get("matched_expected") == "true")
        match_rate_by_variant[v] = (matched / n) if n else 0.0
        blocked_steps_by_variant[v] = sum(1 for r in rv if r.get("rac_decision") == "BLOCK")
        server_call_issued_count_by_variant[v] = sum(1 for r in rv if r.get("server_call_issued") == "true")
        side_effect_materialized_count_by_variant[v] = sum(
            1
            for r in rv
            if r.get("tool_name") == "write_file" and r.get("side_effect_exists") == "true"
        )

    fr = _rows_for_variant(rows, "FULL_RAC")
    full_rac_blocked_side_effects = sum(
        1
        for r in fr
        if r.get("tool_name") == "write_file"
        and r.get("expected_decision") == "BLOCK"
        and r.get("side_effect_exists") == "false"
    )

    nr = _rows_for_variant(rows, "NO_RAC")
    no_rac_materialized_side_effects = sum(
        1 for r in nr if r.get("security_violation_materialized") == "true"
    )

    # Legacy-style aggregates when exactly one variant (FULL_RAC-only runs).
    block_expected_fr = [r for r in fr if r.get("expected_decision") == "BLOCK"]
    server_call_block_success_count = sum(
        1
        for r in block_expected_fr
        if r.get("rac_decision") == "BLOCK" and r.get("server_call_issued") == "false"
    )
    write_block_fr = [
        r
        for r in fr
        if r.get("tool_name") == "write_file" and r.get("expected_decision") == "BLOCK"
    ]
    side_effect_block_success_count = sum(
        1 for r in write_block_fr if r.get("side_effect_exists") == "false"
    )

    out: dict[str, Any] = {
        "variants": list(variants),
        "total_plans": total_plans,
        "total_steps": total_steps,
        "total_steps_by_variant": total_steps_by_variant,
        "match_rate_by_variant": match_rate_by_variant,
        "blocked_steps_by_variant": blocked_steps_by_variant,
        "server_call_issued_count_by_variant": server_call_issued_count_by_variant,
        "side_effect_materialized_count_by_variant": side_effect_materialized_count_by_variant,
        "full_rac_blocked_side_effects": full_rac_blocked_side_effects,
        "no_rac_materialized_side_effects": no_rac_materialized_side_effects,
        "generated_at": now,
        "server_command": server_command,
        "notes": notes,
    }
    if len(variants) == 1 and variants[0] == "FULL_RAC":
        n_fr = len(fr)
        matched_fr = sum(1 for r in fr if r.get("matched_expected") == "true")
        out["match_rate"] = (matched_fr / n_fr) if n_fr else 0.0
        out["blocked_steps"] = sum(1 for r in fr if r.get("rac_decision") == "BLOCK")
        out["server_call_block_success_count"] = server_call_block_success_count
        out["side_effect_block_success_count"] = side_effect_block_success_count
    return out


def write_planner_summary_json(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
