"""Static replay + ablation sweep for RAC-TraceBench v0.6 (CSV / JSON summaries)."""

from __future__ import annotations

import csv
import json
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rac_core.action_semantics.registry import ActionSemanticsRegistry
from rac_core.action_semantics.taxonomy import default_semantics_yaml_path
from rac_core.checker import RACPreCommitChecker
from rac_core.models import DecisionType
from rac_core.store import InMemoryBasisStore, InMemoryCausalLineageStore
from rac_core.validation.ablation import AblationMode, AblationRunner, AblationTraceResult
from rac_core.validation.rac_tracebench_loader import (
    convert_trace_case_to_controlled_trace,
    load_rac_tracebench,
    oracle_label_by_trace_id,
    resolve_rac_tracebench_root,
)


def resolve_tracebench_root(explicit: Path | None = None) -> Path | None:
    if explicit is not None:
        p = explicit.expanduser().resolve()
        return p if (p / "controlled_traces" / "paired").is_dir() else None
    env = os.environ.get("RAC_TRACEBENCH_ROOT")
    if env:
        p = Path(env).expanduser().resolve()
        if (p / "controlled_traces" / "paired").is_dir():
            return p
    r = resolve_rac_tracebench_root()
    if r is not None:
        return r
    fallback = Path("/root/projects/mcp_data/rac_tracebench_v06")
    return fallback if (fallback / "controlled_traces" / "paired").is_dir() else None


def default_variant_plan() -> list[tuple[str, AblationMode]]:
    """(CSV label, :class:`AblationMode`) — all variants share :class:`AblationRunner` replay pipeline."""
    return [
        ("FULL_RAC", AblationMode.FULL_RAC),
        ("NO_RAC", AblationMode.NO_RAC),
        ("ENTRY_ONLY", AblationMode.ENTRY_ONLY_CHECK),
        ("STATIC_TOOL_ALLOWLIST", AblationMode.STATIC_TOOL_ALLOWLIST),
        ("HistoryAware", AblationMode.HISTORY_AWARE_SCOPE),
        ("Static+History", AblationMode.STATIC_HISTORY_AWARE),
        ("RAC_WITHOUT_ACTION", AblationMode.RAC_WITHOUT_ACTION),
        ("RAC_WITHOUT_RESOURCE_ORIGIN", AblationMode.RAC_WITHOUT_RESOURCE_ORIGIN),
        ("RAC_WITHOUT_OUTPUT_ANCHOR", AblationMode.RAC_WITHOUT_ANCHOR),
        ("RAC_WITHOUT_LINEAGE", AblationMode.RAC_WITHOUT_LINEAGE),
        ("RAC_WITHOUT_PURPOSE", AblationMode.RAC_WITHOUT_PURPOSE),
        ("RAC_WITHOUT_CONDITION", AblationMode.RAC_WITHOUT_CONDITIONS),
        ("RAC_WITHOUT_DELEGATION", AblationMode.RAC_WITHOUT_DELEGATION),
    ]


def _checker_factory() -> RACPreCommitChecker:
    return RACPreCommitChecker(
        lineage_store=InMemoryCausalLineageStore(),
        basis_store=InMemoryBasisStore(),
        action_semantics_registry=ActionSemanticsRegistry.load_from_yaml(
            default_semantics_yaml_path()
        ),
    )


def _final_decision_ablation(r: AblationTraceResult) -> DecisionType:
    return r.step_results[-1].observed_decision


def _blocking_step_ablation(r: AblationTraceResult) -> str | None:
    return r.blocked_at_step


def _rules_ablation(r: AblationTraceResult) -> list[str]:
    for sr in r.step_results:
        if sr.observed_decision == DecisionType.BLOCK:
            return list(sr.observed_rules)
    return []


def _decision_reason_from_ablation_result(r: AblationTraceResult) -> str:
    parts: list[str] = []
    for sr in r.step_results:
        if sr.observed_decision == DecisionType.BLOCK:
            m = sr.metadata
            vr = m.get("violation_reasons")
            if isinstance(vr, str) and vr.strip():
                parts.append(vr.strip())
            oa = m.get("output_anchor_integrity_check")
            if oa:
                parts.append(f"output_anchor_integrity_check={oa}")
            bl = m.get("baseline")
            if bl:
                parts.append(f"baseline={bl}")
            break
    last = r.step_results[-1]
    m = last.metadata
    if not parts:
        oa = m.get("output_anchor_integrity_check")
        if oa:
            parts.append(f"output_anchor_integrity_check={oa}")
        bl = m.get("baseline")
        if bl:
            parts.append(f"baseline={bl}")
    return "; ".join(parts)


