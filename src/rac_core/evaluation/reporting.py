"""Stage 9B: aggregate latency CSV samples into paper-style tables and figures."""

from __future__ import annotations

import csv
import io
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from rac_core.evaluation.latency import percentile

# Deep macaron: brighter than flat grey, still low-saturation / paper-safe
_COLOR_LINE_MEDIAN = "#4A9B87"
_COLOR_LINE_P95 = "#D4925C"
_COLOR_LINE_P99 = "#7E7AB8"

_BAR_COLORS = (
    "#4A9B87",
    "#D4925C",
    "#7E7AB8",
    "#5BA3C9",
)

_COMPONENT_DISPLAY_LABELS: dict[str, str] = {
    "construct_event": "Event construction",
    "tool_run": "Tool execution",
    "verify_anchor": "Anchor verification",
    "precommit": "Pre-commit check",
}


def read_latency_csv(path: Path) -> list[dict[str, str]]:
    """Read benchmark CSV; values are raw strings (empty = missing)."""
    text = path.read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader]


def _parse_float(cell: str) -> float | None:
    if cell is None or (isinstance(cell, str) and not cell.strip()):
        return None
    return float(cell)


def _parse_int(cell: str) -> int | None:
    if cell is None or (isinstance(cell, str) and not cell.strip()):
        return None
    return int(cell, 10)


def _parse_metadata(cell: str) -> dict[str, Any]:
    if not cell or not cell.strip():
        return {}
    try:
        return json.loads(cell)
    except json.JSONDecodeError:
        return {}


def _stats(values: list[float]) -> dict[str, float | int]:
    if not values:
        raise ValueError("no values for statistics")
    xs = sorted(values)
    return {
        "n": len(xs),
        "mean_ms": float(statistics.mean(xs)),
        "median_ms": float(statistics.median(xs)),
        "p95_ms": float(percentile(xs, 0.95)),
        "p99_ms": float(percentile(xs, 0.99)),
        "min_ms": float(xs[0]),
        "max_ms": float(xs[-1]),
    }


