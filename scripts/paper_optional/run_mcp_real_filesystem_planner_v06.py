#!/usr/bin/env python3
"""Run deterministic planner JSON plans against the real filesystem MCP server (stdio).

Environment variables (same as ``examples/mcp_real_filesystem_v06/run_real_filesystem_case.py``):
  RAC_REAL_MCP_SERVER_CMD   — e.g. ``npx``
  RAC_REAL_MCP_SERVER_ARGS  — e.g. ``-y @modelcontextprotocol/server-filesystem``

Example:
  export RAC_REAL_MCP_SERVER_CMD=npx
  export RAC_REAL_MCP_SERVER_ARGS='-y @modelcontextprotocol/server-filesystem'
  python3 scripts/paper_optional/run_mcp_real_filesystem_planner_v06.py
  python3 scripts/paper_optional/run_mcp_real_filesystem_planner_v06.py --variants FULL_RAC,NO_RAC

Artifacts (default ``--output-dir`` = ``artifacts/results/`` under the repository root):
  mcp_real_filesystem_planner_v06_results.csv
  mcp_real_filesystem_planner_v06_summary.json

Plans are loaded from ``examples/mcp_real_filesystem_v06/plans/*.json`` (sorted glob), including
hand-authored plans and normalized ``llm_norm_*.json`` replay fixtures. This path does not call any hosted LLM API.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from examples.mcp_real_filesystem_v06.planner_runner import cli_entry  # noqa: E402

if __name__ == "__main__":
    cli_entry()
