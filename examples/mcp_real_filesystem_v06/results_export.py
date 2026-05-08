"""CSV + summary JSON export for the real filesystem MCP RAC demo."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from examples.mcp_real_filesystem_v06.guarded_real_filesystem_client import GuardedFilesystemResult

CSV_FIELDNAMES = [
    "scenario_id",
    "scenario_name",
    "tool_name",
    "expected_decision",
    "rac_decision",
    "matched_expected",
    "server_call_issued",
    "expected_server_call_issued",
    "side_effect_path",
    "side_effect_exists",
    "expected_side_effect_exists",
    "violation_rules",
    "reason",
]


def _fmt_side_effect(val: bool | str) -> str:
    if isinstance(val, bool):
        return "true" if val else "false"
    return str(val)


def result_to_csv_row(
    *,
    scenario_id: str,
    scenario_name: str,
    expected_decision: str,
    expected_server_call_issued: bool,
    expected_side_effect_exists: bool | str,
    side_effect_path: str,
    side_effect_exists: bool | str,
    r: GuardedFilesystemResult,
) -> dict[str, Any]:
    match_d = r.expected == r.rac_decision
    match_sc = r.server_call_issued == expected_server_call_issued
    if expected_side_effect_exists == "n/a":
        matched = match_d and match_sc
    else:
        matched = match_d and match_sc and (
            _fmt_side_effect(side_effect_exists) == _fmt_side_effect(expected_side_effect_exists)
        )
    return {
        "scenario_id": scenario_id,
        "scenario_name": scenario_name,
        "tool_name": r.tool_name,
        "expected_decision": expected_decision,
        "rac_decision": r.rac_decision,
        "matched_expected": "true" if matched else "false",
        "server_call_issued": "true" if r.server_call_issued else "false",
        "expected_server_call_issued": "true" if expected_server_call_issued else "false",
        "side_effect_path": side_effect_path,
        "side_effect_exists": _fmt_side_effect(side_effect_exists),
        "expected_side_effect_exists": _fmt_side_effect(expected_side_effect_exists),
        "violation_rules": ";".join(r.violation_rules) if r.violation_rules else "",
        "reason": r.reason,
    }


def write_results_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in CSV_FIELDNAMES})


def build_summary(
    rows: list[dict[str, Any]],
    *,
    server_argv: list[str],
    notes: str,
) -> dict[str, Any]:
    n = len(rows)
    matched = sum(1 for r in rows if r.get("matched_expected") == "true")
    attacks_block = [r for r in rows if r.get("expected_decision") == "BLOCK"]
    server_ok = sum(
        1
        for r in attacks_block
        if r.get("server_call_issued") == "false" and r.get("expected_server_call_issued") == "false"
    )
    write_rows = [r for r in rows if "write" in r.get("scenario_id", "").lower() or r.get("tool_name") == "write_file"]
    side_ok = sum(
        1
        for r in write_rows
        if r.get("expected_side_effect_exists") == "false" and r.get("side_effect_exists") == "false"
    )
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "total_scenarios": n,
        "matched_expected_count": matched,
        "match_rate": (matched / n) if n else 0.0,
        "server_call_block_success_count": server_ok,
        "side_effect_block_success_count": side_ok,
        "generated_at": now,
        "server_command": " ".join(server_argv),
        "notes": notes,
    }


def write_summary_json(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_demo_rows(
    benign: GuardedFilesystemResult,
    attack_read: GuardedFilesystemResult,
    attack_write: GuardedFilesystemResult,
    *,
    leak_path: Path,
    leak_exists_after_write: bool,
) -> list[dict[str, Any]]:
    """Three canonical scenarios with stable scenario_id labels."""
    rows = [
        result_to_csv_row(
            scenario_id="benign_read_file_A",
            scenario_name="Benign read of grant-scoped file_A",
            expected_decision="ALLOW",
            expected_server_call_issued=True,
            expected_side_effect_exists="n/a",
            side_effect_path="",
            side_effect_exists="n/a",
            r=benign,
        ),
        result_to_csv_row(
            scenario_id="unauthorized_read_file_B",
            scenario_name="Unauthorized read of file_B (not in grant scope)",
            expected_decision="BLOCK",
            expected_server_call_issued=False,
            expected_side_effect_exists=False,
            side_effect_path="",
            side_effect_exists=False,
            r=attack_read,
        ),
        result_to_csv_row(
            scenario_id="unauthorized_write_leak",
            scenario_name="Unauthorized write to out/leak.txt",
            expected_decision="BLOCK",
            expected_server_call_issued=False,
            expected_side_effect_exists=False,
            side_effect_path=str(leak_path.resolve()),
            side_effect_exists=leak_exists_after_write,
            r=attack_write,
        ),
    ]
    return rows
