"""Check consistency across generated artifacts/tables outputs."""

from __future__ import annotations

import json
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from rac_core.validation.benign_fp_traces import build_benign_fp_traces
from rac_core.validation.trace import build_taxonomy_traces


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _csv_data_rows(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return 0
    rows = 0
    for row in csv.DictReader(text.splitlines()):
        if all((v is None) or (str(v).strip() == "") for v in row.values()):
            continue
        rows += 1
    return rows


def _print_result(name: str, ok: bool, detail: str) -> bool:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}: {detail}")
    return ok


def main() -> int:
    out = ROOT / "artifacts" / "tables"
    all_ok = True

    drift = _load_json(out / "drift_taxonomy_summary.json")
    missed = drift.get("missed", drift.get("false_negatives", 0))
    fp = drift.get("fp", drift.get("false_positives", 0))
    all_ok &= _print_result(
        "drift_taxonomy_summary",
        missed == 0 and fp == 0,
        f"missed={missed}, fp={fp}",
    )

    benign = _load_json(out / "benign_fp_summary.json")
    benign_fp = benign.get("false_positives")
    if benign_fp is None:
        # Fallback for current schema: blocked_count equals benign false positives.
        benign_fp = benign.get("blocked_count", 0)
    all_ok &= _print_result(
        "benign_fp_summary",
        benign_fp == 0,
        f"false_positives={benign_fp}",
    )

    stress = _load_json(out / "stress_test_summary.json")
    stress_fp = 0
    if isinstance(stress, list):
        stress_fp = sum(int(item.get("false_positives", 0)) for item in stress)
    elif isinstance(stress, dict):
        stress_fp = int(stress.get("false_positives", 0))
    all_ok &= _print_result(
        "stress_test_summary",
        stress_fp == 0,
        f"false_positives={stress_fp}",
    )

    ablation_path = out / "ablation_summary.json"
    ablation_ok = ablation_path.exists()
    ablation_detail = "missing"
    if ablation_ok:
        ablation = _load_json(ablation_path)
        if isinstance(ablation, list) and ablation:
            required = {"mode", "drift_steps", "blocked_drift", "fn", "fp", "blocking_rate"}
            sample = set(ablation[0].keys())
            ablation_ok = required.issubset(sample)
            ablation_detail = f"fields={sorted(sample)}"
        elif isinstance(ablation, dict):
            required = {"traces", "modes", "rows", "summary"}
            ablation_ok = required.issubset(set(ablation.keys()))
            ablation_detail = f"fields={sorted(ablation.keys())}"
        else:
            ablation_ok = False
            ablation_detail = "unexpected ablation summary format"
    all_ok &= _print_result("ablation_summary", ablation_ok, ablation_detail)

    taxonomy_rows = _csv_data_rows(out / "drift_taxonomy_validation.csv")
    taxonomy_cases = len(build_taxonomy_traces())
    all_ok &= _print_result(
        "taxonomy_rows_vs_cases",
        taxonomy_rows == taxonomy_cases,
        f"rows={taxonomy_rows}, cases={taxonomy_cases}",
    )

    benign_rows = _csv_data_rows(out / "benign_fp_validation.csv")
    benign_cases = len(build_benign_fp_traces())
    all_ok &= _print_result(
        "benign_rows_vs_cases",
        benign_rows == benign_cases,
        f"rows={benign_rows}, cases={benign_cases}",
    )

    stress_rows = _csv_data_rows(out / "stress_test_results.csv")
    oracle_v2 = ROOT / "examples" / "llm_plans" / "stress_test_v2" / "oracle.json"
    oracle_v1 = ROOT / "examples" / "llm_plans" / "stress_test" / "oracle.json"
    oracle = _load_json(oracle_v2 if oracle_v2.exists() else oracle_v1)
    stress_cases = len(oracle)
    all_ok &= _print_result(
        "stress_rows_vs_cases",
        stress_rows == stress_cases,
        f"rows={stress_rows}, cases={stress_cases}",
    )

    if all_ok:
        print("All artifacts consistent.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
