#!/usr/bin/env python3
"""Normalize DeepSeek raw planner envelopes into replay-ready JSON under ``plans/``.

By default, ``fixture_*.json`` files under ``raw_outputs/`` are **skipped** so the final
replay corpus uses only real API envelopes. Use ``--include-fixtures`` for CI/dev when
fixtures must be normalized.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.mcp_real_filesystem_v06.llm_generation.plan_normalization import (  # noqa: E402
    extract_plan_from_raw_envelope,
    normalize_plan_dict,
    strip_runner_only_plan,
    validate_plan_with_temp_sandbox,
)

DEFAULT_GEN = ROOT / "examples/mcp_real_filesystem_v06/llm_generation"
DEFAULT_PLANS = ROOT / "examples/mcp_real_filesystem_v06/plans"
REPORT_NAME = "normalization_report.json"


def _is_fixture_raw(path: Path) -> bool:
    return path.name.startswith("fixture_") and path.suffix == ".json"


def _clean_llm_norm_outputs(norm_dir: Path, plans_dir: Path) -> tuple[int, int]:
    """Remove ``llm_norm_*.json`` from staging and replay dirs. Returns (norm_removed, plans_removed)."""
    n_norm = 0
    n_plans = 0
    if norm_dir.exists():
        for p in norm_dir.glob("llm_norm_*.json"):
            p.unlink(missing_ok=True)
            n_norm += 1
    if plans_dir.exists():
        for p in plans_dir.glob("llm_norm_*.json"):
            p.unlink(missing_ok=True)
            n_plans += 1
    return n_norm, n_plans


def _scenario_id_from_envelope(path: Path, envelope: dict) -> str | None:
    audit = envelope.get("audit") or {}
    sid = audit.get("scenario_id")
    if isinstance(sid, str) and sid.strip():
        return sid.strip()
    return None


def _choose_winning_raw(
    paths: list[Path],
    *,
    include_fixtures: bool,
) -> tuple[Path, list[Path]]:
    """Prefer real API files over fixtures; among API files pick lexicographically greatest name (newest timestamp prefix)."""
    if not paths:
        raise ValueError("empty path group")
    api = [p for p in paths if not _is_fixture_raw(p)]
    fixture_only = [p for p in paths if _is_fixture_raw(p)]
    if api:
        chosen = max(api, key=lambda p: p.name)
        dropped = [p for p in paths if p != chosen]
        return chosen, dropped
    if include_fixtures and fixture_only:
        chosen = max(fixture_only, key=lambda p: p.name)
        dropped = [p for p in paths if p != chosen]
        return chosen, dropped
    # only fixtures but include_fixtures False — should not call
    raise ValueError("no API raw file for scenario and fixtures not included")


def main() -> int:
    p = argparse.ArgumentParser(description="Normalize DeepSeek raw JSON into llm_norm_*.json plans.")
    p.add_argument("--raw-dir", type=Path, default=None, help="Directory containing raw envelope JSON files.")
    p.add_argument(
        "--normalized-dir",
        type=Path,
        default=None,
        help="Staging directory for normalized plans (default: <llm_generation>/normalized_plans).",
    )
    p.add_argument(
        "--plans-dir",
        type=Path,
        default=DEFAULT_PLANS,
        help="Final plans directory for planner_runner (default: examples/mcp_real_filesystem_v06/plans).",
    )
    p.add_argument(
        "--report",
        type=Path,
        default=None,
        help=f"Report JSON path (default: <llm_generation>/reports/{REPORT_NAME}).",
    )
    p.add_argument(
        "--include-fixtures",
        action="store_true",
        help="Also normalize fixture_*.json (default: skip fixtures; use only real API outputs).",
    )
    p.add_argument(
        "--clean-output",
        action="store_true",
        help="Delete existing llm_norm_*.json under normalized-dir and plans-dir before writing.",
    )
    args = p.parse_args()

    gen_base = DEFAULT_GEN
    raw_dir = (args.raw_dir or (gen_base / "raw_outputs")).resolve()
    norm_dir = (args.normalized_dir or (gen_base / "normalized_plans")).resolve()
    plans_dir = args.plans_dir.resolve()
    report_path = (args.report or (gen_base / "reports" / REPORT_NAME)).resolve()

    norm_dir.mkdir(parents=True, exist_ok=True)
    plans_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    all_json = sorted(
        p for p in raw_dir.glob("*.json") if p.name != REPORT_NAME and not p.name.startswith(".")
    )
    fixture_paths = [p for p in all_json if _is_fixture_raw(p)]
    api_paths = [p for p in all_json if not _is_fixture_raw(p)]
    fixture_outputs_seen = len(fixture_paths)

    skipped_fixtures: list[str] = []
    if not args.include_fixtures:
        for fp in fixture_paths:
            skipped_fixtures.append(fp.name)

    # Build candidate list for grouping (API always; fixtures only if flag)
    scan_paths: list[Path] = list(api_paths)
    if args.include_fixtures:
        scan_paths.extend(fixture_paths)

    # Group by scenario_id
    groups: dict[str, list[Path]] = defaultdict(list)
    rejected_pre: list[dict] = []
    for path in scan_paths:
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            rejected_pre.append({"file": path.name, "reason": f"invalid JSON: {e}"})
            continue
        sid = _scenario_id_from_envelope(path, envelope)
        if not sid:
            rejected_pre.append({"file": path.name, "reason": "missing audit.scenario_id"})
            continue
        groups[sid].append(path)

    duplicate_plan_ids: list[dict[str, object]] = []
    selected_files: list[Path] = []
    for sid, gpaths in sorted(groups.items()):
        if len(gpaths) > 1:
            try:
                chosen, dropped = _choose_winning_raw(gpaths, include_fixtures=args.include_fixtures)
            except ValueError as exc:
                rejected_pre.append(
                    {"scenario_id": sid, "reason": str(exc), "files": [p.name for p in gpaths]}
                )
                continue
            duplicate_plan_ids.append(
                {
                    "scenario_id": sid,
                    "selected_source_raw_file": chosen.name,
                    "dropped_raw_files": [d.name for d in dropped],
                }
            )
            selected_files.append(chosen)
        else:
            selected_files.append(gpaths[0])

    real_api_raw_files_in_directory = len(api_paths)
    real_api_outputs_processed = sum(1 for p in selected_files if not _is_fixture_raw(p))
    fixture_outputs_processed = 0
    if args.include_fixtures:
        fixture_outputs_processed = sum(1 for p in selected_files if _is_fixture_raw(p))

    if args.clean_output:
        _clean_llm_norm_outputs(norm_dir, plans_dir)

    per_plan: list[dict] = []
    rejected: list[dict] = []
    all_fixes: list[str] = []
    manual_semantic_any = False
    allow_block: Counter[str] = Counter()

    for path in sorted(selected_files, key=lambda p: p.name):
        envelope = json.loads(path.read_text(encoding="utf-8"))
        audit = envelope.get("audit") or {}
        sid = audit.get("scenario_id") or envelope.get("scenario_id")
        if not isinstance(sid, str) or not sid:
            rejected.append({"file": path.name, "reason": "missing scenario_id in audit"})
            continue

        candidate = extract_plan_from_raw_envelope(envelope)
        if candidate is None:
            rejected.append({"file": path.name, "reason": "could not parse JSON plan from envelope"})
            continue

        manual_sem = bool(audit.get("manual_semantic_edit") or envelope.get("manual_semantic_edit"))
        manual_semantic_any = manual_semantic_any or manual_sem
        normalized, fixes, manual_flag = normalize_plan_dict(candidate, scenario_id=sid, manual_semantic_edit=manual_sem)
        manual_semantic_any = manual_semantic_any or manual_flag
        all_fixes.extend(fixes)

        errs = validate_plan_with_temp_sandbox(normalized)
        if errs:
            rejected.append({"file": path.name, "plan_id": normalized.get("plan_id"), "reasons": errs})
            continue

        stripped = strip_runner_only_plan(normalized)
        out_name = f"llm_norm_{sid}.json"
        norm_out = norm_dir / out_name
        plan_out = plans_dir / out_name
        text = json.dumps(stripped, indent=2, ensure_ascii=False) + "\n"
        norm_out.write_text(text, encoding="utf-8")
        shutil.copy2(norm_out, plan_out)

        for st in stripped["steps"]:
            allow_block[str(st.get("expected_decision"))] += 1

        per_plan.append(
            {
                "plan_id": stripped["plan_id"],
                "selected_source_raw_file": path.name,
                "step_count": len(stripped["steps"]),
                "allow_count": sum(1 for s in stripped["steps"] if s["expected_decision"] == "ALLOW"),
                "block_count": sum(1 for s in stripped["steps"] if s["expected_decision"] == "BLOCK"),
                "auto_fixes": fixes,
                "manual_semantic_edit": manual_sem or manual_flag,
            }
        )

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    report = {
        "generated_at": now,
        "total_raw_outputs": len(all_json),
        "fixture_outputs_seen": fixture_outputs_seen,
        "fixture_outputs_skipped": len(skipped_fixtures),
        "fixture_outputs_skipped_files": skipped_fixtures,
        "real_api_raw_files_in_directory": real_api_raw_files_in_directory,
        "real_api_outputs_processed": real_api_outputs_processed,
        "include_fixtures": bool(args.include_fixtures),
        "fixture_outputs_processed_in_run": fixture_outputs_processed,
        "normalized_plan_output_dir": str(norm_dir),
        "replay_plan_output_dir": str(plans_dir),
        "duplicate_plan_ids": duplicate_plan_ids,
        "valid_normalized_plans": len(per_plan),
        "rejected_plans": len(rejected) + len(rejected_pre),
        "rejection_details": rejected_pre + rejected,
        "per_plan": per_plan,
        "expected_decision_distribution": dict(allow_block),
        "manual_edit_required": bool(all_fixes),
        "manual_semantic_edit": manual_semantic_any,
        "auto_fix_notes": all_fixes,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"normalized={len(per_plan)} rejected={len(rejected)+len(rejected_pre)} "
        f"fixtures_skipped={len(skipped_fixtures)} report={report_path}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
