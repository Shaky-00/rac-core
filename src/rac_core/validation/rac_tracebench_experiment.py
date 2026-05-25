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
    is_v1_tracebench_root,
    load_rac_tracebench,
    oracle_label_by_trace_id,
    resolve_rac_tracebench_root,
)
from rac_core.validation.rac_tracebench_v1_adapter import oracle_rows_by_trace_id
from rac_core.validation.tracebench_workflow_metadata import enrich_case_metadata


def resolve_tracebench_root(explicit: Path | None = None) -> Path | None:
    if explicit is not None:
        p = explicit.expanduser().resolve()
        if (p / "controlled_traces" / "core").is_dir() or (p / "controlled_traces" / "paired").is_dir():
            return p
        return None
    env = os.environ.get("RAC_TRACEBENCH_ROOT")
    if env:
        p = Path(env).expanduser().resolve()
        if (p / "controlled_traces" / "core").is_dir() or (p / "controlled_traces" / "paired").is_dir():
            return p
    return resolve_rac_tracebench_root()


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

_TRACE_BENCH_BASELINE_NAMES = frozenset(
    {
        "FULL_RAC",
        "NO_RAC",
        "ENTRY_ONLY",
        "STATIC_TOOL_ALLOWLIST",
        "HistoryAware",
        "Static+History",
    }
)

_TRACE_BENCH_DIAGNOSTIC_PREFIX = "RAC_WITHOUT_"


