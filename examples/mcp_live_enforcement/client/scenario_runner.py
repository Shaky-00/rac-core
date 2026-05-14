from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from rac_core.models import ResourceMetadata
from rac_core.registry import InMemoryResourceRegistry

from examples.mcp_live_enforcement.client.authorization_event_mapper import AuthorizationEventMapper
from examples.mcp_live_enforcement.client.guarded_client import GuardedMCPClient
from examples.mcp_live_enforcement.client.result_recorder import append_trace, build_summary, write_summary

BASE = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_scenarios() -> list[dict[str, Any]]:
    scenario_dir = BASE / "scenarios"
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(scenario_dir.glob("*.json"))]


async def _open_server(stack: AsyncExitStack, script_name: str, log_path: Path) -> ClientSession:
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(BASE / "servers" / script_name)],
        env={**os.environ, "MCP_SERVER_LOG_PATH": str(log_path)},
    )
    read, write = await stack.enter_async_context(stdio_client(params))
    sess = await stack.enter_async_context(ClientSession(read, write))
    await sess.initialize()
    return sess


async def run_all() -> dict[str, Any]:
    traces_path = BASE / "traces" / "mcp_guarded_trace.jsonl"
    results_path = BASE / "case_outputs" / "mcp_case_study_results.json"
    if traces_path.exists():
        traces_path.unlink()

    grants = {
        "grant_internal_a": _load_json(BASE / "grants" / "grant_internal_a.json"),
        "grant_no_external": _load_json(BASE / "grants" / "grant_no_external.json"),
    }

    mapper = AuthorizationEventMapper(BASE / "manifests" / "tool_manifest.json")
    resource_registry = InMemoryResourceRegistry()
    for item in _load_json(BASE / "resources" / "resource_registry.json").get("resources", []):
        resource_registry.register(
            ResourceMetadata(
                resource_id=item["resource_id"],
                resource_type=item["resource_type"],
                labels=set(item.get("labels", [])),
            )
        )
    guarded_client = GuardedMCPClient(mapper=mapper, resource_registry=resource_registry)

    log_dir = BASE / "traces" / "server_call_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    for p in log_dir.glob("*.jsonl"):
        p.unlink()

    rows: list[dict[str, Any]] = []
    async with AsyncExitStack() as stack:
        sessions = {
            "document_server": await _open_server(stack, "document_server.py", log_dir / "document_server.jsonl"),
            "analysis_server": await _open_server(stack, "analysis_server.py", log_dir / "analysis_server.jsonl"),
            "workspace_server": await _open_server(stack, "workspace_server.py", log_dir / "workspace_server.jsonl"),
            "communication_server": await _open_server(stack, "communication_server.py", log_dir / "communication_server.jsonl"),
        }

        for scenario in _load_scenarios():
            state = guarded_client.build_runtime_state(
                scenario_id=scenario["scenario_id"], grant_id=scenario["grant_id"], grants=grants
            )
            for step in scenario["steps"]:
                row = await guarded_client.guarded_call_tool(
                    scenario_id=scenario["scenario_id"],
                    scenario_type=scenario["scenario_type"],
                    risk_type=scenario["risk_type"],
                    step_id=step["step_id"],
                    server_name=step["server_name"],
                    tool_name=step["tool_name"],
                    arguments=step.get("arguments", {}),
                    expected_should_block=bool(step["expected_should_block"]),
                    expected_label=str(step["expected_label"]),
                    rationale=str(step.get("rationale", "")),
                    server_session=sessions[step["server_name"]],
                    runtime_state=state,
                )
                rows.append(row)
                append_trace(traces_path, row)

    summary = build_summary(rows)
    payload = {"summary": summary, "rows": rows}
    write_summary(results_path, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run scripted MCP-native live enforcement scenarios")
    parser.add_argument("--all", action="store_true", help="Run all scenarios")
    args = parser.parse_args()
    if not args.all:
        raise SystemExit("Use --all to run this case study.")
    outcome = asyncio.run(run_all())
    print(json.dumps(outcome["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
