#!/usr/bin/env bash
# Environment smoke check: Python version, editable install, optional TraceBench path.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
_PARENT="$(cd "$ROOT/.." && pwd)"
if [[ -z "${RAC_DATA_DIR:-}" ]]; then
  if [[ -d "$_PARENT/rac-data-review/tracebench/paired" ]]; then
    export RAC_DATA_DIR="$_PARENT/rac-data-review"
  else
    export RAC_DATA_DIR="$_PARENT/rac-data"
  fi
fi
echo "== Repository root: $ROOT"
echo "== RAC_DATA_DIR: $RAC_DATA_DIR"
python3 <<'PY'
import os
import sys
from pathlib import Path

root = Path(os.getcwd())
sys.path.insert(0, str(root / "src"))
print(f"Python: {sys.version.split()[0]} (executable: {sys.executable})")
if sys.version_info < (3, 11):
    print(
        "WARN: Python 3.11+ is required by pyproject.toml; older interpreters are unsupported for artifact review.",
        file=sys.stderr,
    )
try:
    import pydantic  # noqa: F401
    import yaml  # noqa: F401
except ImportError as e:
    raise SystemExit(f"ERROR: missing dependency: {e}") from e
try:
    import rac_core  # noqa: F401
except ImportError as e:
    raise SystemExit(
        f"ERROR: rac_core not importable ({e}). From repo root run: python3 -m pip install -e .\n"
        "If you cannot install yet, ensure PYTHONPATH includes ./src for development-only imports."
    ) from e
print("OK: core imports (pydantic, yaml, rac_core)")
PY

tb="${RAC_TRACEBENCH_ROOT:-}"
if [[ -z "$tb" ]]; then
  for c in \
    "$RAC_DATA_DIR/tracebench/paired" \
    "$RAC_DATA_DIR/tracebench" \
    "$ROOT/data/tracebench/paired"; do
    if [[ -d "$c/controlled_traces/paired" ]] || [[ -d "$c/controlled_traces/core" ]]; then
      tb="$c"
      break
    fi
  done
fi
if [[ -n "$tb" ]] && { [[ -d "$tb/controlled_traces/paired" ]] || [[ -d "$tb/controlled_traces/core" ]]; }; then
  echo "OK: TraceBench data found (override with RAC_TRACEBENCH_ROOT if needed)"
else
  echo "WARN: TraceBench data not found (populate $RAC_DATA_DIR/tracebench/ or set RAC_TRACEBENCH_ROOT; see data/README.md)"
fi
