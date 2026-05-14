#!/usr/bin/env python3
"""Run deterministic planner JSON plans against the real filesystem MCP server (stdio).

Environment variables (same as ``examples/mcp_real_filesystem_v06/run_real_filesystem_case.py``):
  RAC_REAL_MCP_SERVER_CMD   — e.g. ``npx``
  RAC_REAL_MCP_SERVER_ARGS  — e.g. ``-y @modelcontextprotocol/server-filesystem``

Example:
  export RAC_REAL_MCP_SERVER_CMD=npx
  export RAC_REAL_MCP_SERVER_ARGS='-y @modelcontextprotocol/server-filesystem'
  python3 scripts/run_mcp_real_filesystem_planner_v06.py
  python3 scripts/run_mcp_real_filesystem_planner_v06.py --variants FULL_RAC,NO_RAC

Artifacts (default ``--output-dir`` = repository ``results/``):
  mcp_real_filesystem_planner_v06_results.csv
  mcp_real_filesystem_planner_v06_summary.json

Plans are loaded from ``examples/mcp_real_filesystem_v06/plans/*.json`` (sorted glob), including
hand-authored plans and ``llm_norm_*.json`` after ``normalize_deepseek_planner_plans.py``. Replay
does not call DeepSeek or any LLM API.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from examples.mcp_real_filesystem_v06.planner_runner import cli_entry  # noqa: E402

if __name__ == "__main__":
    cli_entry()
