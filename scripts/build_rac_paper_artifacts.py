#!/usr/bin/env python3
"""Build paper figures and tables from committed ``results/*.json|csv|md`` only (no experiments)."""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
ART_FIG = ROOT / "artifacts" / "figures"
ART_TBL = ROOT / "artifacts" / "tables"
README = ROOT / "artifacts" / "README_experiment_artifacts.md"

INPUTS = {
    "tracebench_summary": RESULTS / "rac_tracebench_v06_summary.json",
    "tracebench_results": RESULTS / "rac_tracebench_v06_results.csv",
    "tracebench_analysis": RESULTS / "rac_tracebench_v06_analysis.md",
    "overhead_summary": RESULTS / "rac_tracebench_v06_overhead_summary.json",
    "mcp_fs_summary": RESULTS / "mcp_real_filesystem_v06_summary.json",
    "mcp_fs_results": RESULTS / "mcp_real_filesystem_v06_results.csv",
    "planner_summary": RESULTS / "mcp_real_filesystem_planner_v06_summary.json",
    "planner_results": RESULTS / "mcp_real_filesystem_planner_v06_results.csv",
    "overview_json": RESULTS / "rac_experiment_overview.json",
    "overview_md": RESULTS / "rac_experiment_overview.md",
}

VARIANT_ORDER = [
    "FULL_RAC",
    "NO_RAC",
    "ENTRY_ONLY",
    "STATIC_TOOL_ALLOWLIST",
    "RAC_WITHOUT_ACTION",
    "RAC_WITHOUT_RESOURCE_ORIGIN",
    "RAC_WITHOUT_OUTPUT_ANCHOR",
    "RAC_WITHOUT_LINEAGE",
    "RAC_WITHOUT_PURPOSE",
    "RAC_WITHOUT_CONDITION",
    "RAC_WITHOUT_DELEGATION",
]

LABEL_ABBREV = {
    "FULL_RAC": "FULL_RAC",
    "NO_RAC": "NO_RAC",
    "ENTRY_ONLY": "ENTRY_ONLY",
    "STATIC_TOOL_ALLOWLIST": "STATIC_AL",
    "RAC_WITHOUT_ACTION": "w/o ACTION",
    "RAC_WITHOUT_RESOURCE_ORIGIN": "w/o RES_ORIG",
    "RAC_WITHOUT_OUTPUT_ANCHOR": "w/o OUT_ANC",
    "RAC_WITHOUT_LINEAGE": "w/o LINEAGE",
    "RAC_WITHOUT_PURPOSE": "w/o PURPOSE",
    "RAC_WITHOUT_CONDITION": "w/o COND",
    "RAC_WITHOUT_DELEGATION": "w/o DELEG",
}


def _load_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _ensure_dirs() -> None:
    ART_FIG.mkdir(parents=True, exist_ok=True)
    ART_TBL.mkdir(parents=True, exist_ok=True)


def _require_matplotlib():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        return plt
    except ImportError as e:
        print(
            "ERROR: matplotlib required. Install with: pip install 'matplotlib>=3.8,<4'\n"
            "  (included in project optional dev extras.)",
            file=sys.stderr,
        )
        raise SystemExit(1) from e