def aggregate_workflow_scaling(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """One summary row per workflow_length over pooled per-step ``total_ms``."""
    by_len: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        wl = _parse_int(row.get("workflow_length", "") or "")
        if wl is None:
            continue
        t = _parse_float(row.get("total_ms", "") or "")
        if t is None:
            continue
        by_len[wl].append(t)
    out: list[dict[str, Any]] = []
    for wl in sorted(by_len):
        st = _stats(by_len[wl])
        out.append(
            {
                "workflow_length": wl,
                "n": st["n"],
                "mean_ms": round(st["mean_ms"], 4),
                "median_ms": round(st["median_ms"], 4),
                "p95_ms": round(st["p95_ms"], 4),
                "p99_ms": round(st["p99_ms"], 4),
                "min_ms": round(st["min_ms"], 4),
                "max_ms": round(st["max_ms"], 4),
            }
        )
    return out


DECISION_SCENARIO_LABELS: dict[str, str] = {
    "decision_path_benign_read_summarize": "benign",
    "decision_path_action_escalation_external_email": "action_escalation",
    "decision_path_resource_expansion_file_b": "resource_expansion",
    "decision_path_forged_predecessor": "forged_predecessor",
}

_DECISION_ORDER: tuple[str, ...] = tuple(DECISION_SCENARIO_LABELS)


def aggregate_decision_paths(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Per decision-path scenario: end-to-end run latency stats."""
    by_scen: dict[str, list[float]] = defaultdict(list)
    decisions: dict[str, str] = {}
    for row in rows:
        scen = (row.get("scenario") or "").strip()
        if not scen:
            continue
        t = _parse_float(row.get("total_ms", "") or "")
        if t is None:
            continue
        by_scen[scen].append(t)
        dec = (row.get("decision") or "").strip()
        if dec:
            decisions[scen] = dec

    def _sort_key(s: str) -> tuple[int, str]:
        if s in _DECISION_ORDER:
            return (_DECISION_ORDER.index(s), s)
        return (len(_DECISION_ORDER), s)

    out: list[dict[str, Any]] = []
    for scen in sorted(by_scen, key=_sort_key):
        st = _stats(by_scen[scen])
        label = DECISION_SCENARIO_LABELS.get(scen, scen)
        out.append(
            {
                "path": label,
                "scenario_key": scen,
                "decision": decisions.get(scen, ""),
                "n": st["n"],
                "mean_ms": round(st["mean_ms"], 4),
                "median_ms": round(st["median_ms"], 4),
                "p95_ms": round(st["p95_ms"], 4),
                "p99_ms": round(st["p99_ms"], 4),
            }
        )
    return out


def aggregate_predecessor_resolution(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    by_n: dict[int, list[float]] = defaultdict(list)
    rules: dict[int, str | None] = {}
    decisions: dict[int, str] = {}
    for row in rows:
        n = _parse_int(row.get("predecessor_count", "") or "")
        if n is None:
            continue
        t = _parse_float(row.get("total_ms", "") or "")
        if t is None:
            continue
        by_n[n].append(t)
        meta = _parse_metadata(row.get("metadata_json", "") or "")
        br = meta.get("blocked_rule")
        if br is not None and n not in rules:
            rules[n] = str(br) if br else None
        dec = (row.get("decision") or "").strip()
        if dec:
            decisions[n] = dec
    out: list[dict[str, Any]] = []
    for n in sorted(by_n):
        st = _stats(by_n[n])
        out.append(
            {
                "predecessor_count": n,
                "decision": decisions.get(n, ""),
                "blocked_rule": rules.get(n, ""),
                "n": st["n"],
                "mean_ms": round(st["mean_ms"], 4),
                "median_ms": round(st["median_ms"], 4),
                "p95_ms": round(st["p95_ms"], 4),
                "p99_ms": round(st["p99_ms"], 4),
                "min_ms": round(st["min_ms"], 4),
                "max_ms": round(st["max_ms"], 4),
            }
        )
    return out


def aggregate_component_breakdown(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Per component: pooled timings from all measured steps/repeats."""
    components: dict[str, list[float]] = {
        "construct_event": [],
        "tool_run": [],
        "verify_anchor": [],
        "precommit": [],
    }
    for row in rows:
        for key, col in (
            ("construct_event", "event_construction_ms"),
            ("verify_anchor", "output_anchor_verification_ms"),
            ("precommit", "precommit_check_ms"),
        ):
            v = _parse_float(row.get(col, "") or "")
            if v is not None:
                components[key].append(v)
        meta = _parse_metadata(row.get("metadata_json", "") or "")
        tv = meta.get("tool_execution_ms")
        if isinstance(tv, (int, float)):
            components["tool_run"].append(float(tv))
    out: list[dict[str, Any]] = []
    order = ["construct_event", "tool_run", "verify_anchor", "precommit"]
    for name in order:
        vals = components[name]
        if not vals:
            out.append(
                {
                    "component": name,
                    "n": 0,
                    "mean_ms": 0.0,
                    "median_ms": 0.0,
                    "p95_ms": 0.0,
                    "p99_ms": 0.0,
                }
            )
            continue
        st = _stats(vals)
        out.append(
            {
                "component": name,
                "n": st["n"],
                "mean_ms": round(st["mean_ms"], 4),
                "median_ms": round(st["median_ms"], 4),
                "p95_ms": round(st["p95_ms"], 4),
                "p99_ms": round(st["p99_ms"], 4),
            }
        )
    return out


def summary_dicts_to_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    keys = list(rows[0].keys())
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=keys)
    w.writeheader()
    for r in rows:
        w.writerow({k: r[k] for k in keys})
    return buf.getvalue()


def summary_dicts_to_markdown(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    keys = list(rows[0].keys())

    def esc(s: object) -> str:
        t = str(s).replace("|", "\\|")
        return t.replace("\n", " ")

    header = "| " + " | ".join(keys) + " |"
    sep = "| " + " | ".join("---" for _ in keys) + " |"
    body = ["| " + " | ".join(esc(r[k]) for k in keys) + " |" for r in rows]
    return "\n".join([header, sep, *body]) + "\n"


def _tex_esc(s: object) -> str:
    t = str(s)
    return (
        t.replace("\\", "\\textbackslash{}")
        .replace("_", "\\_")
        .replace("%", "\\%")
        .replace("&", "\\&")
        .replace("#", "\\#")
    )


def summary_dicts_to_latex_tabular(rows: list[dict[str, Any]]) -> str:
    """Minimal ``tabular`` only (no table float)."""
    if not rows:
        return ""
    keys = list(rows[0].keys())
    n = len(keys)
    spec = "r" * n
    lines = [f"\\begin{{tabular}}{{{spec}}}"]
    lines.append(" & ".join(_tex_esc(k) for k in keys) + " \\\\")
    lines.append("\\hline")
    for r in rows:
        lines.append(" & ".join(_tex_esc(r[k]) for k in keys) + " \\\\")
    lines.append("\\end{tabular}")
    return "\n".join(lines) + "\n"


def _apply_academic_matplotlib_style() -> None:
    import matplotlib as mpl

    mpl.rcParams.update(
        {
            "figure.dpi": 150,
            "savefig.dpi": 150,
            "font.size": 8.5,
            "axes.titlesize": 9,
            "axes.labelsize": 8.5,
            "legend.fontsize": 7.5,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "axes.grid": True,
            "grid.alpha": 0.22,
            "grid.linestyle": "--",
            "axes.facecolor": "white",
            "figure.facecolor": "white",
            "axes.edgecolor": "#4a4a4a",
            "axes.linewidth": 0.65,
            "lines.linewidth": 1.35,
            "lines.markersize": 4.5,
        }
    )


def _style_log_x_integer_ticks(ax, tick_positions: list[int]) -> None:
    """Log-scaled x with major ticks/labels only at ``tick_positions`` (integers)."""
    from matplotlib.ticker import NullFormatter, NullLocator, ScalarFormatter

    if not tick_positions:
        return
    tick_positions = sorted(set(tick_positions))
    ax.set_xscale("log")
    ax.set_xticks(tick_positions)
    ax.set_xticklabels([str(v) for v in tick_positions])
    ax.xaxis.set_minor_locator(NullLocator())
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.xaxis.set_major_formatter(ScalarFormatter())
    lo, hi = min(tick_positions), max(tick_positions)
    ax.set_xlim(lo * 0.92, hi * 1.06)


# Canonical benchmark grid for predecessor log-axis ticks (subset shown per summary)
_PREDECESSOR_COUNT_TICKS = (1, 2, 4, 8, 16, 32)


def plot_workflow_scaling(summary: list[dict[str, Any]], out_path: Path) -> None:
    import matplotlib.pyplot as plt

    if not summary:
        return
    _apply_academic_matplotlib_style()
    lengths = [int(r["workflow_length"]) for r in summary]
    med = [float(r["median_ms"]) for r in summary]
    p95 = [float(r["p95_ms"]) for r in summary]
    p99 = [float(r["p99_ms"]) for r in summary]
    positions = list(range(len(lengths)))

    fig, ax = plt.subplots(figsize=(3.45, 2.2), constrained_layout=True)
    ax.plot(positions, med, marker="o", color=_COLOR_LINE_MEDIAN, label="median")
    ax.plot(positions, p95, marker="s", color=_COLOR_LINE_P95, label="p95", linestyle="--")
    ax.plot(positions, p99, marker="^", color=_COLOR_LINE_P99, label="p99", linestyle=":")
    ax.set_xscale("linear")
    ax.set_xticks(positions)
    ax.set_xticklabels([str(v) for v in lengths])
    ax.set_xlim(positions[0] - 0.35, positions[-1] + 0.35)
    ax.set_xlabel("workflow length (steps)")
    ax.set_ylabel("latency (ms)")
    ax.set_title("Per-step latency vs. workflow length")
    ax.legend(frameon=False, loc="best")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, format="png", bbox_inches="tight")
    plt.close(fig)


def plot_predecessor_resolution(summary: list[dict[str, Any]], out_path: Path) -> None:
    import matplotlib.pyplot as plt

    if not summary:
        return
    _apply_academic_matplotlib_style()
    xs = [int(r["predecessor_count"]) for r in summary]
    med = [float(r["median_ms"]) for r in summary]
    p95 = [float(r["p95_ms"]) for r in summary]
    p99 = [float(r["p99_ms"]) for r in summary]

    fig, ax = plt.subplots(figsize=(3.45, 2.2), constrained_layout=True)
    ax.plot(xs, med, marker="o", color=_COLOR_LINE_MEDIAN, label="median")
    ax.plot(xs, p95, marker="s", color=_COLOR_LINE_P95, label="p95", linestyle="--")
    ax.plot(xs, p99, marker="^", color=_COLOR_LINE_P99, label="p99", linestyle=":")
    pred_ticks = [t for t in _PREDECESSOR_COUNT_TICKS if t in set(xs)]
    if not pred_ticks:
        pred_ticks = list(xs)
    _style_log_x_integer_ticks(ax, pred_ticks)
    ax.set_xlabel("predecessor count (input anchors)")
    ax.set_ylabel("latency (ms)")
    ax.set_title("End-to-end latency vs. fan-in")
    ax.legend(frameon=False, loc="best")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, format="png", bbox_inches="tight")
    plt.close(fig)


