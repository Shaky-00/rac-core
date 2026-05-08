#!/usr/bin/env python3
"""RQ2 compact missed-block figures for ACSAC single-column layout.

Reads ``results/rac_tracebench_v06_summary.json`` only (no rerun). Two layouts:

- **v1:** missed-block rate over all 32 traces (= ``false_negative_by_variant`` × 100).
- **v2:** same false-negative *counts* (``fn × 32``), normalized by **oracle-BLOCK**
  trace count only (27): ``(fn × 32) / 27 × 100``.

Two stacked horizontal-bar panels: baselines vs component ablations.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = ROOT / "results" / "rac_tracebench_v06_summary.json"
OUT_DIR = ROOT / "artifacts" / "figures_paper_rq2"

# TraceBench v0.6: 32 traces total, 27 oracle-BLOCK (violation) traces (see metadata).
N_TRACES_TOTAL = 32
N_ORACLE_BLOCK_TRACES = 27

BASELINE_KEYS = [
    ("FULL_RAC", "Full"),
    ("NO_RAC", "No RAC"),
    ("ENTRY_ONLY", "Entry-only"),
    ("STATIC_TOOL_ALLOWLIST", "Static AL"),
]

# v2 y-axis labels (document asks for "Full RAC")
BASELINE_KEYS_V2 = [
    ("FULL_RAC", "Full RAC"),
    ("NO_RAC", "No RAC"),
    ("ENTRY_ONLY", "Entry-only"),
    ("STATIC_TOOL_ALLOWLIST", "Static AL"),
]

ABLATION_KEYS = [
    ("RAC_WITHOUT_ACTION", "-Action"),
    ("RAC_WITHOUT_RESOURCE_ORIGIN", "-Origin"),
    ("RAC_WITHOUT_OUTPUT_ANCHOR", "-Anchor"),
    ("RAC_WITHOUT_LINEAGE", "-Lineage"),
    ("RAC_WITHOUT_PURPOSE", "-Purpose"),
    ("RAC_WITHOUT_CONDITION", "-Condition"),
    ("RAC_WITHOUT_DELEGATION", "-Delegation"),
]

COLOR_BASELINE = "#3a4550"
COLOR_ABLATION = "#c9d2da"
EDGE = "#2a2a2a"
HATCH_ABLATION = "///"


def _load_summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def _fn_pct_all_traces(fnv: dict[str, float], key: str) -> float:
    return float(fnv[key]) * 100.0


def _fn_pct_oracle_block_only(fnv: dict[str, float], key: str) -> float:
    """(false_negative_count / 27) * 100 with count = false_negative * 32."""
    fn_rate = float(fnv[key])
    fn_count = fn_rate * N_TRACES_TOTAL
    return (fn_count / float(N_ORACLE_BLOCK_TRACES)) * 100.0


def _save(fig, stem: Path) -> None:
    stem.parent.mkdir(parents=True, exist_ok=True)
    kw = dict(bbox_inches="tight", pad_inches=0.05)
    fig.savefig(stem.with_suffix(".pdf"), **kw)
    fig.savefig(stem.with_suffix(".png"), dpi=220, **kw)


def _draw_figure(
    baseline_vals: list[float],
    baseline_lbl: list[str],
    ab_vals: list[float],
    ab_lbl: list[str],
    xlabel: str,
):
    import matplotlib as mpl

    mpl.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec

    mpl.rcParams.update(
        {
            "font.family": "serif",
            "font.size": 7.5,
            "axes.labelsize": 8,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "axes.linewidth": 0.75,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )

    fig = plt.figure(figsize=(3.45, 4.05))
    gs = gridspec.GridSpec(
        2,
        1,
        figure=fig,
        height_ratios=[len(baseline_vals), len(ab_vals)],
        hspace=0.35,
    )

    ax0 = fig.add_subplot(gs[0, 0])
    ax1 = fig.add_subplot(gs[1, 0], sharex=ax0)

    ymax = max(baseline_vals + ab_vals)
    xmax = min(105.0, ymax * 1.06 + 3.0)

    def panel_barh(
        ax,
        vals: list[float],
        labels: list[str],
        facecolor: str,
        *,
        hatch: str | None,
        baseline_panel: bool,
    ) -> None:
        n = len(vals)
        y = list(range(n))
        heights = 0.68
        widths = [max(v, 0.0) for v in vals]
        bars = ax.barh(
            y,
            widths,
            height=heights,
            color=facecolor,
            edgecolor=EDGE,
            linewidth=0.45,
            hatch=hatch if hatch else None,
        )
        if hatch:
            for b in bars:
                b.set_edgecolor(EDGE)
                b.set_linewidth(0.45)

        ax.set_yticks(y)
        ax.set_yticklabels(labels)
        ax.invert_yaxis()
        ax.set_xlim(0, xmax)
        ax.tick_params(axis="y", length=0)
        ax.xaxis.grid(True, linestyle=":", linewidth=0.45, color="#aaaaaa", alpha=0.85)
        ax.set_axisbelow(True)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)

        for yi, v in zip(y, vals):
            txt = f"{v:.1f}%"
            x_text = v + xmax * 0.012 if v > 0 else xmax * 0.018
            if v == 0.0:
                x_text = xmax * 0.018
            ax.text(
                x_text,
                yi,
                txt,
                va="center",
                ha="left",
                fontsize=7,
                color="#111111",
            )

        title = "Baselines" if baseline_panel else "Component ablations"
        ax.set_title(title, loc="left", fontsize=8.5, color="#222222", pad=5)

    panel_barh(ax0, baseline_vals, baseline_lbl, COLOR_BASELINE, hatch=None, baseline_panel=True)
    panel_barh(ax1, ab_vals, ab_lbl, COLOR_ABLATION, hatch=HATCH_ABLATION, baseline_panel=False)

    ax1.set_xlabel(xlabel)

    plt.setp(ax0.get_xticklabels(), visible=False)

    fig.align_xlabels([ax0, ax1])
    fig.subplots_adjust(left=0.22, right=0.98, top=0.96, bottom=0.09)
    return fig


def write_latex_v1(out_path: Path) -> None:
    tex = r"""% RQ2 missed-block rate — rate over all 32 traces (suite-wide false-negative rate).
