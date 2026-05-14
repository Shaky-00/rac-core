#!/usr/bin/env python3
"""Launcher for examples/mcp_real_filesystem_v06/run_real_filesystem_case.py."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.mcp_real_filesystem_v06.run_real_filesystem_case import main

if __name__ == "__main__":
    main()