def run_trace_variant(
    trace,
    *,
    variant: str,
    mode: AblationMode,
) -> tuple[DecisionType, str | None, list[str], str, float]:
    t0 = time.perf_counter()
    ab = AblationRunner(_checker_factory)
    result = ab.run_trace(trace, mode)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    rules = _rules_ablation(result)
    reason = _decision_reason_from_ablation_result(result)
    return (
        _final_decision_ablation(result),
        _blocking_step_ablation(result),
        rules,
        reason,
        elapsed_ms,
    )


def build_experiment_rows(
    *,
    root: Path,
    variant_plan: list[tuple[str, AblationMode]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    bundle = load_rac_tracebench(root)
    cases = bundle["traces"]
    oracle_doc = bundle["oracle_labels"]
    by_oracle = oracle_label_by_trace_id(oracle_doc)
    plan = variant_plan or default_variant_plan()

    rows: list[dict[str, Any]] = []

    for case in cases:
        trace_id = str(case["trace_id"])
        orow = by_oracle[trace_id]
        oracle_dec = str(orow["expected_decision"])
        oracle_types = orow.get("expected_violation_types") or []
        if not isinstance(oracle_types, list):
            oracle_types = []
        oracle_types_str = json.dumps(oracle_types, separators=(",", ":"))

        trace = convert_trace_case_to_controlled_trace(case)

        for variant, mode in plan:
            replay, blocked, rules, reason, ms = run_trace_variant(
                trace, variant=variant, mode=mode
            )
            replay_s = replay.value
            matched = oracle_dec == replay_s
            rules_str = ",".join(rules)
            types_str = rules_str

            rows.append(
                {
                    "trace_id": trace_id,
                    "trace_name": str(case.get("trace_name", "")),
                    "trace_family": str(case.get("trace_family", "")),
                    "pair_id": str(case.get("pair_id", "")),
                    "pair_role": str(case.get("pair_role", "")),
                    "variant": variant,
                    "variant_supported": "true",
                    "oracle_expected_decision": oracle_dec,
                    "replay_decision": replay_s,
                    "matched_oracle": "true" if matched else "false",
                    "blocking_step_id": blocked or "",
                    "oracle_violation_types": oracle_types_str,
                    "replay_violation_types": types_str,
                    "replay_violation_rules": rules_str,
                    "decision_reason": reason,
                    "runtime_ms": round(ms, 3),
                }
            )

    summary = _build_summary(rows, plan, len(cases))
    return rows, summary


def _build_benign_suite_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-variant benign false-positive stats: oracle ALLOW traces incorrectly blocked."""
    variants = sorted({str(r["variant"]) for r in rows})
    oracle_allow_ids: list[str] = []
    seen: set[str] = set()
    for r in rows:
        tid = str(r["trace_id"])
        if str(r["oracle_expected_decision"]) == "ALLOW" and tid not in seen:
            seen.add(tid)
            oracle_allow_ids.append(tid)
    n = len(oracle_allow_ids)
    by_variant: dict[str, dict[str, Any]] = {}
    for v in variants:
        blocked = 0
        admitted = 0
        for tid in oracle_allow_ids:
            row = next(x for x in rows if str(x["variant"]) == v and str(x["trace_id"]) == tid)
            if str(row["replay_decision"]) == "BLOCK":
                blocked += 1
            else:
                admitted += 1
        by_variant[v] = {
            "total_benign_oracle_allow_traces": n,
            "admitted_benign": admitted,
            "blocked_benign_false_positives": blocked,
            "benign_false_positive_rate": (blocked / n) if n else 0.0,
        }
    return {
        "description": (
            "Benign false-positive analysis over traces with oracle_expected_decision ALLOW. "
            "blocked_benign_false_positives counts oracle-ALLOW traces where replay_decision is BLOCK."
        ),
        "total_benign_traces": n,
        "by_variant": by_variant,
    }


def write_benign_suite_summary_files(benign_summary: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    """Write ``rac_tracebench_v06_benign_summary.{json,csv}`` (separate from oracle-BLOCK missed-block metrics)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "rac_tracebench_v06_benign_summary.json"
    json_path.write_text(json.dumps(benign_summary, indent=2, sort_keys=True), encoding="utf-8")
    csv_path = out_dir / "rac_tracebench_v06_benign_summary.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "variant",
                "total_benign_traces",
                "admitted_benign",
                "blocked_benign_false_positives",
                "benign_false_positive_rate",
            ]
        )
        n_tot = int(benign_summary["total_benign_traces"])
        for v in sorted((benign_summary.get("by_variant") or {}).keys()):
            d = benign_summary["by_variant"][v]
            w.writerow(
                [
                    v,
                    n_tot,
                    d["admitted_benign"],
                    d["blocked_benign_false_positives"],
                    f"{float(d['benign_false_positive_rate']):.8f}",
                ]
            )
    return csv_path, json_path