\begin{figure}[t]
\centering
\includegraphics[width=\columnwidth]{figure/fig_missed_block_rate_compact.pdf}
\caption{Missed-block rate under baselines and component ablations. A missed block is an oracle-BLOCK trace that a variant incorrectly allows. Full RAC misses no blocking case, whereas weaker baselines and component-disabled variants miss drift cases that require the removed evidence source.}
\label{fig:ablation-missed-block}
\end{figure}
"""
    out_path.write_text(tex, encoding="utf-8")


def write_latex_v2(out_path: Path) -> None:
    tex = r"""% RQ2 missed-block rate — normalized by oracle-BLOCK traces only ($n{=}27$).
\begin{figure}[t]
\centering
\includegraphics[width=\columnwidth]{figure/fig_missed_block_rate_compact_v2.pdf}
\caption{Missed-block rate \emph{among oracle-BLOCK traces} ($n{=}27$). The denominator is the set of TraceBench traces whose oracle decision is BLOCK; benign (oracle-ALLOW) traces are excluded. Each rate is $\text{FN}/27$, where $\text{FN}$ is the count of oracle-BLOCK traces incorrectly allowed (equivalently $\text{false\_negative}\times 32$ under the full suite). Full RAC yields no false negatives on violation traces; weaker baselines and component-disabled variants allow a fraction of those violations.}
\label{fig:ablation-missed-block-v2}
\end{figure}
"""
    out_path.write_text(tex, encoding="utf-8")


def main() -> int:
    if not SUMMARY_PATH.is_file():
        print(f"ERROR: missing {SUMMARY_PATH}", file=sys.stderr)
        return 2

    summary = _load_summary()
    fnv = summary.get("false_negative_by_variant") or {}
    for k, _ in BASELINE_KEYS + ABLATION_KEYS:
        if k not in fnv:
            print(f"ERROR: variant not in summary: {k}", file=sys.stderr)
            return 3

    import matplotlib.pyplot as plt

    # --- v1: all 32 traces ---
    base_v1 = [_fn_pct_all_traces(fnv, k) for k, _ in BASELINE_KEYS]
    lbl_v1 = [lbl for _, lbl in BASELINE_KEYS]
    ab_v1 = [_fn_pct_all_traces(fnv, k) for k, _ in ABLATION_KEYS]
    ab_lbl = [lbl for _, lbl in ABLATION_KEYS]

    fig1 = _draw_figure(
        base_v1,
        lbl_v1,
        ab_v1,
        ab_lbl,
        "Missed-block rate (%)",
    )
    stem1 = OUT_DIR / "fig_missed_block_rate_compact"
    _save(fig1, stem1)
    plt.close(fig1)
    write_latex_v1(OUT_DIR / "fig_missed_block_rate_compact.tex")

    # --- v2: oracle-BLOCK traces only (27) ---
    base_v2 = [_fn_pct_oracle_block_only(fnv, k) for k, _ in BASELINE_KEYS_V2]
    lbl_v2 = [lbl for _, lbl in BASELINE_KEYS_V2]
    ab_v2 = [_fn_pct_oracle_block_only(fnv, k) for k, _ in ABLATION_KEYS]

    fig2 = _draw_figure(
        base_v2,
        lbl_v2,
        ab_v2,
        ab_lbl,
        "Missed-block rate among oracle-BLOCK traces (%)",
    )
    stem2 = OUT_DIR / "fig_missed_block_rate_compact_v2"
    _save(fig2, stem2)
    plt.close(fig2)
    write_latex_v2(OUT_DIR / "fig_missed_block_rate_compact_v2.tex")

    print(f"Wrote {stem1.with_suffix('.pdf')}")
    print(f"Wrote {stem2.with_suffix('.pdf')}")
    print(f"Wrote {OUT_DIR / 'fig_missed_block_rate_compact_v2.tex'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
