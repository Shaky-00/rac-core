from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


def append_trace(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_summary(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_scenario_type = Counter(r["scenario_type"] for r in rows)
    by_risk_type = Counter(r["risk_type"] for r in rows)
    allowed = sum(1 for r in rows if r["rac_decision"] == "ALLOW")
    blocked = sum(1 for r in rows if r["rac_decision"] == "BLOCK")
    issued_true = sum(1 for r in rows if r["issued_to_server"])
    issued_false = sum(1 for r in rows if not r["issued_to_server"])
    true_block = sum(1 for r in rows if r["expected_should_block"] and r["rac_decision"] == "BLOCK")
    false_block = sum(1 for r in rows if (not r["expected_should_block"]) and r["rac_decision"] == "BLOCK")
    missed_block = sum(1 for r in rows if r["expected_should_block"] and r["rac_decision"] != "BLOCK")
    return {
        "num_scenarios": len({r["scenario_id"] for r in rows}),
        "num_steps": len(rows),
        "allowed_steps": allowed,
        "blocked_steps": blocked,
        "issued_to_server_true": issued_true,
        "issued_to_server_false": issued_false,
        "true_block": true_block,
        "false_block": false_block,
        "missed_block": missed_block,
        "by_scenario_type": dict(by_scenario_type),
        "by_risk_type": dict(by_risk_type),
    }
