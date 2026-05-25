#!/usr/bin/env python3
"""Sanity checks for RQ2 TraceBench-Expanded replay outputs."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from rac_core.validation.rac_tracebench_experiment import (  # noqa: E402
    build_experiment_rows,
    resolve_tracebench_root,
    tracebench_variant_plan,
)


def run_sanity(
    *,
    root: Path,
    summary_path: Path | None = None,
    rows: list[dict] | None = None,
    summary: dict | None = None,
) -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    if summary is None and summary_path:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if rows is None:
        rows, summary = build_experiment_rows(
            root=root,
            variant_plan=tracebench_variant_plan("rq2_full"),
            suite="expanded",
            include_mixed=True,
            include_rq2_overlay=True,
        )

    assert summary is not None
    st_counts = summary.get("scenario_type_counts") or {}
    composite_n = int(st_counts.get("composite_drift", 0))
    multi_fam = int(summary.get("block_workflows_with_multiple_violation_families", 0))

    if composite_n <= 0:
        errors.append("composite_drift BLOCK workflow count must be > 0")
    if multi_fam <= 0:
        errors.append("expected some BLOCK workflows with len(violation_families) >= 2")

    full_mismatches = [
        r
        for r in rows
        if r["variant"] == "FULL_RAC" and r.get("matched_oracle") == "false"
    ]
    if full_mismatches:
        for r in full_mismatches[:20]:
            errors.append(
                f"FULL_RAC oracle mismatch: workflow_id={r.get('workflow_id')} "
                f"oracle={r.get('oracle_label')} replay={r.get('replay_decision')}"
            )
        if len(full_mismatches) > 20:
            errors.append(f"... and {len(full_mismatches) - 20} more FULL_RAC mismatches")

    diag = summary.get("component_diagnostic_flips") or []
    fam_counts = Counter()
    for r in rows:
        if r["variant"] != "FULL_RAC":
            continue
        if r.get("oracle_label") != "BLOCK":
            continue
        try:
            vf = json.loads(str(r.get("violation_families", "[]")))
        except json.JSONDecodeError:
            vf = []
        if isinstance(vf, list) and len(vf) == 1:
            fam_counts[vf[0]] += 1

    for mode, label in [
        ("RAC_WITHOUT_ACTION", "action_escalation"),
        ("RAC_WITHOUT_RESOURCE_ORIGIN", "resource_drift"),
        ("RAC_WITHOUT_PURPOSE", "purpose_drift"),
        ("RAC_WITHOUT_LINEAGE", "lineage_violation"),
        ("RAC_WITHOUT_OUTPUT_ANCHOR", "output_anchor_violation"),
        ("RAC_WITHOUT_CONDITION", "condition_weakening"),
        ("RAC_WITHOUT_DELEGATION", "delegation_amplification"),
    ]:
        missed = int((summary.get("missed_block_by_variant") or {}).get(mode, {}).get("missed_block_count", 0))
        fam_total = int(fam_counts.get(label, 0))
        if fam_total > 0 and missed == fam_total:
            warnings.append(
                f"diagnostic {mode} missed_block_count ({missed}) equals single-family "
                f"BLOCK count for {label} ({fam_total}) — check composite coverage"
            )

    report = {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "composite_drift_count": composite_n,
        "multi_family_block_count": multi_fam,
        "full_rac_mismatch_count": len(full_mismatches),
        "component_diagnostic_flip_count": len(diag),
    }
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=None)
    ap.add_argument(
        "--summary",
        type=Path,
        default=ROOT / "artifacts/results/v1_expanded_rq2/rac_tracebench_v1_expanded_rq2_summary.json",
    )
    args = ap.parse_args()
    root = resolve_tracebench_root(args.root)
    if root is None:
        print("ERROR: TraceBench root not found", file=sys.stderr)
        return 2
    report = run_sanity(root=root, summary_path=args.summary.expanduser().resolve())
    print(json.dumps(report, indent=2))
    if report["warnings"]:
        for w in report["warnings"]:
            print(f"WARNING: {w}", file=sys.stderr)
    if not report["ok"]:
        for e in report["errors"]:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
