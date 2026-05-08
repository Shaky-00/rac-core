from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

SERVER = Server("workspace_server")


def _log_call(tool_name: str, arguments: dict[str, Any]) -> None:
    log_path = os.environ.get("MCP_SERVER_LOG_PATH")
    if not log_path:
        return
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "server": "workspace_server",
        "tool_name": tool_name,
        "arguments": arguments,
    }
    p = Path(log_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _text(payload: dict[str, Any]) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]


@SERVER.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="create_internal_report",
            description="Create an internal report artifact",
            inputSchema={
                "type": "object",
                "properties": {
                    "summary_id": {"type": "string"},
                    "metrics_id": {"type": "string"},
                },
            },
        ),
        Tool(
            name="save_internal_report",
            description="Persist internal report",
            inputSchema={
                "type": "object",
                "properties": {"report_id": {"type": "string"}},
                "required": ["report_id"],
            },
        ),
    ]


@SERVER.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    _log_call(name, arguments)
    if name == "create_internal_report":
        seed = str(arguments.get("metrics_id") or arguments.get("summary_id") or "none")
        return _text(
            {
                "status": "ok",
                "artifact_id": f"artifact:internal_report:{seed}",
                "resources": [],
                "output_type": "internal_report",
            }
        )
    if name == "save_internal_report":
        report_id = str(arguments.get("report_id", ""))
        return _text(
            {
                "status": "ok",
                "saved": True,
                "resources": [],
                "output_type": "save_receipt",
                "report_id": report_id,
            }
        )
    raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await SERVER.run(read_stream, write_stream, SERVER.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