def _save_figure(fig, stem: str) -> None:
    import matplotlib.pyplot as _plt

    base = ART_FIG / stem
    fig.savefig(base.with_suffix(".png"), dpi=200, bbox_inches="tight")
    fig.savefig(base.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(base.with_suffix(".svg"), bbox_inches="tight")
    fig.clear()
    _plt.close(fig)


def figure_ablation_match_rate(tb: dict, plt) -> None:
    mrv = tb.get("match_rate_by_variant") or {}
    fnv = tb.get("false_negative_by_variant") or {}
    fpv = tb.get("false_positive_by_variant") or {}
    variants = [v for v in VARIANT_ORDER if v in mrv]
    rates = [mrv[v] for v in variants]
    labels = [LABEL_ABBREV.get(v, v) for v in variants]

    fig, ax = plt.subplots(figsize=(11.5, 4.2))
    x = range(len(variants))
    ax.bar(x, rates, color="#3d5a80", edgecolor="#293241", linewidth=0.6)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=42, ha="right", fontsize=9)
    ax.set_ylabel("Match rate")
    ax.set_ylim(0, 1.05)
    ax.set_title("TraceBench v0.6: oracle match rate by replay variant (controlled replay)")
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    fig.tight_layout()
    _save_figure(fig, "figure_ablation_match_rate")

    lines = [
        "| variant | match_rate | false_negative | false_positive |",
        "|---------|------------|----------------|----------------|",
    ]
    for v in variants:
        lines.append(
            f"| `{v}` | {mrv.get(v)} | {fnv.get(v)} | {fpv.get(v)} |"
        )
    lines.append("")
    lines.append("*Abbreviations in figure axis labels:* STATIC_AL = STATIC_TOOL_ALLOWLIST; "
                 "w/o \\* = RAC_WITHOUT_\\* component ablation.")
    (ART_TBL / "table_ablation_match_rate.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def figure_overhead_latency(oh: dict, plt) -> None:
    keys = ["p50_step_ms", "p95_step_ms", "p99_step_ms", "mean_step_ms", "mean_trace_ms"]
    labels_k = ["p50 step", "p95 step", "p99 step", "mean step", "mean trace"]
    vals = [float(oh[k]) for k in keys]

    fig, ax = plt.subplots(figsize=(7.5, 4))
    ax.bar(range(len(vals)), vals, color="#5c677d", edgecolor="#333", linewidth=0.5)
    ax.set_xticks(range(len(labels_k)))
    ax.set_xticklabels(labels_k, rotation=22, ha="right")
    ax.set_ylabel("Latency (ms)")
    ax.set_title(
        "Controlled replay microbenchmark: step/trace latency (TraceBench harness)"
    )
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    fig.tight_layout()
    _save_figure(fig, "figure_overhead_latency")

    notes = oh.get("coarse_grained_measurement_notes", "")
    tbl = [
        "| Key | Value |",
        "|-----|-------|",
        f"| iterations | {oh.get('iterations')} |",
        f"| total_runs | {oh.get('total_runs')} |",
        f"| total_step_records | {oh.get('total_step_records')} |",
        f"| num_traces | {oh.get('num_traces')} |",
        f"| p50_step_ms | {oh.get('p50_step_ms')} |",
        f"| p95_step_ms | {oh.get('p95_step_ms')} |",
        f"| p99_step_ms | {oh.get('p99_step_ms')} |",
        f"| mean_step_ms | {oh.get('mean_step_ms')} |",
        f"| max_step_ms | {oh.get('max_step_ms')} |",
        f"| mean_trace_ms | {oh.get('mean_trace_ms')} |",
        f"| p95_trace_ms | {oh.get('p95_trace_ms')} |",
        f"| generated_at | {oh.get('generated_at')} |",
        "",
        "### coarse_grained_measurement_notes",
        "",
        notes if notes else "*(empty)*",
        "",
    ]
    (ART_TBL / "table_overhead_summary.md").write_text("\n".join(tbl) + "\n", encoding="utf-8")


def figure_real_mcp_side_effects(planner: dict | None, plt) -> None:
    if not planner:
        stub = (
            "# Real MCP side effects — input missing\n\n"
            "`mcp_real_filesystem_planner_v06_summary.json` was not found; figure skipped.\n"
        )
        (ART_TBL / "table_real_mcp_side_effects.md").write_text(stub, encoding="utf-8")
        return

    fr_sc = planner.get("server_call_issued_count_by_variant", {}).get("FULL_RAC")
    nr_sc = planner.get("server_call_issued_count_by_variant", {}).get("NO_RAC")
    fr_se = planner.get("side_effect_materialized_count_by_variant", {}).get("FULL_RAC")
    nr_se = planner.get("side_effect_materialized_count_by_variant", {}).get("NO_RAC")

    variants = ["FULL_RAC", "NO_RAC"]
    srv_calls = [fr_sc, nr_sc]
    side_mat = [fr_se, nr_se]

    fig, ax = plt.subplots(figsize=(6.5, 4))
    w = 0.35
    x = [0, 1]
    ax.bar([i - w / 2 for i in x], srv_calls, width=w, label="server_call_issued_count", color="#4a6fa5")
    ax.bar([i + w / 2 for i in x], side_mat, width=w, label="side_effect_materialized_count", color="#c08552")
    ax.set_xticks(x)
    ax.set_xticklabels(variants)
    ax.set_ylabel("Count")
    ax.legend(fontsize=8, loc="upper left")
    ax.set_title("Planner filesystem MCP: issued calls vs write side-effects materialized")
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    fig.tight_layout()
    _save_figure(fig, "figure_real_mcp_side_effects")

    csv_path = INPUTS["planner_results"]
    rows_out: list[list[str]] = []
    if csv_path.is_file():
        with csv_path.open(encoding="utf-8", newline="") as f:
            rdr = csv.DictReader(f)
            want = {"attack_write_leak_plan", "attack_mixed_list_then_write_plan"}
            for row in rdr:
                if row.get("tool_name") != "write_file":
                    continue
                if row.get("plan_id") not in want:
                    continue
                rows_out.append(
                    [
                        row.get("plan_id", ""),
                        row.get("variant", ""),
                        row.get("rac_decision", ""),
                        row.get("server_call_issued", ""),
                        row.get("side_effect_exists", ""),
                        row.get("security_violation_materialized", ""),
                    ]
                )

    md = [
        "| plan_id | variant | rac_decision | server_call_issued | side_effect_exists | security_violation_materialized |",
        "|---------|---------|--------------|--------------------|--------------------|-------------------------------|",
    ]
    for r in rows_out:
        md.append("| " + " | ".join(r) + " |")
    md.extend(
        [
            "",
            "*Representative `write_file` steps from `mcp_real_filesystem_planner_v06_results.csv` "
            "(attack_write_leak_plan S02, attack_mixed_list_then_write_plan S02).*",
        ]
    )
    (ART_TBL / "table_real_mcp_side_effects.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def figure_experiment_overview(ov: dict | None, planner: dict | None, oh: dict | None, plt) -> None:
    if not ov:
        return
    ct = ov.get("controlled_tracebench") or {}
    mr_fr = ct.get("match_rate_FULL_RAC", 1.0)
    oh_p95 = (oh or {}).get("p95_step_ms")
    fr_blk = (planner or {}).get("full_rac_blocked_side_effects")
    nr_mat = (planner or {}).get("no_rac_materialized_side_effects")

    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.2))

    axes[0].bar([0], [mr_fr], color="#3d5a80", width=0.5)
    axes[0].set_xticks([0])
    axes[0].set_xticklabels(["FULL_RAC"])
    axes[0].set_ylim(0, 1.1)
    axes[0].set_ylabel("Match rate")
    axes[0].set_title("TraceBench\n(controlled)")
    axes[0].grid(axis="y", linestyle="--", alpha=0.35)

    if oh_p95 is not None:
        axes[1].bar([0], [float(oh_p95)], color="#5c677d", width=0.5)
        axes[1].set_xticks([0])
        axes[1].set_xticklabels(["p95 step"])
        axes[1].set_ylabel("ms")
        axes[1].set_title("Overhead\n(microbenchmark)")
    axes[1].grid(axis="y", linestyle="--", alpha=0.35)

    if fr_blk is not None and nr_mat is not None:
        axes[2].bar(
            [0, 1],
            [int(fr_blk), int(nr_mat)],
            color=["#3d5a80", "#c08552"],
            width=0.55,
        )
        axes[2].set_xticks([0, 1])
        axes[2].set_xticklabels(["FULL_RAC\nblocked writes", "NO_RAC\nmaterialized"])
        axes[2].set_ylabel("Count")
        axes[2].set_title("Planner MCP\n(side effects)")
    axes[2].grid(axis="y", linestyle="--", alpha=0.35)

    fig.suptitle("Experiment overview (from aggregated JSON summaries)", fontsize=11, y=1.02)
    fig.tight_layout()
    _save_figure(fig, "figure_experiment_overview")


