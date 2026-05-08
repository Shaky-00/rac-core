#!/usr/bin/env python3
"""Aggregate existing ``results/*.json`` summaries into a single overview (no experiments run)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"

INPUTS = {
    "tracebench": RESULTS / "rac_tracebench_v06_summary.json",
    "overhead": RESULTS / "rac_tracebench_v06_overhead_summary.json",
    "mcp_fs": RESULTS / "mcp_real_filesystem_v06_summary.json",
    "planner": RESULTS / "mcp_real_filesystem_planner_v06_summary.json",
}
OUT_JSON = RESULTS / "rac_experiment_overview.json"
OUT_MD = RESULTS / "rac_experiment_overview.md"


def _load(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    tb = _load(INPUTS["tracebench"])
    oh = _load(INPUTS["overhead"])
    mcp = _load(INPUTS["mcp_fs"])
    planner = _load(INPUTS["planner"])

    missing = [str(p.relative_to(ROOT)) for p in INPUTS.values() if not p.is_file()]
    # Re-check: tracebench required for core sections
    if tb is None:
        print(f"ERROR: missing required {INPUTS['tracebench']}", file=sys.stderr)
        return 1

    mrv = tb.get("match_rate_by_variant") or {}
    fnv = tb.get("false_negative_by_variant") or {}
    fpv = tb.get("false_positive_by_variant") or {}

    ablation_prefix = "RAC_WITHOUT_"
    ablation_rates = {
        k: mrv[k]
        for k in mrv
        if k.startswith(ablation_prefix)
    }
    ablation_fn = {k: fnv.get(k) for k in ablation_rates}

    sorted_ablation = sorted(ablation_rates.items(), key=lambda x: (x[1], x[0]))
    worst_rate = sorted_ablation[0][1] if sorted_ablation else None
    tied_lowest = [k for k, v in sorted_ablation if v == worst_rate] if worst_rate is not None else []
    key_fn_signal = {
        "lowest_match_rate": worst_rate,
        "variants_at_lowest_match_rate": tied_lowest,
        "false_negative_by_ablation_variant": ablation_fn,
        "full_rac_false_negative": fnv.get("FULL_RAC"),
        "note": "Ablations with lower match_rate indicate stronger regression vs FULL_RAC; higher false_negative vs FULL_RAC indicates missed attacks.",
    }

    controlled_tracebench = {
        "total_traces": tb.get("total_traces"),
        "variants": tb.get("variants") or tb.get("supported_variants"),
        "match_rate_FULL_RAC": mrv.get("FULL_RAC"),
        "match_rate_NO_RAC": mrv.get("NO_RAC"),
        "match_rate_ENTRY_ONLY": mrv.get("ENTRY_ONLY"),
        "match_rate_STATIC_TOOL_ALLOWLIST": mrv.get("STATIC_TOOL_ALLOWLIST"),
        "false_positive_by_variant": {k: fpv.get(k) for k in ("FULL_RAC", "NO_RAC", "ENTRY_ONLY", "STATIC_TOOL_ALLOWLIST") if k in fpv or k in mrv},
        "false_negative_by_variant": {k: fnv.get(k) for k in ("FULL_RAC", "NO_RAC", "ENTRY_ONLY", "STATIC_TOOL_ALLOWLIST") if k in fnv or k in mrv},
        "source_generated_at": tb.get("generated_at"),
    }

    overhead_section = None
    if oh:
        overhead_section = {
            "iterations": oh.get("iterations"),
            "p50_step_ms": oh.get("p50_step_ms"),
            "p95_step_ms": oh.get("p95_step_ms"),
            "p99_step_ms": oh.get("p99_step_ms"),
            "mean_step_ms": oh.get("mean_step_ms"),
            "mean_trace_ms": oh.get("mean_trace_ms"),
            "coarse_grained_measurement_notes": oh.get("coarse_grained_measurement_notes"),
            "source_generated_at": oh.get("generated_at"),
        }

    real_fs = None
    if mcp:
        real_fs = {
            "total_scenarios": mcp.get("total_scenarios"),
            "match_rate": mcp.get("match_rate"),
            "blocked_attack_steps_server_not_called": mcp.get("server_call_block_success_count"),
            "side_effect_block_success_count": mcp.get("side_effect_block_success_count"),
            "matched_expected_count": mcp.get("matched_expected_count"),
            "source_generated_at": mcp.get("generated_at"),
        }

    planner_section = None
    if planner:
        if planner.get("variants") is not None:
            planner_section = {
                "total_plans": planner.get("total_plans"),
                "total_steps_by_variant": planner.get("total_steps_by_variant"),
                "match_rate_by_variant": planner.get("match_rate_by_variant"),
                "server_call_issued_count_by_variant": planner.get("server_call_issued_count_by_variant"),
                "side_effect_materialized_count_by_variant": planner.get("side_effect_materialized_count_by_variant"),
                "full_rac_blocked_side_effects": planner.get("full_rac_blocked_side_effects"),
                "no_rac_materialized_side_effects": planner.get("no_rac_materialized_side_effects"),
                "variants": planner.get("variants"),
                "source_generated_at": planner.get("generated_at"),
            }
        else:
            planner_section = {
                "total_plans": planner.get("total_plans"),
                "total_steps": planner.get("total_steps"),
                "match_rate": planner.get("match_rate"),
                "blocked_steps": planner.get("blocked_steps"),
                "server_call_block_success_count": planner.get("server_call_block_success_count"),
                "side_effect_block_success_count": planner.get("side_effect_block_success_count"),
                "note": "Legacy single-variant planner summary (no FULL_RAC/NO_RAC breakdown). Re-run planner with --variants FULL_RAC,NO_RAC to refresh.",
                "source_generated_at": planner.get("generated_at"),
            }

    conclusion = (
        "FULL_RAC matches controlled TraceBench expectations while weaker baselines (NO_RAC, ENTRY_ONLY, static allowlist) "
        "and RAC_WITHOUT ablations show authorization drift and missed blocks (higher false negatives). "
        "Ablation sweep indicates component necessity via match-rate drops. "
        "Replay overhead percentiles on controlled traces stay low at coarse instrumentation granularity. "
        "Real filesystem MCP runs show NO_RAC materializing unauthorized write side effects while FULL_RAC prevents them "
        "(compare planner variant summaries when present)."
    )

    overview = {
        "overview_generated_at": _now_iso(),
        "inputs": {k: str(v) for k, v in INPUTS.items()},
        "missing_inputs": missing,
        "controlled_tracebench": controlled_tracebench,
        "ablation": {
            "match_rate_by_variant_RAC_WITHOUT": ablation_rates,
            "key_false_negative_signal": key_fn_signal,
        },
        "overhead": overhead_section,
        "real_filesystem_mcp": real_fs,
        "planner_style_filesystem_mcp": planner_section,
        "conclusion": conclusion,
    }

    OUT_JSON.write_text(json.dumps(overview, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# RAC experiment overview",
        "",
        f"Generated: `{overview['overview_generated_at']}` (reads committed ``results/*.json`` artifacts only).",
        "",
        "## Controlled TraceBench",
        "",
        f"- **total_traces**: {controlled_tracebench.get('total_traces')}",
        f"- **FULL_RAC match_rate**: {controlled_tracebench.get('match_rate_FULL_RAC')}",
        f"- **NO_RAC match_rate**: {controlled_tracebench.get('match_rate_NO_RAC')}",
        f"- **ENTRY_ONLY match_rate**: {controlled_tracebench.get('match_rate_ENTRY_ONLY')}",
        f"- **STATIC_TOOL_ALLOWLIST match_rate**: {controlled_tracebench.get('match_rate_STATIC_TOOL_ALLOWLIST')}",
        f"- **false_positive (FULL_RAC)**: {fpv.get('FULL_RAC')}",
        f"- **false_negative (FULL_RAC)**: {fnv.get('FULL_RAC')}",
        f"- **false_negative (NO_RAC)**: {fnv.get('NO_RAC')}",
        "",
        "## Ablation (RAC_WITHOUT_*)",
        "",
        "Match rates (controlled replay):",
        "",
    ]
    for k, v in sorted(ablation_rates.items()):
        lines.append(f"- **{k}**: {v}")
    lines.extend(
        [
            "",
        "**FN signal (summary)**:",
        f"- Lowest match_rate: `{key_fn_signal.get('lowest_match_rate')}` (variants: {', '.join(key_fn_signal.get('variants_at_lowest_match_rate') or [])})",
            "",
            "## Overhead (controlled TraceBench replay)",
            "",
        ]
    )
    if overhead_section:
        lines.extend(
            [
                f"- **iterations**: {overhead_section.get('iterations')}",
                f"- **p50_step_ms**: {overhead_section.get('p50_step_ms')}",
                f"- **p95_step_ms**: {overhead_section.get('p95_step_ms')}",
                f"- **p99_step_ms**: {overhead_section.get('p99_step_ms')}",
                f"- **mean_step_ms**: {overhead_section.get('mean_step_ms')}",
                f"- **mean_trace_ms**: {overhead_section.get('mean_trace_ms')}",
                f"- **coarse_grained_measurement_notes**: {overhead_section.get('coarse_grained_measurement_notes')}",
                "",
            ]
        )
    else:
        lines.append("*Overhead summary missing.*\n")

    lines.extend(["## Real filesystem MCP (demo script)", ""])
    if real_fs:
        lines.extend(
            [
                f"- **total_scenarios**: {real_fs.get('total_scenarios')}",
                f"- **match_rate**: {real_fs.get('match_rate')}",
                f"- **blocked attack steps (server not called)**: {real_fs.get('blocked_attack_steps_server_not_called')}",
                f"- **side_effect_block_success_count**: {real_fs.get('side_effect_block_success_count')}",
                "",
            ]
        )
    else:
        lines.append(f"*Missing `{INPUTS['mcp_fs'].relative_to(ROOT)}`.*\n")

    lines.extend(["## Planner-style filesystem MCP", ""])
    if planner_section:
        lines.append("```json")
        lines.append(json.dumps(planner_section, indent=2, ensure_ascii=False))
        lines.append("```")
        lines.append("")
    else:
        lines.append(f"*Missing `{INPUTS['planner'].relative_to(ROOT)}`.*\n")

    lines.extend(["## Conclusion", "", conclusion, ""])

    if missing:
        lines.extend(["## Missing inputs", "", "- " + "\n- ".join(missing), ""])

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_JSON.relative_to(ROOT)}")
    print(f"Wrote {OUT_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
