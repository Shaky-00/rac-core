#!/usr/bin/env python3
"""Build v2 paper figures and tables under artifacts/*_paper_v2/ (no RAC core edits).

Reads committed ``results/*.json`` and ``results/*.csv`` only. Optionally re-runs the
overhead microbenchmark if per-step CSV is missing or unusable (``--allow-rerun-overhead``).
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
FIG_V2 = ROOT / "artifacts" / "figures_paper_v2"
TBL_V2 = ROOT / "artifacts" / "tables_paper_v2"
README_FIG = FIG_V2 / "README_figures.md"

INPUTS = {
    "tracebench_summary": RESULTS / "rac_tracebench_v06_summary.json",
    "overhead_summary": RESULTS / "rac_tracebench_v06_overhead_summary.json",
    "overhead_csv": RESULTS / "rac_tracebench_v06_overhead.csv",
    "planner_summary": RESULTS / "mcp_real_filesystem_planner_v06_summary.json",
    "planner_results": RESULTS / "mcp_real_filesystem_planner_v06_results.csv",
    "overview_json": RESULTS / "rac_experiment_overview.json",
}

GROUP1_ORDER = [
    "FULL_RAC",
    "NO_RAC",
    "ENTRY_ONLY",
    "STATIC_TOOL_ALLOWLIST",
]
GROUP2_ORDER = [
    "RAC_WITHOUT_ACTION",
    "RAC_WITHOUT_RESOURCE_ORIGIN",
    "RAC_WITHOUT_OUTPUT_ANCHOR",
    "RAC_WITHOUT_LINEAGE",
    "RAC_WITHOUT_PURPOSE",
    "RAC_WITHOUT_CONDITION",
    "RAC_WITHOUT_DELEGATION",
]

X_LABELS = {
    "FULL_RAC": "FULL",
    "NO_RAC": "NO",
    "ENTRY_ONLY": "Entry",
    "STATIC_TOOL_ALLOWLIST": "Static",
    "RAC_WITHOUT_ACTION": "-Act",
    "RAC_WITHOUT_RESOURCE_ORIGIN": "-ResOrig",
    "RAC_WITHOUT_OUTPUT_ANCHOR": "-Anchor",
    "RAC_WITHOUT_LINEAGE": "-Line",
    "RAC_WITHOUT_PURPOSE": "-Purpose",
    "RAC_WITHOUT_CONDITION": "-Cond",
    "RAC_WITHOUT_DELEGATION": "-Del",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _trace_category(trace_family: str) -> str:
    if trace_family.startswith("benign_"):
        return "benign"
    if trace_family.startswith("action_"):
        return "action"
    if trace_family.startswith("resource_"):
        return "resource"
    if trace_family.startswith("purpose_"):
        return "purpose"
    if trace_family.startswith("condition_"):
        return "condition"
    if trace_family.startswith("delegation_"):
        return "delegation"
    if trace_family.startswith("lineage_"):
        return "lineage"
    if trace_family.startswith("output_anchor_") or trace_family == "invalid_output_anchor":
        return "output_anchor"
    if trace_family.startswith("multi_predecessor_"):
        return "multi_predecessor"
    if trace_family == "forged_predecessor":
        return "lineage"
    return "other"


def _require_matplotlib():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        return plt
    except ImportError as e:
        print(
            "ERROR: matplotlib required. pip install 'matplotlib>=3.8,<4'\n",
            file=sys.stderr,
        )
        raise SystemExit(1) from e


def _paper_rcparams(plt):
    import matplotlib as mpl

    mpl.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "font.size": 9,
            "axes.labelsize": 9.5,
            "axes.titlesize": 9,
            "xtick.labelsize": 8.5,
            "ytick.labelsize": 8.5,
            "legend.fontsize": 8.5,
            "axes.edgecolor": "#333333",
            "axes.linewidth": 0.8,
            "grid.color": "#bbbbbb",
            "grid.linestyle": "--",
            "grid.linewidth": 0.5,
            "grid.alpha": 0.6,
        }
    )


def _save_figure(fig, stem: Path) -> None:
    import matplotlib.pyplot as _plt

    stem.parent.mkdir(parents=True, exist_ok=True)
    kw = dict(bbox_inches="tight", pad_inches=0.12)
    fig.savefig(stem.with_suffix(".png"), dpi=220, **kw)
    fig.savefig(stem.with_suffix(".pdf"), **kw)
    fig.savefig(stem.with_suffix(".svg"), **kw)
    fig.clear()
    _plt.close(fig)


def _annotate_bars(ax, bars, values, *, as_percent: bool, percent_decimals: int = 2) -> None:
    for bar, v in zip(bars, values):
        h = bar.get_height()
        if as_percent:
            t = f"{100.0 * v:.{percent_decimals}f}%"
        else:
            t = f"{v:.0f}"
        ax.annotate(
            t,
            xy=(bar.get_x() + bar.get_width() / 2, h),
            xytext=(0, 2),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=7.5,
            color="#222222",
        )


def figure_missed_block_rate(summary: dict, plt) -> None:
    fnv = summary.get("false_negative_by_variant") or {}
    mrv = summary.get("match_rate_by_variant") or {}
    fpv = summary.get("false_positive_by_variant") or {}

    variants: list[str] = []
    for v in GROUP1_ORDER + GROUP2_ORDER:
        if v in fnv:
            variants.append(v)

    rates = [float(fnv[v]) for v in variants]
    labels = [X_LABELS.get(v, v) for v in variants]

    # x positions with a gap between group1 and group2
    g1n = len([v for v in GROUP1_ORDER if v in fnv])
    g2n = len([v for v in GROUP2_ORDER if v in fnv])
    gap = 1.0
    x1 = list(range(g1n))
    x2 = [g1n + gap + i for i in range(g2n)]
    xpos = x1 + x2
    sep_x = (x1[-1] + x2[0]) / 2.0 if x1 and x2 else None

    fig_w = 6.8
    fig, ax = plt.subplots(figsize=(fig_w, 3.05))
    colors = ["#6e6e6e"] * g1n + ["#9a9a9a"] * g2n
    hatches = [""] * g1n + ["///"] * g2n
    bars = ax.bar(xpos, rates, color=colors, edgecolor="#222222", linewidth=0.65, width=0.72)
    for bar, h in zip(bars, hatches):
        if h:
            bar.set_hatch(h)

    ax.set_xticks(xpos)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Missed-block rate")
    ax.set_ylim(0, 1.0)
    ax.set_yticks([0.0, 0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
    if sep_x is not None:
        ax.axvline(sep_x, color="#555555", linestyle="-", linewidth=0.7, zorder=0)
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    _annotate_bars(ax, bars, rates, as_percent=True, percent_decimals=1)

    # Group names below tick labels
    if x1 and x2:
        mid1 = (x1[0] + x1[-1]) / 2.0
        mid2 = (x2[0] + x2[-1]) / 2.0
        ax.annotate(
            "Baselines",
            xy=(mid1, 0.0),
            xycoords=("data", "axes fraction"),
            xytext=(0, -32),
            textcoords="offset points",
            ha="center",
            va="top",
            fontsize=8,
            color="#333333",
        )
        ax.annotate(
            "Component ablations",
            xy=(mid2, 0.0),
            xycoords=("data", "axes fraction"),
            xytext=(0, -32),
            textcoords="offset points",
            ha="center",
            va="top",
            fontsize=8,
            color="#333333",
        )

    fig.tight_layout(rect=[0, 0.12, 1, 1])
    _save_figure(fig, FIG_V2 / "fig_missed_block_rate")

    # table
    lines = [
        "| variant | false_negative | match_rate | false_positive |",
        "|---------|----------------|------------|----------------|",
    ]
    for v in GROUP1_ORDER + GROUP2_ORDER:
        if v not in fnv:
            continue
        lines.append(
            f"| `{v}` | {fnv.get(v)} | {mrv.get(v)} | {fpv.get(v)} |"
        )
    (TBL_V2 / "table_variant_missed_block.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_overhead_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        rows = list(r)
        fields = r.fieldnames or []
    return rows, list(fields)


def _overhead_csv_ok(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 50:
        return False
    rows, fields = _load_overhead_csv(path)
    need = {"total_step_ms", "total_trace_ms", "trace_family", "iteration", "trace_id"}
    if not need <= set(fields):
        return False
    if not rows:
        return False
    try:
        float(rows[0]["total_step_ms"])
        float(rows[0]["total_trace_ms"])
    except (KeyError, ValueError, TypeError):
        return False
    return True


def _maybe_rerun_overhead(allow: bool) -> bool:
    """Return True if a rerun was performed."""
    csv_p = INPUTS["overhead_csv"]
    if _overhead_csv_ok(csv_p):
        return False
    if not allow:
        print(
            f"ERROR: overhead CSV missing or unusable: {csv_p}\n"
            "  Re-run with --allow-rerun-overhead (requires RAC_TRACEBENCH_ROOT / tracebench data).",
            file=sys.stderr,
        )
        raise SystemExit(2)
    print(f"INFO: Re-running overhead script to regenerate {csv_p} ...", file=sys.stderr)
    cmd = [sys.executable, str(ROOT / "scripts" / "run_rac_tracebench_overhead.py"), "--iterations", "100"]
    subprocess.run(cmd, cwd=str(ROOT), check=True)
    if not _overhead_csv_ok(csv_p):
        print("ERROR: overhead CSV still invalid after rerun.", file=sys.stderr)
        raise SystemExit(3)
    return True


def figure_overhead_distribution(rows: list[dict[str, str]], oh_summary: dict, plt) -> str:
    """Returns description of plot style for reporting."""
    import numpy as np

    all_steps: list[float] = []
    for row in rows:
        try:
            all_steps.append(float(row["total_step_ms"]))
        except (ValueError, TypeError, KeyError):
            continue

    # trace-level: one sample per (iteration, trace_id)
    seen: set[tuple[str, str]] = set()
    all_traces: list[float] = []
    for row in rows:
        key = (row.get("iteration", ""), row.get("trace_id", ""))
        if key in seen or key == ("", ""):
            continue
        try:
            tms = float(row.get("total_trace_ms") or row.get("replay_total_ms") or 0.0)
        except (ValueError, TypeError):
            continue
        seen.add(key)
        all_traces.append(tms)

    def _boxplot_single(ax, data: list[float], *, xtick: str, facecolor: str, box_hatch: str | None) -> None:
        boxprops = {"facecolor": facecolor, "edgecolor": "#222222"}
        if box_hatch:
            boxprops["hatch"] = box_hatch
        bp_kw: dict[str, Any] = dict(
            positions=[1],
            widths=0.42,
            patch_artist=True,
            showfliers=False,
            medianprops={"color": "#111111", "linewidth": 1.2},
            boxprops=boxprops,
            whiskerprops={"color": "#222222"},
            capprops={"color": "#222222"},
        )
        try:
            ax.boxplot([data], tick_labels=[xtick], **bp_kw)
        except TypeError:
            ax.boxplot([data], labels=[xtick], **bp_kw)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.8, 2.75), sharey=False)
    _boxplot_single(ax1, all_steps, xtick="Steps", facecolor="#d8d8d8", box_hatch=None)
    ax1.set_ylabel("Latency (ms)")
    ax1.set_ylim(0, 0.8)
    ax1.yaxis.grid(True)
    ax1.set_axisbelow(True)

    _boxplot_single(ax2, all_traces, xtick="Traces", facecolor="#c8c8c8", box_hatch="///")
    ax2.set_ylabel("Latency (ms)")
    ax2.set_ylim(0, 1.1)
    ax2.yaxis.grid(True)
    ax2.set_axisbelow(True)

    max_step = float(oh_summary.get("max_step_ms") or 0.0)
    max_step_s = f"{max_step:.2f}"
    note = f"Max step = {max_step_s} ms; see Table."

    fig.tight_layout(rect=[0, 0.14, 1, 1])
    fig.text(0.5, 0.02, note, transform=fig.transFigure, ha="center", va="bottom", fontsize=7.5, color="#333333")
    _save_figure(fig, FIG_V2 / "fig_overhead_distribution")

    # table_overhead_distribution.md
    def pctile(arr: list[float], q: float) -> float:
        if not arr:
            return float("nan")
        return float(np.percentile(np.array(arr, dtype=float), q))

    notes = str(oh_summary.get("coarse_grained_measurement_notes") or "")
    tbl_lines = [
        "| field | value |",
        "|-------|-------|",
        f"| iterations | {oh_summary.get('iterations', '')} |",
        f"| total_runs | {oh_summary.get('total_runs', '')} |",
        f"| total_step_records | {oh_summary.get('total_step_records', len(all_steps))} |",
        f"| p50_step_ms | {oh_summary.get('p50_step_ms', pctile(all_steps, 50))} |",
        f"| p95_step_ms | {oh_summary.get('p95_step_ms', pctile(all_steps, 95))} |",
        f"| p99_step_ms | {oh_summary.get('p99_step_ms', pctile(all_steps, 99))} |",
        f"| mean_step_ms | {oh_summary.get('mean_step_ms', float(np.mean(all_steps)) if all_steps else '')} |",
        f"| max_step_ms | {oh_summary.get('max_step_ms', max(all_steps) if all_steps else '')} |",
        f"| mean_trace_ms | {oh_summary.get('mean_trace_ms', '')} |",
        f"| p95_trace_ms | {oh_summary.get('p95_trace_ms', '')} |",
        "",
        "**coarse_grained_measurement_notes**",
        "",
        notes,
        "",
        "**Figure (overhead) display**",
        "",
        "- Step panel: overall `total_step_ms` (all step records); y-axis clipped to 0–0.8 ms for the body of the distribution.",
        "- Trace panel: overall `total_trace_ms`, one value per `(iteration, trace_id)`; y-axis clipped to 0–1.1 ms.",
        "- Tukey fliers not drawn (`showfliers=False`); full data retained; global max remains in `max_step_ms` above.",
        f"- On-figure note: max step ≈ {max_step_s} ms (see table).",
        "",
    ]
    (TBL_V2 / "table_overhead_distribution.md").write_text("\n".join(tbl_lines) + "\n", encoding="utf-8")

    return "dual-panel overall boxplots (step + trace); y-limits clip view; fliers hidden; max in table"


def figure_real_mcp_unauthorized_writes(plt) -> None:
    import numpy as np

    planner_summary = _load_json(INPUTS["planner_summary"])
    prev = [
        int(planner_summary.get("full_rac_blocked_side_effects") or 0),
        0,
    ]
    mat = [
        int(planner_summary.get("side_effect_materialized_count_by_variant", {}).get("FULL_RAC") or 0),
        int(planner_summary.get("side_effect_materialized_count_by_variant", {}).get("NO_RAC") or 0),
    ]

    x = np.arange(2)
    width = 0.34
    fig, ax = plt.subplots(figsize=(3.35, 2.85))
    b1 = ax.bar(
        x - width / 2,
        prev,
        width,
        label="Prevented writes",
        color="#b0b0b0",
        edgecolor="#222222",
        linewidth=0.65,
    )
    b2 = ax.bar(
        x + width / 2,
        mat,
        width,
        label="Materialized writes",
        color="#6a6a6a",
        edgecolor="#222222",
        linewidth=0.65,
    )
    ax.set_xticks(x)
    ax.set_xticklabels(["FULL_RAC", "NO_RAC"], fontsize=8)
    ax.set_ylabel("Count")
    leg = ax.legend(loc="upper right", frameon=False, handlelength=1.4, borderaxespad=0.35)
    for t in leg.get_texts():
        t.set_fontsize(7)
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    ax.set_ylim(0, 2.0)
    ax.set_yticks([0, 1, 2])

    for bar, v in zip(b1, prev):
        ax.annotate(
            str(int(v)),
            xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, 2),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
        )
    for bar, v in zip(b2, mat):
        ax.annotate(
            str(int(v)),
            xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, 2),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
        )

    fig.tight_layout()
    _save_figure(fig, FIG_V2 / "fig_real_mcp_unauthorized_writes")


def table_tracebench_coverage(summary: dict) -> None:
    per = summary.get("per_family_results") or {}
    cats: dict[str, list[str]] = defaultdict(list)
    for fam in sorted(per.keys()):
        c = _trace_category(fam)
        cats[c].append(fam)

    predicates = {
        "benign": "No injected violation; benign workflow",
        "action": "Action escalation / disallowed tool path",
        "resource": "Resource expansion or unverifiable origin",
        "purpose": "Purpose drift vs declared intent",
        "condition": "Condition weakening along chain",
        "delegation": "Delegation / sub-agent boundary",
        "lineage": "Lineage / predecessor binding (incl. forged predecessor)",
        "output_anchor": "Output anchor mismatch or invalid anchor",
        "multi_predecessor": "Multi-predecessor aggregate / unsupported patterns",
    }

    lines = [
        "| Category | # Traces | Predicate / violation type |",
        "|----------|----------|------------------------------|",
    ]
    order = [
        "benign",
        "action",
        "resource",
        "purpose",
        "condition",
        "delegation",
        "lineage",
        "output_anchor",
        "multi_predecessor",
    ]
    for c in order:
        n = len(cats.get(c, []))
        lines.append(f"| {c} | {n} | {predicates.get(c, '')} |")
    lines.append("")
    lines.append(f"*Total trace families in summary: {len(per)}.*")
    (TBL_V2 / "table_tracebench_coverage_compact.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def table_experiment_overview_compact() -> None:
    lines = [
        "| Evaluation | Scale | Main result |",
        "|------------|-------|-------------|",
        "| Controlled TraceBench | 32 traces × 11 variants | FULL_RAC 32/32, FP=0, FN=0 |",
        "| Ablation | Baselines + 7 component removals | Removing components increases missed-block rate vs FULL |",
        "| Overhead | 100 iterations / 7600 step records | p95 step ≈ 0.219 ms (coarse instrumentation) |",
        "| Real MCP planner | 6 plans / 10 steps per variant (FULL vs NO_RAC) | NO_RAC materializes 2 unauthorized writes; FULL_RAC 0 |",
        "",
    ]
    (TBL_V2 / "table_experiment_overview_compact.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def table_real_mcp_write_effects() -> None:
    path = INPUTS["planner_results"]
    rows_out: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("tool_name") != "write_file":
                continue
            pid = row.get("plan_id") or ""
            if pid not in ("attack_write_leak_plan", "attack_mixed_list_then_write_plan"):
                continue
            if row.get("step_id") != "S02":
                continue
            rows_out.append(row)

    cols = [
        "plan_id",
        "variant",
        "rac_decision",
        "server_call_issued",
        "side_effect_exists",
        "security_violation_materialized",
    ]
    lines = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
    ]
    for row in rows_out:
        lines.append("| " + " | ".join(str(row.get(c, "")) for c in cols) + " |")
    lines.append("")
    (TBL_V2 / "table_real_mcp_write_effects.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_readme(overhead_plot_kind: str, overhead_rerun: bool) -> None:
    rerun_note = "Overhead CSV was regenerated via `scripts/run_rac_tracebench_overhead.py`." if overhead_rerun else "No overhead rerun; existing `results/rac_tracebench_v06_overhead.csv` was used."

    text = f"""# Paper figures v2 (`figures_paper_v2`)

