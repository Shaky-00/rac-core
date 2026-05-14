from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

mcp = pytest.importorskip("mcp")

from examples.mcp_live_enforcement.client.scenario_runner import run_all

BASE = Path(__file__).resolve().parents[1] / "examples" / "mcp_live_enforcement"


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def test_mcp_live_enforcement_case_study() -> None:
    _ = mcp
    scenario_dir = BASE / "scenarios"
    scenario_files = sorted(p.name for p in scenario_dir.glob("*.json"))
    assert scenario_files == [
        "benign_deep_internal.json",
        "benign_internal_summary.json",
        "injection_induced_external_disclosure.json",
        "injection_induced_resource_drift.json",
        "purpose_drift_external_send.json",
        "resource_expansion.json",
    ]

    outcome = asyncio.run(run_all())
    rows = outcome["rows"]

    blocked_rows = [r for r in rows if r["rac_decision"] == "BLOCK"]
    allowed_rows = [r for r in rows if r["rac_decision"] == "ALLOW"]
    assert blocked_rows, "expected blocked steps"
    assert allowed_rows, "expected allowed steps"
    assert all(not r["issued_to_server"] for r in blocked_rows)
    assert all(r["issued_to_server"] for r in allowed_rows)

    def _lookup(sid: str, step: str) -> dict[str, object]:
        for row in rows:
            if row["scenario_id"] == sid and row["step_id"] == step:
                return row
        raise AssertionError(f"missing row for {sid}/{step}")

    assert _lookup("purpose_drift_external_send", "3")["rac_decision"] == "BLOCK"
    assert _lookup("resource_expansion", "4")["rac_decision"] == "BLOCK"
    assert _lookup("injection_induced_external_disclosure", "3")["rac_decision"] == "BLOCK"
    assert _lookup("benign_internal_summary", "3")["rac_decision"] == "ALLOW"
    assert _lookup("benign_internal_summary", "3")["issued_to_server"] is True
    assert _lookup("benign_deep_internal", "4")["rac_decision"] == "ALLOW"
    assert _lookup("benign_deep_internal", "4")["issued_to_server"] is True

    trace_rows = _read_jsonl(BASE / "traces" / "mcp_guarded_trace.jsonl")
    assert len(trace_rows) == len(rows)

    comm_logs = _read_jsonl(BASE / "traces" / "server_call_logs" / "communication_server.jsonl")
    # In this stage all send_email attempts are expected to be blocked pre-call.
    assert comm_logs == []