def tracebench_variant_plan(group: str) -> list[tuple[str, AblationMode]]:
    """Subset of :func:`default_variant_plan` for RQ2-style runs (same replay semantics per variant)."""
    plan = default_variant_plan()
    g = (group or "all").strip().lower()
    if g in ("all", "full"):
        return plan
    if g in ("baselines", "baseline", "rq2_main", "rq2"):
        return [(v, m) for v, m in plan if v in _TRACE_BENCH_BASELINE_NAMES]
    if g in ("ablations", "ablation", "rac_without", "rq2_diagnostic", "diagnostic"):
        return [(v, m) for v, m in plan if v.startswith(_TRACE_BENCH_DIAGNOSTIC_PREFIX)]
    if g == "rq2_full":
        return plan
    raise ValueError(f"unknown variant group: {group!r}")


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
    suite: str = "all",
    include_mixed: bool = True,
    include_rq2_overlay: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    bundle = load_rac_tracebench(
        root,
        suite=suite,
        include_mixed=include_mixed,
        include_rq2_overlay=include_rq2_overlay,
    )
    cases = bundle["traces"]
    oracle_doc = bundle["oracle_labels"]
    if is_v1_tracebench_root(root):
        by_oracle = oracle_rows_by_trace_id(oracle_doc)
    else:
        by_oracle = oracle_label_by_trace_id(oracle_doc)
    plan = variant_plan or default_variant_plan()

    rows: list[dict[str, Any]] = []

    for case in cases:
        trace_id = str(case["trace_id"])
        orow = by_oracle.get(trace_id) or by_oracle.get(str(case.get("workflow_id", trace_id)))
        if orow is None:
            raise KeyError(f"missing oracle row for trace_id={trace_id!r}")
        wmeta = enrich_case_metadata(
            {
                "case_id": trace_id,
                "legacy_trace_id": case.get("workflow_id") or trace_id,
                "family": case.get("trace_family") or case.get("primary_family"),
                "expected_workflow_decision": orow.get("expected_decision"),
                "expected_violation_rules": case.get("expected_predicates") or [],
            },
            orow,
        )
        if case.get("oracle_label"):
            wmeta = {
                **wmeta,
                "oracle_label": case["oracle_label"],
                "scenario_type": case.get("scenario_type", wmeta["scenario_type"]),
                "violation_families": case.get("violation_families") or wmeta["violation_families"],
                "primary_family": case.get("primary_family") or wmeta["primary_family"],
                "violation_families_json": json.dumps(
                    case.get("violation_families") or wmeta["violation_families"],
                    separators=(",", ":"),
                ),
            }
        oracle_dec = str(wmeta["oracle_label"])
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
            is_missed = oracle_dec == "BLOCK" and replay_s == "ALLOW"
            is_false = oracle_dec == "ALLOW" and replay_s == "BLOCK"

            rows.append(
                {
                    "workflow_id": wmeta["workflow_id"],
                    "trace_id": trace_id,
                    "trace_name": str(case.get("trace_name", "")),
                    "trace_family": str(case.get("trace_family", "")),
                    "pair_id": str(case.get("pair_id", "")),
                    "pair_role": str(case.get("pair_role", "")),
                    "variant": variant,
                    "variant_role": (
                        "diagnostic"
                        if variant.startswith(_TRACE_BENCH_DIAGNOSTIC_PREFIX)
                        else "main"
                    ),
                    "variant_supported": "true",
                    "oracle_label": oracle_dec,
                    "oracle_expected_decision": oracle_dec,
                    "scenario_type": wmeta["scenario_type"],
                    "violation_families": wmeta["violation_families_json"],
                    "primary_family": wmeta["primary_family"],
                    "replay_decision": replay_s,
                    "matched_oracle": "true" if matched else "false",
                    "is_missed_block": "true" if is_missed else "false",
                    "is_false_block": "true" if is_false else "false",
                    "blocking_step_id": blocked or "",
                    "oracle_violation_types": oracle_types_str,
                    "replay_violation_types": types_str,
                    "replay_violation_rules": rules_str,
                    "blocked_by_rules": rules_str,
                    "decision_reason": reason,
                    "runtime_ms": round(ms, 3),
                }
            )

    summary = _build_summary(rows, plan, len(cases), cases=cases, bundle=bundle)
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
    *,
    cases: list[dict[str, Any]] | None = None,
    bundle: dict[str, Any] | None = None,
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

    seen_allow: set[str] = set()
    seen_block: set[str] = set()
    for r in supported_rows:
        tid = str(r["trace_id"])
        if r["oracle_expected_decision"] == "ALLOW" and tid not in seen_allow:
            seen_allow.add(tid)
        if r["oracle_expected_decision"] == "BLOCK" and tid not in seen_block:
            seen_block.add(tid)
    allow_cases = len(seen_allow)
    block_cases = len(seen_block)

    missed_block_by_variant: dict[str, dict[str, Any]] = {}
    for v in variants_run:
        rs = by_variant.get(v, [])
        fn = sum(
            1
            for x in rs
            if x["oracle_expected_decision"] == "BLOCK" and x["replay_decision"] == "ALLOW"
        )
        rate = (fn / block_cases) if block_cases else 0.0
        missed_block_by_variant[v] = {
            "missed_block_count": fn,
            "missed_block_rate": rate,
            "oracle_block_denominator": block_cases,
        }

    benign_admitted_by_variant: dict[str, int] = {}
    benign_summary = _build_benign_suite_summary(rows)
    for v, d in (benign_summary.get("by_variant") or {}).items():
        benign_admitted_by_variant[str(v)] = int(d.get("admitted_benign", 0))

    false_block_by_variant: dict[str, dict[str, Any]] = {}
    for v in variants_run:
        rs = by_variant.get(v, [])
        fp = sum(
            1
            for x in rs
            if x.get("oracle_label", x.get("oracle_expected_decision")) == "ALLOW"
            and x.get("replay_decision") == "BLOCK"
        )
        rate = (fp / allow_cases) if allow_cases else 0.0
        false_block_by_variant[v] = {
            "false_block_count": fp,
            "false_block_rate": rate,
            "oracle_allow_denominator": allow_cases,
        }

    missed_block_by_scenario_type: dict[str, dict[str, dict[str, Any]]] = {}
    primary_family_missed: dict[str, dict[str, dict[str, Any]]] = {}
    workflow_meta: dict[str, dict[str, str]] = {}
    for r in supported_rows:
        wid = str(r.get("workflow_id") or r["trace_id"])
        if wid not in workflow_meta:
            workflow_meta[wid] = {
                "oracle_label": str(r.get("oracle_label", r.get("oracle_expected_decision", ""))),
                "scenario_type": str(r.get("scenario_type", "")),
                "primary_family": str(r.get("primary_family", "")),
            }

    for v in variants_run:
        missed_block_by_scenario_type[v] = {}
        primary_family_missed[v] = {}
        for stype in ("single_drift", "composite_drift"):
            block_ids = [
                wid
                for wid, m in workflow_meta.items()
                if m["oracle_label"] == "BLOCK" and m["scenario_type"] == stype
            ]
            denom = len(block_ids)
            missed = sum(
                1
                for wid in block_ids
                if any(
                    str(x.get("workflow_id") or x["trace_id"]) == wid
                    and x.get("replay_decision") == "ALLOW"
                    for x in by_variant[v]
                )
            )
            missed_block_by_scenario_type[v][stype] = {
                "missed_block_count": missed,
                "missed_block_rate": (missed / denom) if denom else 0.0,
                "oracle_block_denominator": denom,
            }

        fam_block: dict[str, list[str]] = defaultdict(list)
        for wid, m in workflow_meta.items():
            if m["oracle_label"] == "BLOCK" and m["primary_family"]:
                fam_block[m["primary_family"]].append(wid)
        for fam, block_ids in fam_block.items():
            denom = len(block_ids)
            missed = sum(
                1
                for wid in block_ids
                if any(
                    str(x.get("workflow_id") or x["trace_id"]) == wid
                    and x.get("replay_decision") == "ALLOW"
                    for x in by_variant[v]
                )
            )
            primary_family_missed[v][fam] = {
                "missed_block_count": missed,
                "missed_block_rate": (missed / denom) if denom else 0.0,
                "oracle_block_denominator": denom,
            }

    scenario_type_counts: dict[str, int] = defaultdict(int)
    for _wid, m in workflow_meta.items():
        scenario_type_counts[m["scenario_type"]] += 1
    for st in ("benign", "single_drift", "composite_drift"):
        scenario_type_counts.setdefault(st, 0)

    composite_multi_family = 0
    seen_wid: set[str] = set()
    for r in supported_rows:
        wid = str(r.get("workflow_id") or r["trace_id"])
        if wid in seen_wid:
            continue
        if str(r.get("oracle_label", "")) != "BLOCK":
            continue
        seen_wid.add(wid)
        try:
            vf = json.loads(str(r.get("violation_families", "[]")))
        except json.JSONDecodeError:
            vf = []
        if isinstance(vf, list) and len(vf) >= 2:
            composite_multi_family += 1

    family_breakdown: dict[str, int] = {}
    if cases:
        for c in cases:
            fam = str(c.get("trace_family", ""))
            family_breakdown[fam] = family_breakdown.get(fam, 0) + 1

    component_diagnostic: list[dict[str, Any]] = []
    full_rows = {str(r["workflow_id"] or r["trace_id"]): r for r in by_variant.get("FULL_RAC", [])}
    for v in variants_run:
        if not v.startswith(_TRACE_BENCH_DIAGNOSTIC_PREFIX):
            continue
        for r in by_variant.get(v, []):
            wid = str(r.get("workflow_id") or r["trace_id"])
            full = full_rows.get(wid)
            if not full:
                continue
            if full.get("replay_decision") != r.get("replay_decision"):
                component_diagnostic.append(
                    {
                        "workflow_id": wid,
                        "diagnostic_variant": v,
                        "oracle_label": r.get("oracle_label"),
                        "full_rac_decision": full.get("replay_decision"),
                        "diagnostic_decision": r.get("replay_decision"),
                        "scenario_type": r.get("scenario_type"),
                        "violation_families": r.get("violation_families"),
                        "primary_family": r.get("primary_family"),
                    }
                )

    return {
        "total_traces": total_traces,
        "total_cases": total_traces,
        "allow_cases": allow_cases,
        "block_cases": block_cases,
        "oracle_block_denominator": block_cases,
        "benchmark_version": (bundle or {}).get("benchmark_version", "0.6"),
        "suite": (bundle or {}).get("suite", "all"),
        "include_mixed": (bundle or {}).get("include_mixed", True),
        "include_rq2_overlay": (bundle or {}).get("include_rq2_overlay", False),
        "scenario_type_counts": dict(scenario_type_counts),
        "block_workflows_with_multiple_violation_families": composite_multi_family,
        "missed_block_by_variant": missed_block_by_variant,
        "false_block_by_variant": false_block_by_variant,
        "missed_block_by_scenario_type": missed_block_by_scenario_type,
        "missed_block_by_primary_family": primary_family_missed,
        "component_diagnostic_flips": component_diagnostic,
        "benign_admitted_by_variant": benign_admitted_by_variant,
        "family_breakdown": family_breakdown,
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
    "workflow_id",
    "trace_id",
    "trace_name",
    "trace_family",
    "pair_id",
    "pair_role",
    "variant",
    "variant_role",
    "variant_supported",
    "oracle_label",
    "oracle_expected_decision",
    "scenario_type",
    "violation_families",
    "primary_family",
    "replay_decision",
    "matched_oracle",
    "is_missed_block",
    "is_false_block",
    "blocking_step_id",
    "oracle_violation_types",
    "replay_violation_types",
    "replay_violation_rules",
    "blocked_by_rules",
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


def write_rq2_auxiliary_outputs(summary: dict[str, Any], out_dir: Path) -> list[Path]:
    """Write RQ2 diagnostic CSV/JSON alongside main experiment outputs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    diag = summary.get("component_diagnostic_flips") or []
    diag_path = out_dir / "rq2_component_diagnostic.csv"
    with diag_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "workflow_id",
                "diagnostic_variant",
                "oracle_label",
                "full_rac_decision",
                "diagnostic_decision",
                "scenario_type",
                "violation_families",
                "primary_family",
            ],
        )
        w.writeheader()
        for row in diag:
            w.writerow(row)
    written.append(diag_path)

    rq2_path = out_dir / "rq2_summary.json"
    rq2_doc = {
        "missed_block_by_variant": summary.get("missed_block_by_variant"),
        "false_block_by_variant": summary.get("false_block_by_variant"),
        "missed_block_by_scenario_type": summary.get("missed_block_by_scenario_type"),
        "missed_block_by_primary_family": summary.get("missed_block_by_primary_family"),
        "scenario_type_counts": summary.get("scenario_type_counts"),
        "block_workflows_with_multiple_violation_families": summary.get(
            "block_workflows_with_multiple_violation_families"
        ),
        "component_diagnostic_flip_count": len(diag),
    }
    rq2_path.write_text(json.dumps(rq2_doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    written.append(rq2_path)
    return written


def run_and_write(
    *,
    root: Path | None = None,
    output_dir: Path | None = None,
    variant_plan: list[tuple[str, AblationMode]] | None = None,
    csv_name: str = "rac_tracebench_v06_results.csv",
    json_name: str = "rac_tracebench_v06_summary.json",
    suite: str = "all",
    include_mixed: bool = True,
    include_rq2_overlay: bool = False,
    write_rq2_aux: bool = False,
) -> tuple[Path, Path]:
    r = resolve_tracebench_root(root)
    if r is None:
        raise FileNotFoundError(
            "RAC-TraceBench root not found. Set RAC_TRACEBENCH_ROOT or install suites under "
            "RAC_DATA_DIR (default ../rac-data/tracebench/paired or tracebench/controlled_traces/...)."
        )
    out = output_dir or Path("results")
    out = out.expanduser().resolve()
    rows, summary = build_experiment_rows(
        root=r,
        variant_plan=variant_plan,
        suite=suite,
        include_mixed=include_mixed,
        include_rq2_overlay=include_rq2_overlay,
    )
    csv_path = out / csv_name
    json_path = out / json_name
    write_tracebench_experiment_csv(rows, csv_path)
    write_tracebench_experiment_summary(summary, json_path)
    benign = summary.get("benign_suite_summary")
    if isinstance(benign, dict):
        write_benign_suite_summary_files(benign, out)
    if write_rq2_aux:
        write_rq2_auxiliary_outputs(summary, out)
    return csv_path, json_path
