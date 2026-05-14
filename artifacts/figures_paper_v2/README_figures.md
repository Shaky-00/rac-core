# Paper figures v2 (`figures_paper_v2`)

Grayscale-friendly assets for two-column security paper layouts. Caption text in the paper should explain measurement caveats (especially overhead instrumentation).

No overhead rerun; existing `results/rac_tracebench_v06_overhead.csv` was used.

## Figure A — `fig_missed_block_rate.*`

- **Data:** `results/rac_tracebench_v06_summary.json` → `false_negative_by_variant` (missed-block rate).
- **Fields:** per-variant aggregate false-negative rate over 32 traces; companion table adds `match_rate`, `false_positive`.
- **Design:** Y-axis 0–100% with ticks at 0/25/50/75/100%; thin separator between **Baselines** and **Component ablations** (group names below ticks); short x-labels (`-ResOrig`, `-Anchor`, `-Purpose`, …); hatch on ablation bars; bar labels one decimal (e.g. 84.4%).
- **Placement:** **Main text** (core controlled evaluation).

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
