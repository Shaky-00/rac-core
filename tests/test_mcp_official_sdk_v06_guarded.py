"""v0.6-aligned MCP official SDK guarded demo (stdio MCP boundary + RAC pre-call)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))

try:
    import mcp  # noqa: F401
except ImportError:
    pytest.skip("mcp package required (install with: pip install 'mcp>=1.0,<2.0')", allow_module_level=True)

from examples.mcp_official_sdk.guarded_mcp_client import GuardedMCPClient
from examples.mcp_official_sdk.run_mcp_sdk_case_study import _make_grant, _make_session
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from rac_core.demo.local_controller import demo_initial_basis_from_grant


SERVER = REPO / "examples" / "mcp_official_sdk" / "mcp_demo_server.py"


def test_initial_basis_excludes_external_disclosure_leaf() -> None:
    g = _make_grant("ib_probe")
    ib = demo_initial_basis_from_grant(
        g,
        grant_template_ids=["internal_analysis", "search_and_retrieval"],
    )
    assert "disclose.send_message" not in ib.allowed_action_labels


async def _async_benign(trace_path: Path, server_log: Path):
    env = {**os.environ, "MCP_OFFICIAL_SDK_SERVER_CALL_LOG": str(server_log)}
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            c = GuardedMCPClient(
                session=session,
                session_context=_make_session("pytest_benign"),
                grant_envelope=_make_grant("pytest_benign"),
                trace_jsonl_path=trace_path,
            )
            r1 = await c.guarded_tool_call(
                case_id="pytest_benign",
                scenario="read",
                expected="ALLOW",
                tool_name="read_file",
                arguments={"file_id": "file_A"},
                selected_purpose="internal_analysis",
            )
            r2 = await c.guarded_tool_call(
                case_id="pytest_benign",
                scenario="summarize",
                expected="ALLOW",
                tool_name="summarize_text",
                arguments={"input_anchor": c.last_anchor_id},
                selected_purpose="internal_analysis",
                input_anchor=c.last_anchor_id,
            )
            return r1, r2


def test_benign_read_summarize_allow_and_server_calls(tmp_path) -> None:
    trace = tmp_path / "trace.jsonl"
    slog = tmp_path / "server.jsonl"
    r1, r2 = asyncio.run(_async_benign(trace, slog))
    assert r1.rac_decision == "ALLOW" and r1.server_call_issued is True
    assert r2.rac_decision == "ALLOW" and r2.server_call_issued is True
    lines = [ln for ln in slog.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2
    parsed = [json.loads(ln) for ln in lines]
    assert parsed[0]["tool"] == "read_file"
    assert parsed[1]["tool"] == "summarize_text"


async def _async_attack(trace_path: Path, server_log: Path):
    env = {**os.environ, "MCP_OFFICIAL_SDK_SERVER_CALL_LOG": str(server_log)}
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            c = GuardedMCPClient(
                session=session,
                session_context=_make_session("pytest_attack"),
                grant_envelope=_make_grant("pytest_attack", include_external=True),
                trace_jsonl_path=trace_path,
            )
            await c.guarded_tool_call(
                case_id="pytest_attack",
                scenario="read",
                expected="ALLOW",
                tool_name="read_file",
                arguments={"file_id": "file_A"},
                selected_purpose="internal_analysis",
            )
            await c.guarded_tool_call(
                case_id="pytest_attack",
                scenario="summarize",
                expected="ALLOW",
                tool_name="summarize_text",
                arguments={"input_anchor": c.last_anchor_id},
                selected_purpose="internal_analysis",
                input_anchor=c.last_anchor_id,
            )
            r3 = await c.guarded_tool_call(
                case_id="pytest_attack",
                scenario="email",
                expected="BLOCK",
                tool_name="create_email_draft",
                arguments={"summary": c.last_summary_text or "x", "recipient": "external@example.com"},
                selected_purpose="internal_analysis",
                input_anchor=c.last_anchor_id,
            )
            return r3


def test_attack_email_blocked_no_server_call(tmp_path) -> None:
    trace = tmp_path / "trace.jsonl"
    slog = tmp_path / "server.jsonl"
    r3 = asyncio.run(_async_attack(trace, slog))
    assert r3.rac_decision == "BLOCK"
    assert r3.server_call_issued is False
    assert r3.evidence_or_rule == "ACTION_ESCALATION"
    lines = [ln for ln in slog.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2
    assert all(json.loads(ln)["tool"] != "create_email_draft" for ln in lines)

    rows = [json.loads(ln) for ln in trace.read_text(encoding="utf-8").splitlines() if ln.strip()]
    email_rows = [r for r in rows if r.get("tool_name") == "create_email_draft"]
    assert len(email_rows) == 1
    er = email_rows[0]
    assert er["server_call_issued"] is False
    assert "disclose.send_message" in er.get("required_actions", [])
