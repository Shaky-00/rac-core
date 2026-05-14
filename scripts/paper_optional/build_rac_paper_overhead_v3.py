#!/usr/bin/env python3
"""Optional helper for overhead figures and tables from TraceBench overhead CSV/summary.

Does not modify RAC core. Does not re-run experiments unless
``--allow-rerun-overhead`` is passed and the CSV is missing or unusable.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from io_paths import OptionalMergedResultPath, repo_root

ROOT = repo_root()
R = OptionalMergedResultPath()
FIG = ROOT / "artifacts" / "generated" / "figures_v3"
TBL = ROOT / "artifacts" / "generated" / "tables_v3"
README = FIG / "README_overhead_artifacts.md"

CSV_PATH = R / "rac_tracebench_v06_overhead.csv"
SUMMARY_PATH = R / "rac_tracebench_v06_overhead_summary.json"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_ms(raw: str | None) -> float | None:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_ms_zero(raw: str | None) -> float:
    v = _parse_ms(raw)
    return 0.0 if v is None else v


def _pctile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return float("nan")
    xs = sorted_vals
    n = len(xs)
    if n == 1:
        return xs[0]
    idx = (n - 1) * (q / 100.0)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return xs[lo]
    return xs[lo] + (xs[hi] - xs[lo]) * (idx - lo)


def _stats(vals: list[float]) -> dict[str, float]:
    if not vals:
        return {"p50_ms": float("nan"), "p95_ms": float("nan"), "p99_ms": float("nan"), "mean_ms": float("nan"), "max_ms": float("nan")}
    s = sorted(vals)
    return {
        "p50_ms": _pctile(s, 50),
        "p95_ms": _pctile(s, 95),
        "p99_ms": _pctile(s, 99),
        "mean_ms": sum(s) / len(s),
        "max_ms": s[-1],
    }


def _benign_or_violation(trace_family: str) -> str:
    return "benign" if trace_family.startswith("benign_") else "violation"


def _require_plt():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        return plt
    except ImportError as e:
        print("ERROR: matplotlib required (pip install 'matplotlib>=3.8,<4').", file=sys.stderr)
        raise SystemExit(1) from e


def _paper_style(plt) -> None:
    import matplotlib as mpl

    mpl.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "font.size": 8.5,
            "axes.labelsize": 9,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "axes.edgecolor": "#333333",
            "axes.linewidth": 0.75,
            "grid.color": "#bbbbbb",
            "grid.linestyle": "--",
            "grid.linewidth": 0.45,
            "grid.alpha": 0.55,
        }
    )


def _save_fig(fig, stem: Path) -> None:
    import matplotlib.pyplot as _plt

    stem.parent.mkdir(parents=True, exist_ok=True)
    kw = dict(bbox_inches="tight", pad_inches=0.1)
    fig.savefig(stem.with_suffix(".png"), dpi=220, **kw)
    fig.savefig(stem.with_suffix(".pdf"), **kw)
    fig.savefig(stem.with_suffix(".svg"), **kw)
    fig.clear()
    _plt.close(fig)


def _boxplot_compat(ax, data, positions, *, vert: bool, labels: list[str] | None, **kwargs: Any) -> None:
    try:
        ax.boxplot(data, positions=positions, vert=vert, tick_labels=labels, **kwargs)
    except TypeError:
        ax.boxplot(data, positions=positions, vert=vert, labels=labels, **kwargs)


def load_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        rows = list(r)
        fields = list(r.fieldnames or [])
    return rows, fields


def csv_ok(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 20:
        return False
    rows, fields = load_rows(path)
    need = {
        "output_anchor_precheck_ms",
        "lineage_resolution_ms",
        "precommit_check_ms",
        "total_step_ms",
        "total_trace_ms",
        "trace_id",
        "trace_family",
        "step_index",
    }
    if not need <= set(fields):
        return False
    return bool(rows)


def maybe_rerun(allow: bool) -> bool:
    if csv_ok(CSV_PATH):
        return False
    if not allow:
        print(
            f"ERROR: missing or invalid overhead CSV: {CSV_PATH}\n"
            "  Pass --allow-rerun-overhead to regenerate (needs RAC_TRACEBENCH_ROOT).",
            file=sys.stderr,
        )
        raise SystemExit(2)
    cmd = [sys.executable, str(ROOT / "scripts" / "run_rac_tracebench_overhead.py"), "--iterations", "100"]
    subprocess.run(cmd, cwd=str(ROOT), check=True)
    if not csv_ok(CSV_PATH):
        print("ERROR: overhead CSV still invalid after rerun.", file=sys.stderr)
        raise SystemExit(3)
    return True


def figure_step_by_group(rows: list[dict[str, str]], plt) -> None:
    """Figure B: benign vs violation (no step-level decision in CSV)."""
    benign: list[float] = []
    viol: list[float] = []
    for row in rows:
        fam = row.get("trace_family") or ""
        try:
            t = float(row["total_step_ms"])
        except (ValueError, TypeError, KeyError):
            continue
        if _benign_or_violation(fam) == "benign":
            benign.append(t)
        else:
            viol.append(t)

    fig, ax = plt.subplots(figsize=(2.85, 2.55))
    _boxplot_compat(
        ax,
        [benign, viol],
        [1, 2],
        vert=True,
        labels=["benign", "violation"],
        patch_artist=True,
        showfliers=False,
        widths=0.52,
        medianprops={"color": "#111111", "linewidth": 1.1},
        boxprops={"facecolor": "#d4d4d4", "edgecolor": "#222222"},
        whiskerprops={"color": "#444444"},
        capprops={"color": "#444444"},
    )
    ax.set_ylabel("total_step_ms (ms)")
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    fig.tight_layout()
    _save_fig(fig, FIG / "fig_step_latency_by_decision")


def trace_length_by_trace_id(rows: list[dict[str, str]]) -> dict[str, int]:
    """Steps per trace_id from one reference iteration (0)."""
    by_trace: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        if row.get("iteration") != "0":
            continue
        tid = row.get("trace_id") or ""
        if not tid:
            continue
        try:
            si = int(row["step_index"])
        except (ValueError, TypeError, KeyError):
            continue
        by_trace[tid].add(si)
    return {tid: (max(indices) + 1) for tid, indices in by_trace.items() if indices}


def bucket_for_length(n: int) -> str:
    if n == 1:
        return "1-step"
    if n == 2:
        return "2-step"
    if n == 3:
        return "3-step"
    if n == 4:
        return "4-step"
    return "≥5-step"


def figure_trace_by_length(rows: list[dict[str, str]], plt) -> bool:
    """Figure C: total_trace_ms by trace length bucket. Returns False if insufficient."""
    lens = trace_length_by_trace_id(rows)
    if len(lens) < 2:
        return False

    bucket_samples: dict[str, list[float]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row.get("iteration", ""), row.get("trace_id", ""))
        if key in seen or key == ("", ""):
            continue
        tid = row.get("trace_id") or ""
        if tid not in lens:
            continue
        try:
            tms = float(row.get("total_trace_ms") or row.get("replay_total_ms") or 0.0)
        except (ValueError, TypeError):
            continue
        seen.add(key)
        bucket_samples[bucket_for_length(lens[tid])].append(tms)

    order = ["1-step", "2-step", "3-step", "4-step", "≥5-step"]
    data = [bucket_samples[b] for b in order if bucket_samples[b]]
    labels = [b for b in order if bucket_samples[b]]
    if len(data) < 2:
        return False

    fig, ax = plt.subplots(figsize=(3.5, 2.55))
    pos = list(range(1, len(data) + 1))
    _boxplot_compat(
        ax,
        data,
        pos,
        vert=True,
        labels=labels,
        patch_artist=True,
        showfliers=False,
        widths=0.5,
        medianprops={"color": "#111111", "linewidth": 1.1},
        boxprops={"facecolor": "#cfcfcf", "edgecolor": "#222222"},
        whiskerprops={"color": "#444444"},
        capprops={"color": "#444444"},
    )
    ax.set_ylabel("total_trace_ms (ms)")
    ax.tick_params(axis="x", labelrotation=18)
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    fig.tight_layout()
    _save_fig(fig, FIG / "fig_trace_latency_by_length")
    return True


def write_table_by_component(rows: list[dict[str, str]]) -> None:
    components = [
        ("Output-anchor precheck", "output_anchor_precheck_ms", True),
        ("Lineage resolution", "lineage_resolution_ms", True),
        ("PreCommit check", "precommit_check_ms", True),
        ("Total step", "total_step_ms", True),
        ("Total trace", "__trace__", False),
    ]
    lines = [
        "| Component | p50_ms | p95_ms | p99_ms | mean_ms | max_ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]

    # total trace deduped
    trace_vals: list[float] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row.get("iteration", ""), row.get("trace_id", ""))
        if key in seen or key == ("", ""):
            continue
        v = _parse_ms(row.get("total_trace_ms") or row.get("replay_total_ms"))
        if v is None:
            continue
        seen.add(key)
        trace_vals.append(v)

    for name, col, is_col in components:
        if is_col:
            vals = [_parse_ms_zero(row.get(col)) for row in rows]
        else:
            vals = trace_vals
        st = _stats(sorted(vals))
        lines.append(
            f"| {name} | {st['p50_ms']:.6g} | {st['p95_ms']:.6g} | {st['p99_ms']:.6g} | {st['mean_ms']:.6g} | {st['max_ms']:.6g} |"
        )
    lines.append("")
    (TBL / "table_overhead_by_component.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_table_grouping(rows: list[dict[str, str]]) -> None:
    groups: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        fam = row.get("trace_family") or ""
        g = _benign_or_violation(fam)
        try:
            groups[g].append(float(row["total_step_ms"]))
        except (ValueError, TypeError, KeyError):
            continue

    lines = [
        "| Group | mean_step_ms | p95_step_ms | count |",
        "| --- | ---: | ---: | ---: |",
    ]
    for g in ("benign", "violation"):
        vals = sorted(groups.get(g, []))
        if not vals:
            lines.append(f"| {g} | — | — | 0 |")
            continue
        st = _stats(vals)
        lines.append(f"| {g} | {st['mean_ms']:.6g} | {st['p95_ms']:.6g} | {len(vals)} |")
    lines.append("")
    lines.append("*Grouping: `benign` if `trace_family` starts with `benign_`, else `violation`. No per-step ALLOW/BLOCK in overhead CSV.*")
    (TBL / "table_overhead_grouping.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_readme(
    *,
    fields: list[str],
    present: dict[str, bool],
    gen_b: bool,
    gen_c: bool,
    rerun: bool,
) -> None:
    gen_a = True
    lines = [
        "# Overhead / latency figures (v3 pack)",
        "",
        "## 1. Source files",
        "",
        f"- `{CSV_PATH.relative_to(ROOT)}`",
        f"- `{SUMMARY_PATH.relative_to(ROOT)}`",
        "",
        "## 2. Overhead CSV columns (header order)",
        "",
        "```",
        ", ".join(fields),
        "```",
        "",
        "## 3. Field checklist",
        "",
        "| Field / concept | Present? | Notes |",
        "| --- | ---: | --- |",
    ]
    notes_map = {
        "decision (ALLOW/BLOCK)": "Not logged in overhead CSV; Figure B uses benign vs violation from `trace_family`.",
        "predecessor / lineage status columns": "No dedicated lineage-state column; use `lineage_resolution_ms` timing only.",
        "resource_origin_verification_ms (often empty)": "Column present; values empty (rolled into `precommit_check_ms`).",
        "action_coverage_check_ms (often empty)": "Column present; values empty (rolled into `precommit_check_ms`).",
    }
    for k, ok in sorted(present.items()):
        note = notes_map.get(k, "")
        lines.append(f"| {k} | {'yes' if ok else 'no'} | {note} |")
    lines.extend(
        [
            "",
            "## 4. Figures generated",
            "",
        ]
    )
    if gen_a:
        lines.append("- **Figure A** `fig_overhead_breakdown.{pdf,png,svg}` — RAC step-level component distributions (horizontal boxplots, log-scaled x).")
    if gen_b:
        lines.append("- **Figure B** `fig_step_latency_by_decision.{pdf,png,svg}` — `total_step_ms` by **benign vs violation** (fallback; no step-level decision in CSV).")
    else:
        lines.append("- **Figure B** — not generated (see §6).")
    if gen_c:
        lines.append("- **Figure C** `fig_trace_latency_by_length.{pdf,png,svg}` — `total_trace_ms` by trace length bucket.")
    else:
        lines.append("- **Figure C** — not generated (see §6).")
    lines.extend(
        [
            "",
            "## 5. Tables",
            "",
            "- `../tables_paper_v3/table_overhead_by_component.md` — percentiles by component (+ total trace).",
            "- `../tables_paper_v3/table_overhead_grouping.md` — benign vs violation step stats.",
            "",
            "## 6. Figures not generated (if any)",
            "",
        ]
    )
    if not gen_b:
        lines.append("- Figure B would require per-step `decision` (ALLOW/BLOCK) in the overhead CSV or a reliable step-level join; neither is available from committed artifact summaries alone.")
    if not gen_c:
        lines.append("- Figure C requires per-trace step counts and `total_trace_ms`; if buckets were empty or single-bucket, the figure is skipped.")
    lines.extend(
        [
            "",
            "## 7. Overhead rerun",
            "",
            ("**Rerun performed** via `scripts/run_rac_tracebench_overhead.py` (CSV was missing or invalid)." if rerun else "**No rerun** — existing CSV was used."),
            "",
            "## 8. Figure selection",
            "",
            "**Figure A (`fig_overhead_breakdown`)** highlights RAC-internal splits (output-anchor / lineage / precommit vs total step) on the instrumented replay path.",
            "",
        ]
    )
    README.write_text("\n".join(lines) + "\n", encoding="utf-8")


def figure_overhead_breakdown(rows: list[dict[str, str]], plt) -> None:
    """Figure A: horizontal boxplots per component; log x to span sub-ms and ms-scale."""
    import numpy as np

    oa = [_parse_ms_zero(row.get("output_anchor_precheck_ms")) for row in rows]
    lin = [_parse_ms_zero(row.get("lineage_resolution_ms")) for row in rows]
    pc = [_parse_ms_zero(row.get("precommit_check_ms")) for row in rows]
    tot = [_parse_ms_zero(row.get("total_step_ms")) for row in rows]

    eps = 1e-6
    data_plot = [
        np.maximum(np.array(oa, dtype=float), eps),
        np.maximum(np.array(lin, dtype=float), eps),
        np.maximum(np.array(pc, dtype=float), eps),
        np.maximum(np.array(tot, dtype=float), eps),
    ]
    labels = [
        "Output-anchor precheck",
        "Lineage resolution",
        "PreCommit check",
        "Total step",
    ]
    positions = [4, 3, 2, 1]

    fig, ax = plt.subplots(figsize=(4.6, 2.65))
    b = ax.boxplot(
        data_plot,
        positions=positions,
        vert=False,
        widths=0.55,
        patch_artist=True,
        showfliers=False,
        medianprops={"color": "#111111", "linewidth": 1.1},
        boxprops={"facecolor": "#d0d0d0", "edgecolor": "#222222"},
        whiskerprops={"color": "#444444"},
        capprops={"color": "#444444"},
    )
    ax.set_yticks(positions)
    ax.set_yticklabels(labels)
    for i, box in enumerate(b["boxes"]):
        if i == 3:
            box.set_facecolor("#b8b8b8")
            box.set_hatch("//")

    ax.set_xlabel("Latency (ms, log scale)")
    ax.set_xscale("log")
    ax.xaxis.grid(True, which="both")
    ax.set_axisbelow(True)
    ax.annotate(
        "Zeros in CSV → 10⁻⁶ ms for log axis.",
        xy=(0.02, 0.02),
        xycoords="axes fraction",
        fontsize=6.5,
        color="#555555",
    )
    fig.tight_layout()
    _save_fig(fig, FIG / "fig_overhead_breakdown")


def audit_fields(fieldnames: list[str]) -> dict[str, bool]:
    fset = set(fieldnames)
    return {
        "output_anchor_precheck_ms": "output_anchor_precheck_ms" in fset,
        "lineage_resolution_ms": "lineage_resolution_ms" in fset,
        "precommit_check_ms": "precommit_check_ms" in fset,
        "total_step_ms": "total_step_ms" in fset,
        "total_trace_ms or replay_total_ms": ("total_trace_ms" in fset or "replay_total_ms" in fset),
        "trace_id": "trace_id" in fset,
        "trace_family": "trace_family" in fset,
        "step_index (or step_id)": "step_index" in fset or "step_id" in fset,
        "step_name": "step_name" in fset,
        "decision (ALLOW/BLOCK)": "decision" in fset,
        "predecessor / lineage status columns": any(
            x in fset
            for x in ("predecessor_status", "lineage_status", "predecessor", "lineage_state")
        ),
        "resource_origin_verification_ms (often empty)": "resource_origin_verification_ms" in fset,
        "action_coverage_check_ms (often empty)": "action_coverage_check_ms" in fset,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--allow-rerun-overhead", action="store_true")
    args = p.parse_args()

    FIG.mkdir(parents=True, exist_ok=True)
    TBL.mkdir(parents=True, exist_ok=True)

    rerun = maybe_rerun(args.allow_rerun_overhead)
    rows, fieldnames = load_rows(CSV_PATH)
    present = audit_fields(fieldnames)

    plt = _require_plt()
    _paper_style(plt)

    figure_overhead_breakdown(rows, plt)
    figure_step_by_group(rows, plt)
    gen_c = figure_trace_by_length(rows, plt)

    write_table_by_component(rows)
    write_table_grouping(rows)

    write_readme(
        fields=fieldnames,
        present=present,
        gen_b=True,
        gen_c=gen_c,
        rerun=rerun,
    )

    print(f"Wrote figures under {FIG}")
    print(f"Wrote tables under {TBL}")
    print(f"Wrote {README}")


if __name__ == "__main__":
    main()
