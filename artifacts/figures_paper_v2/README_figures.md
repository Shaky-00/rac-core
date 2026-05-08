# Paper figures v2 (`figures_paper_v2`)

Grayscale-friendly assets for two-column security paper layouts. Caption text in the paper should explain measurement caveats (especially overhead instrumentation).

No overhead rerun; existing `results/rac_tracebench_v06_overhead.csv` was used.

## Figure A — `fig_missed_block_rate.*`

- **Data:** `results/rac_tracebench_v06_summary.json` → `false_negative_by_variant` (missed-block rate).
- **Fields:** per-variant aggregate false-negative rate over 32 traces; companion table adds `match_rate`, `false_positive`.
- **Design:** Two visually separated groups (baselines vs RAC_WITHOUT ablations); hatch on ablation bars for B/W distinction.
- **Placement:** **Main text** (core controlled evaluation).

### Single-column ACSAC revision — `../figures_paper_rq2/fig_missed_block_rate_compact.*`

- **Script:** `scripts/build_rq2_missed_block_compact.py` (reads the same summary JSON; **does not** alter rates).
- **Design:** Two **stacked** horizontal-bar panels (baselines above, component ablations below), shared **x** = missed-block rate (%); compact labels; LaTeX snippet `figures_paper_rq2/fig_missed_block_rate_compact.tex`.
- **Use when:** IEEE/ACSAC **single-column** figure (`[t]` + `\columnwidth`), replacing the older wide vertical-bar `figures_paper_v2/fig_missed_block_rate.*` layout.

### Oracle-BLOCK–normalized (recommended for RQ2 text) — `fig_missed_block_rate_compact_v2.*`

- **Normalization:** Missed-block rate **among oracle-BLOCK traces only** ($n{=}27$): $\text{FN}/27$ with $\text{FN}=\text{false\_negative}\times 32$ (same counts as the suite-wide FN rate on 32 traces).
- **Files:** `figures_paper_rq2/fig_missed_block_rate_compact_v2.pdf` / `.png`, `fig_missed_block_rate_compact_v2.tex`.

## Figure B — `fig_overhead_distribution.*`

- **Data:** `results/rac_tracebench_v06_overhead.csv`, summary fields in `results/rac_tracebench_v06_overhead_summary.json`.
- **Fields:** overall `total_step_ms` (all rows); overall `total_trace_ms` deduped per `(iteration, trace_id)`.
- **Design:** dual-panel overall boxplots (step + trace); y-limits clip view; fliers hidden; max in table
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