def plot_component_breakdown(summary: list[dict[str, Any]], out_path: Path) -> None:
    import matplotlib.pyplot as plt

    if not summary:
        return
    _apply_academic_matplotlib_style()
    keys = [str(r["component"]) for r in summary]
    labels = [_COMPONENT_DISPLAY_LABELS.get(k, k) for k in keys]
    means = [float(r["mean_ms"]) for r in summary]
    colors = [_BAR_COLORS[i % len(_BAR_COLORS)] for i in range(len(summary))]

    fig, ax = plt.subplots(figsize=(3.45, 2.2), constrained_layout=True)
    x = range(len(labels))
    ax.bar(
        x,
        means,
        color=colors,
        edgecolor="#5c5c5c",
        linewidth=0.45,
    )
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=22, ha="right")
    ax.set_ylabel("mean latency (ms)")
    ax.set_title("Component breakdown (mean)")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, format="png", bbox_inches="tight")
    plt.close(fig)


def _write_triplet(
    stem: str,
    rows: list[dict[str, Any]],
    out_dir: Path,
    *,
    written: list[Path],
) -> None:
    base = out_dir / stem
    p_csv = base.with_suffix(".csv")
    p_md = Path(str(base) + ".md")
    p_tex = Path(str(base) + ".tex")
    p_csv.write_text(summary_dicts_to_csv(rows), encoding="utf-8")
    p_md.write_text(summary_dicts_to_markdown(rows), encoding="utf-8")
    p_tex.write_text(summary_dicts_to_latex_tabular(rows), encoding="utf-8")
    written.extend([p_csv, p_md, p_tex])