def categorize_family(name: str) -> tuple[str, str]:
    """Return (coverage_category, representative predicate / theme)."""
    if name.startswith("benign_"):
        return ("benign", "Benign internal workflows (oracle ALLOW)")
    if name.startswith("action_escalation"):
        return ("action_escalation", "ActionCoverage / unauthorized leaf escalation")
    if name.startswith("resource_expansion") or name.startswith("resource_origin"):
        return ("resource", "ResourceContainment / ResourceOrigin")
    if name.startswith("purpose_drift"):
        return ("purpose", "PurposePreservation")
    if name.startswith("condition_weakening"):
        return ("condition", "ConditionPreservation")
    if name.startswith("delegation_"):
        return ("delegation", "DelegationNonAmplification")
    if name.startswith("lineage_") or name == "forged_predecessor":
        return ("lineage", "LineageValidity")
    if name.startswith("output_anchor_") or name == "invalid_output_anchor":
        return ("output_anchor", "OutputAnchorIntegrity")
    if name.startswith("multi_predecessor"):
        return ("multi_predecessor", "MultiPredecessorUnsupported")
    return ("other", "misc")


def table_tracebench_coverage(tb: dict) -> None:
    families = list((tb.get("per_family_results") or {}).keys())
    buckets: dict[str, list[str]] = defaultdict(list)
    pred: dict[str, str] = {}
    for fam in families:
        cat, hint = categorize_family(fam)
        buckets[cat].append(fam)
        pred.setdefault(cat, hint)

    lines = [
        "| family (coverage category) | count | representative predicate / violation type |",
        "|------------------------------|-------|---------------------------------------------|",
    ]
    for cat in sorted(buckets.keys()):
        lines.append(f"| {cat} | {len(buckets[cat])} | {pred.get(cat, '')} |")
    lines.extend(
        [
            "",
            "*Derived from `rac_tracebench_v06_summary.json` → `per_family_results` keys (32 traces); "
            "predicates align with `rac_tracebench_v06_analysis.md` §3.*",
        ]
    )
    (ART_TBL / "table_tracebench_coverage.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def table_variant_summary(tb: dict) -> None:
    mrv = tb.get("match_rate_by_variant") or {}
    fnv = tb.get("false_negative_by_variant") or {}
    fpv = tb.get("false_positive_by_variant") or {}
    lines = [
        "| variant | match_rate | false_negative | false_positive |",
        "|---------|------------|----------------|----------------|",
    ]
    for v in sorted(mrv.keys()):
        lines.append(f"| `{v}` | {mrv[v]} | {fnv.get(v)} | {fpv.get(v)} |")
    (ART_TBL / "table_variant_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def table_real_mcp_planner_summary(planner: dict | None) -> None:
    if not planner:
        (ART_TBL / "table_real_mcp_planner_summary.md").write_text(
            "*Input `mcp_real_filesystem_planner_v06_summary.json` missing.*\n",
            encoding="utf-8",
        )
        return
    body = json.dumps(planner, indent=2, ensure_ascii=False)
    text = (
        "### Planner filesystem MCP (`mcp_real_filesystem_planner_v06_summary.json`)\n\n"
        "```json\n"
        f"{body}\n```\n"
    )
    (ART_TBL / "table_real_mcp_planner_summary.md").write_text(text, encoding="utf-8")


def table_experiment_overview(ov: dict | None) -> None:
    if not ov:
        (ART_TBL / "table_experiment_overview.md").write_text(
            "*`rac_experiment_overview.json` missing.*\n", encoding="utf-8"
        )
        return
    ct = ov.get("controlled_tracebench") or {}
    ab = ov.get("ablation") or {}
    oh = ov.get("overhead") or {}
    rf = ov.get("real_filesystem_mcp")
    pl = ov.get("planner_style_filesystem_mcp")

    lines = [
        "| Section | Metric | Value |",
        "|---------|--------|-------|",
        "| TraceBench | total_traces | "
        f"{ct.get('total_traces')} |",
        "| TraceBench | match_rate FULL_RAC | "
        f"{ct.get('match_rate_FULL_RAC')} |",
        "| TraceBench | match_rate NO_RAC | "
        f"{ct.get('match_rate_NO_RAC')} |",
        "| Ablation | lowest RAC_WITHOUT match rates | "
        f"{ab.get('match_rate_by_variant_RAC_WITHOUT')} |",
        "| Overhead | p95_step_ms | "
        f"{oh.get('p95_step_ms')} |",
        "| Overhead | mean_trace_ms | "
        f"{oh.get('mean_trace_ms')} |",
        "| Real MCP demo | total_scenarios | "
        f"{(rf or {}).get('total_scenarios', 'n/a')} |",
        "| Planner | total_plans | "
        f"{(pl or {}).get('total_plans', 'n/a')} |",
        "| Planner | match_rate FULL_RAC / NO_RAC | "
        f"{(pl or {}).get('match_rate_by_variant')} |",
        "| Planner | side_effect_materialized FULL_RAC / NO_RAC | "
        f"{(pl or {}).get('side_effect_materialized_count_by_variant')} |",
        "| Planner | full_rac_blocked_side_effects | "
        f"{(pl or {}).get('full_rac_blocked_side_effects', 'n/a')} |",
        "| Planner | no_rac_materialized_side_effects | "
        f"{(pl or {}).get('no_rac_materialized_side_effects', 'n/a')} |",
        "",
        "*Source: `results/rac_experiment_overview.json`.*",
    ]
    (ART_TBL / "table_experiment_overview.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_readme(missing: list[str]) -> None:
    lines = [
        "# Experiment artifacts (figures & tables)",
        "",
        "Generated by `scripts/build_rac_paper_artifacts.py` from committed `results/` outputs only.",
        "Regenerate: `python3 scripts/build_rac_paper_artifacts.py`",
        "",
        "Requires **matplotlib** (`pip install 'matplotlib>=3.8,<4'` or OS package `python3-matplotlib`).",
        "",
        "## Figures (`artifacts/figures/`)",
        "",
        "| File | Description | Inputs |",
        "|------|-------------|--------|",
        "| `figure_ablation_match_rate.{png,pdf,svg}` | Bar chart: match rate per TraceBench variant | `rac_tracebench_v06_summary.json` |",
        "| `figure_overhead_latency.{png,pdf,svg}` | Bar chart: p50/p95/p99/mean step & mean trace latency (ms) | `rac_tracebench_v06_overhead_summary.json` |",
        "| `figure_real_mcp_side_effects.{png,pdf,svg}` | Grouped bars: server calls issued vs write side-effects materialized (FULL_RAC vs NO_RAC) | `mcp_real_filesystem_planner_v06_summary.json` |",
        "| `figure_experiment_overview.{png,pdf,svg}` | Three-panel overview (TraceBench FULL_RAC rate, overhead p95 step, planner side-effect counts) | `rac_experiment_overview.json`, overhead & planner summaries |",
        "",
        "### Axis label abbreviations (Figure 1)",
        "",
        "- **STATIC_AL** = STATIC_TOOL_ALLOWLIST",
        "- **w/o \\*** = RAC_WITHOUT_* ablations (ACTION, RES_ORIG, OUT_ANC, LINEAGE, PURPOSE, COND, DELEG)",
        "",
        "## Tables (`artifacts/tables/`)",
        "",
        "| File | Inputs |",
        "|------|--------|",
        "| `table_ablation_match_rate.md` | tracebench summary |",
        "| `table_overhead_summary.md` | overhead summary |",
        "| `table_tracebench_coverage.md` | tracebench summary (+ analysis cross-check) |",
        "| `table_variant_summary.md` | tracebench summary |",
        "| `table_real_mcp_side_effects.md` | planner results CSV |",
        "| `table_real_mcp_planner_summary.md` | planner summary JSON |",
        "| `table_experiment_overview.md` | rac_experiment_overview.json |",
        "",
        "## Expected inputs under `results/`",
        "",
        "Optional reads used when present: "
        "`rac_tracebench_v06_results.csv`, `rac_tracebench_v06_analysis.md`, "
        "`mcp_real_filesystem_v06_summary.json`, `mcp_real_filesystem_v06_results.csv`, "
        "`rac_experiment_overview.md`.",
        "",
    ]
    if missing:
        lines.extend(["## Missing inputs at generation time", "", *[f"- `{m}`" for m in missing], ""])
    else:
        lines.extend(["## Missing inputs at generation time", "", "- *(none)*", ""])
    README.parent.mkdir(parents=True, exist_ok=True)
    README.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    _ensure_dirs()
    plt = _require_matplotlib()
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": "#222222",
            "axes.labelsize": 10,
            "axes.titlesize": 10,
            "font.size": 10,
            "figure.dpi": 120,
        }
    )

    missing = [str(p.relative_to(ROOT)) for p in INPUTS.values() if not p.is_file()]

    tb = _load_json(INPUTS["tracebench_summary"])
    oh = _load_json(INPUTS["overhead_summary"])
    planner = _load_json(INPUTS["planner_summary"])
    ov = _load_json(INPUTS["overview_json"])

    if tb:
        figure_ablation_match_rate(tb, plt)
        table_tracebench_coverage(tb)
        table_variant_summary(tb)
    else:
        print("WARN: rac_tracebench_v06_summary.json missing; skipping Fig1 & TraceBench tables.", file=sys.stderr)

    if oh:
        figure_overhead_latency(oh, plt)
    else:
        print("WARN: overhead summary missing; skipping Fig2.", file=sys.stderr)

    figure_real_mcp_side_effects(planner, plt)
    figure_experiment_overview(ov, planner, oh, plt)

    table_real_mcp_planner_summary(planner)
    table_experiment_overview(ov)

    plt.close("all")

    write_readme(missing)
    print(f"Wrote figures under {ART_FIG.relative_to(ROOT)}")
    print(f"Wrote tables under {ART_TBL.relative_to(ROOT)}")
    print(f"Wrote {README.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
