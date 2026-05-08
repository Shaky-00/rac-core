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

SERVER = Server("document_server")


def _log_call(tool_name: str, arguments: dict[str, Any]) -> None:
    log_path = os.environ.get("MCP_SERVER_LOG_PATH")
    if not log_path:
        return
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "server": "document_server",
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
            name="read_report",
            description="Read a report by resource id",
            inputSchema={
                "type": "object",
                "properties": {"report_id": {"type": "string"}},
                "required": ["report_id"],
            },
        ),
        Tool(
            name="search_reports",
            description="Search report index",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "search_space_resource": {"type": "string"},
                },
                "required": ["query"],
            },
        ),
    ]


@SERVER.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    _log_call(name, arguments)
    if name == "read_report":
        report_id = str(arguments.get("report_id", ""))
        return _text(
            {
                "status": "ok",
                "artifact_id": f"artifact:read:{report_id}",
                "resources": [report_id],
                "output_type": "report_content",
                "content": f"content::{report_id}",
            }
        )
    if name == "search_reports":
        scope = str(arguments.get("search_space_resource") or "res:index:reports")
        query = str(arguments.get("query", ""))
        results = ["res:report:A"] if "related" in query else ["res:report:A"]
        return _text(
            {
                "status": "ok",
                "artifact_id": f"artifact:search:{abs(hash(query)) % 10000}",
                "resources": [scope],
                "output_type": "search_results",
                "results": results,
            }
        )
    raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await SERVER.run(read_stream, write_stream, SERVER.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
