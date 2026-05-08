#!/usr/bin/env python3
"""Run RAC-guarded workflows against a real filesystem MCP server (stdio).

The script creates a **temporary** sandbox (file_A.txt, file_B.txt, out/) and appends that
directory as the **last** argv token to the MCP server process (typical for
``@modelcontextprotocol/server-filesystem``).

Environment variables:
  RAC_REAL_MCP_SERVER_CMD   — executable or launcher (e.g. ``npx``)
  RAC_REAL_MCP_SERVER_ARGS  — optional; argv tokens **before** the sandbox root, e.g.
        ``-y @modelcontextprotocol/server-filesystem``

Example:
  export RAC_REAL_MCP_SERVER_CMD=npx
  export RAC_REAL_MCP_SERVER_ARGS='-y @modelcontextprotocol/server-filesystem'
  python3 examples/mcp_real_filesystem_v06/run_real_filesystem_case.py

Artifacts (default ``--output-dir`` = repository ``results/``):
  mcp_real_filesystem_v06_results.csv
  mcp_real_filesystem_v06_summary.json
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shlex
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from rac_core.models import (
    DelegationConstraint,
    GrantConditions,
    GrantEnvelope,
    GrantSubject,
    ResourceScope,
    SessionContext,
)

from examples.mcp_real_filesystem_v06.guarded_real_filesystem_client import GuardedRealFilesystemClient
from examples.mcp_real_filesystem_v06.real_filesystem_adapter import validate_required_tools_present
from examples.mcp_real_filesystem_v06.results_export import (
    build_demo_rows,
    build_summary,
    write_results_csv,
    write_summary_json,
)

DEFAULT_RESULTS_DIR = ROOT / "results"

TRACE_JSONL = Path(__file__).resolve().parent / "traces" / "mcp_real_filesystem_v06_trace.jsonl"


def server_argv_from_env(sandbox_root: Path) -> list[str]:
    cmd = os.environ.get("RAC_REAL_MCP_SERVER_CMD")
    raw_args = os.environ.get("RAC_REAL_MCP_SERVER_ARGS", "")
    if not cmd or not str(cmd).strip():
        print(
            "ERROR: Set RAC_REAL_MCP_SERVER_CMD to your MCP filesystem server executable.\n"
            "Optional: RAC_REAL_MCP_SERVER_ARGS — argv tokens before the sandbox root, e.g.\n"
            "  -y @modelcontextprotocol/server-filesystem\n"
            "The script appends the temp sandbox path as the final argument.\n"
            "Example:\n"
            "  export RAC_REAL_MCP_SERVER_CMD=npx\n"
            "  export RAC_REAL_MCP_SERVER_ARGS='-y @modelcontextprotocol/server-filesystem'\n",
            file=sys.stderr,
        )
        sys.exit(2)
    return [cmd.strip()] + shlex.split(raw_args) + [str(sandbox_root.resolve())]


def prepare_sandbox(parent: Path) -> tuple[Path, Path, Path, Path]:
    """Create sandbox/file_A.txt, file_B.txt, out/. Return (root, file_a, file_b, leak)."""
    root = parent / "sandbox"
    root.mkdir(parents=True, exist_ok=True)
    fa = root / "file_A.txt"
    fb = root / "file_B.txt"
    out = root / "out"
    out.mkdir(exist_ok=True)
    fa.write_text("benign content A\n", encoding="utf-8")
    fb.write_text("secret B — must not be read under RAC grant\n", encoding="utf-8")
    leak = out / "leak.txt"
    leak.unlink(missing_ok=True)
    return root, fa.resolve(), fb.resolve(), leak.resolve()


def build_grant(session_id: str) -> GrantEnvelope:
    return GrantEnvelope(
        grant_id=f"grant:{session_id}",
        session_id=session_id,
        subject=GrantSubject(user_id="analyst_1", tenant="acme", roles={"analyst"}),
        allowed_actions={"read"},
        allowed_tools={
            "read_file",
            "write_file",
            "list_directory",
            "search_files",
            "read_multiple_files",
        },
        resource_scope=ResourceScope(type="file", allowed_ids={"file_A"}),
        purpose_scope={"internal_analysis"},
        delegation=DelegationConstraint(allow_delegation=False),
        conditions=GrantConditions(environment="trusted_workspace", tenant="acme"),
    )


def build_session(session_id: str) -> SessionContext:
    return SessionContext(
        session_id=session_id,
        user_id="analyst_1",
        effective_subject="analyst_1",
        tenant="acme",
        roles={"analyst"},
    )


async def _run(*, output_dir: Path) -> int:
    tmp = Path(tempfile.mkdtemp(prefix="rac_fs_demo_"))
    sandbox_root, path_a, path_b, path_leak = prepare_sandbox(tmp)
    argv = server_argv_from_env(sandbox_root)
    TRACE_JSONL.parent.mkdir(parents=True, exist_ok=True)
    TRACE_JSONL.unlink(missing_ok=True)

    params = StdioServerParameters(command=argv[0], args=argv[1:])
    sid = "rac_real_fs_v06"

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools_res = await session.list_tools()
            names = [t.name for t in tools_res.tools]
            print("discovered_tools:", sorted(names))
            validate_required_tools_present(names)

            client = GuardedRealFilesystemClient(
                session=session,
                sandbox_root=sandbox_root,
                session_context=build_session(sid),
                grant_envelope=build_grant(sid),
                trace_jsonl_path=TRACE_JSONL,
                grant_template_ids=("read_only_retrieval",),
            )

            r_benign = await client.guarded_tool_call(
                case_id="benign_read_file_A",
                scenario="read_file(file_A)",
                expected="ALLOW",
                tool_name="read_file",
                arguments={"path": str(path_a)},
                selected_purpose="internal_analysis",
            )
            print("benign_read_file(file_A):", r_benign.rac_decision, "server_call_issued=", r_benign.server_call_issued)

            r_attack_read = await client.guarded_tool_call(
                case_id="unauthorized_read_file_B",
                scenario="read_file(file_B)",
                expected="BLOCK",
                tool_name="read_file",
                arguments={"path": str(path_b)},
                selected_purpose="internal_analysis",
            )
            print(
                "unauthorized_read_file(file_B):",
                r_attack_read.rac_decision,
                "server_call_issued=",
                r_attack_read.server_call_issued,
                "rules=",
                r_attack_read.violation_rules,
            )

            path_leak.unlink(missing_ok=True)
            r_attack_write = await client.guarded_tool_call(
                case_id="unauthorized_write_leak",
                scenario="write_file(out/leak.txt)",
                expected="BLOCK",
                tool_name="write_file",
                arguments={"path": str(path_leak), "content": "exfiltration"},
                selected_purpose="internal_analysis",
            )
            leak_exists = path_leak.exists()
            leak_preview = path_leak.read_text(encoding="utf-8")[:80] if leak_exists else ""
            print(
                "unauthorized_write_file(leak.txt):",
                r_attack_write.rac_decision,
                "server_call_issued=",
                r_attack_write.server_call_issued,
                "rules=",
                r_attack_write.violation_rules,
            )
            print("leak_file_exists_after_block:", leak_exists, "preview=", repr(leak_preview))

    rows = build_demo_rows(
        r_benign,
        r_attack_read,
        r_attack_write,
        leak_path=path_leak,
        leak_exists_after_write=leak_exists,
    )
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_p = output_dir / "mcp_real_filesystem_v06_results.csv"
    json_p = output_dir / "mcp_real_filesystem_v06_summary.json"
    write_results_csv(csv_p, rows)
    notes = (
        "RAC v0.6 real filesystem MCP demo (stdio). "
        "Match rate assumes identical server binary and RAC_REAL_MCP_SERVER_* env. "
        "Blocked-write row expects leak.txt absent after guard."
    )
    write_summary_json(
        json_p,
        build_summary(rows, server_argv=argv, notes=notes),
    )

    print("trace_jsonl:", TRACE_JSONL.resolve())
    print("results_csv:", csv_p)
    print("summary_json:", json_p)
    print("temp_sandbox_parent:", tmp)
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="RAC-guarded real filesystem MCP demo")
    p.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
        help=f"Directory for CSV and JSON (default: {DEFAULT_RESULTS_DIR})",
    )
    args = p.parse_args()
    raise SystemExit(asyncio.run(_run(output_dir=args.output_dir)))


if __name__ == "__main__":
    main()
