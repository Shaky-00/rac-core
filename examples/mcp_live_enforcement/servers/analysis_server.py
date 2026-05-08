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

SERVER = Server("analysis_server")


def _log_call(tool_name: str, arguments: dict[str, Any]) -> None:
    log_path = os.environ.get("MCP_SERVER_LOG_PATH")
    if not log_path:
        return
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "server": "analysis_server",
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
            name="summarize_report",
            description="Summarize report or artifact",
            inputSchema={
                "type": "object",
                "properties": {
                    "report_id": {"type": "string"},
                    "artifact_id": {"type": "string"},
                },
            },
        ),
        Tool(
            name="extract_metrics",
            description="Extract metrics from summary",
            inputSchema={
                "type": "object",
                "properties": {"summary_id": {"type": "string"}},
                "required": ["summary_id"],
            },
        ),
        Tool(
            name="compare_reports",
            description="Compare two reports",
            inputSchema={
                "type": "object",
                "properties": {
                    "left_report_id": {"type": "string"},
                    "right_report_id": {"type": "string"},
                },
                "required": ["left_report_id", "right_report_id"],
            },
        ),
    ]


@SERVER.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    _log_call(name, arguments)
    if name == "summarize_report":
        seed = str(arguments.get("artifact_id") or arguments.get("report_id") or "none")
        return _text(
            {
                "status": "ok",
                "artifact_id": f"artifact:summary:{seed}",
                "resources": [],
                "output_type": "summary",
                "summary": f"summary::{seed}",
            }
        )
    if name == "extract_metrics":
        summary_id = str(arguments.get("summary_id", ""))
        return _text(
            {
                "status": "ok",
                "artifact_id": f"artifact:metrics:{summary_id}",
                "resources": [],
                "output_type": "metrics",
                "metrics": {"kpi": 42},
            }
        )
    if name == "compare_reports":
        left = str(arguments.get("left_report_id", ""))
        right = str(arguments.get("right_report_id", ""))
        return _text(
            {
                "status": "ok",
                "artifact_id": f"artifact:compare:{left}:{right}",
                "resources": [left, right],
                "output_type": "comparison",
            }
        )
    raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await SERVER.run(read_stream, write_stream, SERVER.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
