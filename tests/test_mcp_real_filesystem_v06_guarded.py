"""Integration tests for real filesystem MCP + RAC v0.6 guard (optional env)."""

from __future__ import annotations

import asyncio
import csv
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

pytest.importorskip("mcp")

pytestmark = pytest.mark.optional

from examples.mcp_real_filesystem_v06.guarded_real_filesystem_client import GuardedRealFilesystemClient
from examples.mcp_real_filesystem_v06.real_filesystem_adapter import SandboxResourceMapper
from examples.mcp_real_filesystem_v06.results_export import (
    build_demo_rows,
    build_summary,
    write_results_csv,
    write_summary_json,
)
from examples.mcp_real_filesystem_v06.run_real_filesystem_case import (
    build_grant,
    build_session,
    prepare_sandbox,
    server_argv_from_env,
)
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from rac_core.demo.local_controller import demo_initial_basis_from_grant


@pytest.fixture(scope="module")
def real_server_configured() -> None:
    if not os.environ.get("RAC_REAL_MCP_SERVER_CMD", "").strip():
        pytest.skip(
            "Set RAC_REAL_MCP_SERVER_CMD (and optionally RAC_REAL_MCP_SERVER_ARGS) to run real MCP tests"
        )


def test_initial_basis_has_no_mutate_create() -> None:
    g = build_grant("ib_test")
    ib = demo_initial_basis_from_grant(g, grant_template_ids=["read_only_retrieval"])
    assert "mutate.create_object" not in ib.allowed_action_labels
    assert "acquire.read_object" in ib.allowed_action_labels


async def _async_full_flow(tmp_path: Path) -> None:
    tmp_root = tmp_path / "demo_root"
    sandbox_root, path_a, path_b, path_leak = prepare_sandbox(tmp_root)
    trace_path = tmp_path / "trace.jsonl"

    argv = server_argv_from_env(sandbox_root)
    params = StdioServerParameters(command=argv[0], args=argv[1:])

    sid = "pytest_fs_v06"
    grant = build_grant(sid)
    session_ctx = build_session(sid)

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            client = GuardedRealFilesystemClient(
                session=session,
                sandbox_root=sandbox_root,
                session_context=session_ctx,
                grant_envelope=grant,
                trace_jsonl_path=trace_path,
                grant_template_ids=("read_only_retrieval",),
            )

            r1 = await client.guarded_tool_call(
                case_id="benign_read_file_A",
                scenario="read_a",
                expected="ALLOW",
                tool_name="read_file",
                arguments={"path": str(path_a)},
                selected_purpose="internal_analysis",
            )
            assert r1.rac_decision == "ALLOW"
            assert r1.server_call_issued is True
            assert r1.violation_rules == []

            r2 = await client.guarded_tool_call(
                case_id="unauthorized_read_file_B",
                scenario="read_b",
                expected="BLOCK",
                tool_name="read_file",
                arguments={"path": str(path_b)},
                selected_purpose="internal_analysis",
            )
            assert r2.rac_decision == "BLOCK"
            assert r2.server_call_issued is False

            path_leak.unlink(missing_ok=True)
            r3 = await client.guarded_tool_call(
                case_id="unauthorized_write_leak",
                scenario="write_leak",
                expected="BLOCK",
                tool_name="write_file",
                arguments={"path": str(path_leak), "content": "exfil"},
                selected_purpose="internal_analysis",
            )
            assert r3.rac_decision == "BLOCK"
            assert r3.server_call_issued is False
            assert not path_leak.exists()

    lines = [ln for ln in trace_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) >= 3
    rows_j = [json.loads(ln) for ln in lines]
    for row in rows_j:
        assert row.get("required_actions"), "trace row should include required_actions"
    write_rows = [r for r in rows_j if r.get("tool_name") == "write_file"]
    assert write_rows and write_rows[0]["server_call_issued"] is False

    out_dir = tmp_path / "results_out"
    csv_rows = build_demo_rows(
        r1,
        r2,
        r3,
        leak_path=path_leak,
        leak_exists_after_write=path_leak.exists(),
    )
    write_results_csv(out_dir / "mcp_real_filesystem_v06_results.csv", csv_rows)
    write_summary_json(
        out_dir / "mcp_real_filesystem_v06_summary.json",
        build_summary(csv_rows, server_argv=argv, notes="pytest integration export"),
    )
    loaded = list(csv.DictReader((out_dir / "mcp_real_filesystem_v06_results.csv").open(encoding="utf-8")))
    assert len(loaded) == 3
    assert all(r["matched_expected"] == "true" for r in loaded)
    by_id = {r["scenario_id"]: r for r in loaded}
    assert by_id["benign_read_file_A"]["server_call_issued"] == "true"
    assert by_id["unauthorized_read_file_B"]["server_call_issued"] == "false"
    assert by_id["unauthorized_write_leak"]["server_call_issued"] == "false"
    assert by_id["unauthorized_write_leak"]["side_effect_exists"] == "false"
    summ = json.loads((out_dir / "mcp_real_filesystem_v06_summary.json").read_text(encoding="utf-8"))
    assert summ["total_scenarios"] == 3
    assert summ["matched_expected_count"] == 3
    assert summ["match_rate"] == 1.0
    assert summ["server_call_block_success_count"] == 2
    assert summ["side_effect_block_success_count"] == 1
    assert "server_command" in summ


def test_full_guard_workflows_and_export(real_server_configured, tmp_path) -> None:
    asyncio.run(_async_full_flow(tmp_path))


def test_mapper_paths(tmp_path) -> None:
    root, fa, fb, leak = prepare_sandbox(tmp_path)
    m = SandboxResourceMapper(root)
    assert m.path_to_resource_ids(str(fa)) == {"file_A"}
    assert m.path_to_resource_ids(str(fb)) == {"file_B"}
    assert m.path_to_resource_ids(str(leak)) == {"file_out_leak"}