def generate_all_latency_reports(
    perf_dir: Path,
    *,
    log: Callable[[str], None] | None = None,
) -> list[Path]:
    """Read raw latency CSVs under ``perf_dir``; write summaries + figures next to them."""
    log = log or (lambda m: None)
    written: list[Path] = []

    def phase(i: int, total: int, name: str) -> None:
        log(f"[{i}/{total}] processing {name}...")

    total = 4

    phase(1, total, "workflow scaling")
    wf_rows = read_latency_csv(perf_dir / "latency_workflow_scaling.csv")
    wf_sum = aggregate_workflow_scaling(wf_rows)
    _write_triplet("latency_workflow_scaling_summary", wf_sum, perf_dir, written=written)
    plot_workflow_scaling(wf_sum, perf_dir / "latency_workflow_scaling.png")
    written.append(perf_dir / "latency_workflow_scaling.png")

    phase(2, total, "decision paths")
    dp_rows = read_latency_csv(perf_dir / "latency_decision_paths.csv")
    dp_sum = aggregate_decision_paths(dp_rows)
    _write_triplet("latency_decision_paths_summary", dp_sum, perf_dir, written=written)

    phase(3, total, "predecessor resolution")
    pr_rows = read_latency_csv(perf_dir / "latency_predecessor_resolution.csv")
    pr_sum = aggregate_predecessor_resolution(pr_rows)
    _write_triplet("latency_predecessor_resolution_summary", pr_sum, perf_dir, written=written)
    plot_predecessor_resolution(pr_sum, perf_dir / "latency_predecessor_resolution.png")
    written.append(perf_dir / "latency_predecessor_resolution.png")

    phase(4, total, "component breakdown")
    bd_rows = read_latency_csv(perf_dir / "latency_breakdown.csv")
    bd_sum = aggregate_component_breakdown(bd_rows)
    _write_triplet("latency_breakdown_summary", bd_sum, perf_dir, written=written)
    plot_component_breakdown(bd_sum, perf_dir / "latency_breakdown.png")
    written.append(perf_dir / "latency_breakdown.png")

    return written