def _build_summary(
    rows: list[dict[str, Any]],
    plan: list[tuple[str, AblationMode]],
    total_traces: int,
) -> dict[str, Any]:
    variants_run = [v for v, _ in plan]
    supported_variants = list(variants_run)
    unsupported_variants: list[str] = []
    supported_rows = [r for r in rows if r.get("variant_supported") == "true"]
    total_runs = len(supported_rows)

    by_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in supported_rows:
        by_variant[str(r["variant"])].append(r)

    def _rates(vname: str) -> dict[str, float]:
        rs = by_variant.get(vname, [])
        if not rs:
            return {"match_rate": 0.0, "false_positive_rate": 0.0, "false_negative_rate": 0.0, "block_rate": 0.0}
        n = len(rs)
        matches = sum(1 for x in rs if x["matched_oracle"] == "true")
        fp = sum(
            1
            for x in rs
            if x["oracle_expected_decision"] == "ALLOW" and x["replay_decision"] == "BLOCK"
        )
        fn = sum(
            1
            for x in rs
            if x["oracle_expected_decision"] == "BLOCK" and x["replay_decision"] == "ALLOW"
        )
        br = sum(1 for x in rs if x["replay_decision"] == "BLOCK")
        return {
            "match_rate": matches / n,
            "false_positive_rate": fp / n,
            "false_negative_rate": fn / n,
            "block_rate": br / n,
        }

    match_rate_by_variant = {v: _rates(v)["match_rate"] for v in variants_run}
    false_positive_by_variant = {v: _rates(v)["false_positive_rate"] for v in variants_run}
    false_negative_by_variant = {v: _rates(v)["false_negative_rate"] for v in variants_run}
    block_rate_by_variant = {v: _rates(v)["block_rate"] for v in variants_run}

    per_family: dict[str, dict[str, dict[str, float | int]]] = defaultdict(dict)
    for r in supported_rows:
        fam = str(r["trace_family"])
        var = str(r["variant"])
        bucket = per_family[fam].setdefault(var, {"matched": 0, "total": 0})
        bucket["total"] = int(bucket["total"]) + 1
        if r["matched_oracle"] == "true":
            bucket["matched"] = int(bucket["matched"]) + 1

    for fam in per_family:
        for var in per_family[fam]:
            b = per_family[fam][var]
            tot = int(b["total"])
            b["match_rate"] = float(b["matched"]) / tot if tot else 0.0

    return {
        "total_traces": total_traces,
        "variants": variants_run,
        "supported_variants": supported_variants,
        "unsupported_variants": unsupported_variants,
        "total_runs": total_runs,
        "match_rate_by_variant": match_rate_by_variant,
        "false_positive_by_variant": false_positive_by_variant,
        "false_negative_by_variant": false_negative_by_variant,
        "block_rate_by_variant": block_rate_by_variant,
        "per_family_results": dict(per_family),
        "benign_suite_summary": _build_benign_suite_summary(rows),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "static_tool_allowlist_note": (
            "STATIC_TOOL_ALLOWLIST uses a fixed {read_file, summarize_file} allowlist baseline heuristic "
            "for TraceBench replay; it does not expand grant_templates or enforce resource/purpose/lineage."
        ),
    }


CSV_FIELDNAMES: tuple[str, ...] = (
    "trace_id",
    "trace_name",
    "trace_family",
    "pair_id",
    "pair_role",
    "variant",
    "variant_supported",
    "oracle_expected_decision",
    "replay_decision",
    "matched_oracle",
    "blocking_step_id",
    "oracle_violation_types",
    "replay_violation_types",
    "replay_violation_rules",
    "decision_reason",
    "runtime_ms",
)


def write_tracebench_experiment_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(CSV_FIELDNAMES), extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in CSV_FIELDNAMES})


def write_tracebench_experiment_summary(summary: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")


def run_and_write(
    *,
    root: Path | None = None,
    output_dir: Path | None = None,
    csv_name: str = "rac_tracebench_v06_results.csv",
    json_name: str = "rac_tracebench_v06_summary.json",
) -> tuple[Path, Path]:
    r = resolve_tracebench_root(root)
    if r is None:
        raise FileNotFoundError(
            "RAC-TraceBench root not found. Set RAC_TRACEBENCH_ROOT or place mcp_data/rac_tracebench_v06."
        )
    out = output_dir or Path("results")
    out = out.expanduser().resolve()
    rows, summary = build_experiment_rows(root=r)
    csv_path = out / csv_name
    json_path = out / json_name
    write_tracebench_experiment_csv(rows, csv_path)
    write_tracebench_experiment_summary(summary, json_path)
    benign = summary.get("benign_suite_summary")
    if isinstance(benign, dict):
        write_benign_suite_summary_files(benign, out)
    return csv_path, json_path