Grayscale-friendly assets for two-column security paper layouts. Caption text in the paper should explain measurement caveats (especially overhead instrumentation).

{rerun_note}

## Figure A — `fig_missed_block_rate.*`

- **Data:** `results/rac_tracebench_v06_summary.json` → `false_negative_by_variant` (missed-block rate).
- **Fields:** per-variant aggregate false-negative rate over 32 traces; companion table adds `match_rate`, `false_positive`.
- **Design:** Y-axis 0–100% with ticks at 0/25/50/75/100%; thin separator between **Baselines** and **Component ablations** (group names below ticks); short x-labels (`-ResOrig`, `-Anchor`, `-Purpose`, …); hatch on ablation bars; bar labels one decimal (e.g. 84.4%).
- **Placement:** **Main text** (core controlled evaluation).

## Figure B — `fig_overhead_distribution.*`

- **Data:** `results/rac_tracebench_v06_overhead.csv`, summary fields in `results/rac_tracebench_v06_overhead_summary.json`.
- **Fields:** overall `total_step_ms` (all rows); overall `total_trace_ms` deduped per `(iteration, trace_id)`.
- **Design:** {overhead_plot_kind}
- **Placement:** **Main text** or **appendix** depending on page budget; keep `coarse_grained_measurement_notes` from the overhead table in appendix.

