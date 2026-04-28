from __future__ import annotations

import asyncio
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

RESOURCES: dict[str, dict[str, str]] = {
    "file_A": {
        "tenant": "acme",
        "purpose": "internal_summary",
        "content": "Q2 finance highlights for acme internal review.",
    },
    "file_B": {
        "tenant": "acme",
        "purpose": "other",
        "content": "Partner notes and external-facing draft fragments.",
    },
    "file_C": {
        "tenant": "other",
        "purpose": "internal_summary",
        "content": "Other tenant confidential planning notes.",
    },
}

SERVER = Server("rac-mcp-official-sdk-demo")


def _as_text(payload: dict[str, Any]) -> list[TextContent]:
    return [TextContent(type="text", text=str(payload))]


@SERVER.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="read_file",
            description="Read a simulated file by id.",
            inputSchema={
                "type": "object",
                "properties": {"file_id": {"type": "string"}},
                "required": ["file_id"],
            },
        ),
        Tool(
            name="search_documents",
            description="Search and return matching simulated resource IDs.",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        ),
        Tool(
            name="summarize_text",
            description="Return a deterministic summary from content or anchor.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "input_anchor": {"type": "string"},
                },
            },
        ),
        Tool(
            name="create_email_draft",
            description="Create an email draft (simulated external release action).",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "summary": {"type": "string"},
                    "recipient": {"type": "string"},
                },
                "required": ["recipient"],
            },
        ),
    ]


@SERVER.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "read_file":
        file_id = str(arguments["file_id"])
        if file_id not in RESOURCES:
            raise ValueError(f"Unknown file_id: {file_id}")
        record = RESOURCES[file_id]
        return _as_text(
            {
                "tool": "read_file",
                "file_id": file_id,
                "tenant": record["tenant"],
                "purpose": record["purpose"],
                "content": record["content"],
            }
        )

    if name == "search_documents":
        query = str(arguments.get("query", "")).lower()
        if "q2" in query:
            results = ["file_A"]
        elif "acme" in query:
            results = ["file_A", "file_B"]
        else:
            results = ["file_B"]
        return _as_text({"tool": "search_documents", "query": query, "results": results})

    if name == "summarize_text":
        raw = str(arguments.get("content") or arguments.get("input_anchor") or "empty")
        return _as_text({"tool": "summarize_text", "summary": f"summary::{raw[:48]}"})

    if name == "create_email_draft":
        recipient = str(arguments["recipient"])
        text = str(arguments.get("summary") or arguments.get("content") or "")
        return _as_text(
            {
                "tool": "create_email_draft",
                "draft_id": f"draft::{recipient}",
                "recipient": recipient,
                "preview": text[:80],
            }
        )

    raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await SERVER.run(read_stream, write_stream, SERVER.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
