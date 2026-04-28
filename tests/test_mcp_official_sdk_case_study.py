from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

mcp = pytest.importorskip("mcp")

from examples.mcp_official_sdk.run_mcp_sdk_case_study import run_case_study


def test_mcp_official_sdk_case_study_smoke() -> None:
    _ = mcp
    result = asyncio.run(run_case_study())
    assert "results" in result
    assert "summary" in result

    artifact = Path("artifacts/tables/mcp_sdk_case_study.json")
    assert artifact.exists()
    rows = json.loads(artifact.read_text(encoding="utf-8"))
    assert rows
    summary_artifact = Path("artifacts/tables/mcp_sdk_case_study_summary.json")
    assert summary_artifact.exists()
    summary_rows = json.loads(summary_artifact.read_text(encoding="utf-8"))
    assert summary_rows

    assert any(r["rac_decision"] == "ALLOW" and r["server_call_issued"] is True for r in rows)
    assert any(r["rac_decision"] == "BLOCK" and r["server_call_issued"] is False for r in rows)
    assert all(r["matched"] is True for r in rows)
    assert any(
        r["Outcome"] == "BLOCK" and r["Server_call_issued"] == "No" for r in summary_rows
    )

    action_block = next(
        r for r in rows if r["scenario"] == "mcp_action_escalation/email"
    )
    assert action_block["rac_decision"] == "BLOCK"
    assert action_block["evidence_or_rule"] != "RESOURCE_ORIGIN_UNVERIFIABLE"