## Figure C — `fig_real_mcp_unauthorized_writes.*`

- **Data:** `results/mcp_real_filesystem_planner_v06_summary.json` (aggregated prevented/materialized counts).
- **Fields:** blocked unauthorized writes under FULL (`full_rac_blocked_side_effects`); materialized side effects per variant (`side_effect_materialized_count_by_variant`).
- **Design:** Grouped bars (Prevented writes / Materialized writes); x-axis `FULL_RAC` / `NO_RAC`; y-axis 0–2 integer ticks.
- **Placement:** **Main text** (real-toolchain evidence); per-step detail in `tables_paper_v2/table_real_mcp_write_effects.md`.

## Tables (`../tables_paper_v2/`)

| File | Source | Placement |
|------|--------|-----------|
| `table_variant_missed_block.md` | TraceBench summary | main text / appendix |
| `table_overhead_distribution.md` | overhead CSV + summary JSON | appendix |
| `table_tracebench_coverage_compact.md` | TraceBench summary `per_family_results` | appendix |
| `table_experiment_overview_compact.md` | curated from overview + summaries | main text (one row) or appendix |
| `table_real_mcp_write_effects.md` | planner results CSV (filtered `write_file` S02) | appendix |

## Intentionally omitted (vs older artifact passes)

- No experiment “overview” multi-panel figure.
- No single figure mixing step percentiles and mean trace latency in one bar chart.
- No rainbow / saturated multi-metric overview plots.
"""
    README_FIG.write_text(text, encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description="Build v2 paper figures/tables under artifacts/*_paper_v2/")
    p.add_argument(
        "--allow-rerun-overhead",
        action="store_true",
        help="If overhead CSV is missing or invalid, run run_rac_tracebench_overhead.py",
    )
    args = p.parse_args()

    FIG_V2.mkdir(parents=True, exist_ok=True)
    TBL_V2.mkdir(parents=True, exist_ok=True)

    overhead_rerun = _maybe_rerun_overhead(args.allow_rerun_overhead)

    plt = _require_matplotlib()
    _paper_rcparams(plt)

    tb = _load_json(INPUTS["tracebench_summary"])
    oh = _load_json(INPUTS["overhead_summary"])

    figure_missed_block_rate(tb, plt)

    csv_rows, _ = _load_overhead_csv(INPUTS["overhead_csv"])
    overhead_kind = figure_overhead_distribution(csv_rows, oh, plt)

    figure_real_mcp_unauthorized_writes(plt)

    table_tracebench_coverage(tb)
    table_experiment_overview_compact()
    table_real_mcp_write_effects()

    write_readme(overhead_kind, overhead_rerun)
    print(f"Wrote figures under {FIG_V2}")
    print(f"Wrote tables under {TBL_V2}")
    print(f"Wrote {README_FIG}")


if __name__ == "__main__":
    main()
