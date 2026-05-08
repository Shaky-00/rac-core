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

SERVER = Server("communication_server")


def _log_call(tool_name: str, arguments: dict[str, Any]) -> None:
    log_path = os.environ.get("MCP_SERVER_LOG_PATH")
    if not log_path:
        return
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "server": "communication_server",
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
            name="send_email",
            description="Send external email",
            inputSchema={
                "type": "object",
                "properties": {
                    "recipient": {"type": "string"},
                    "summary_id": {"type": "string"},
                    "report_id": {"type": "string"},
                },
                "required": ["recipient"],
            },
        )
    ]


@SERVER.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    _log_call(name, arguments)
    if name == "send_email":
        recipient = str(arguments.get("recipient", ""))
        return _text(
            {
                "status": "ok",
                "message_id": f"msg::{recipient}",
                "resources": [recipient],
                "output_type": "external_send",
            }
        )
    raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await SERVER.run(read_stream, write_stream, SERVER.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
