# Overhead / latency artifacts (paper v3)

## 1. Source files

- `results/rac_tracebench_v06_overhead.csv`
- `results/rac_tracebench_v06_overhead_summary.json`

## 2. Overhead CSV columns (header order)

```
iteration, trace_id, trace_family, step_index, step_name, output_anchor_precheck_ms, lineage_resolution_ms, resource_origin_verification_ms, action_coverage_check_ms, precommit_check_ms, total_step_ms, total_trace_ms, replay_total_ms
```

## 3. Field checklist

| Field / concept | Present? | Notes |
| --- | ---: | --- |
| action_coverage_check_ms (often empty) | yes | Column present; values empty (rolled into `precommit_check_ms`). |
| decision (ALLOW/BLOCK) | no | Not logged in overhead CSV; Figure B uses benign vs violation from `trace_family`. |
| lineage_resolution_ms | yes |  |
| output_anchor_precheck_ms | yes |  |
| precommit_check_ms | yes |  |
| predecessor / lineage status columns | no | No dedicated lineage-state column; use `lineage_resolution_ms` timing only. |
| resource_origin_verification_ms (often empty) | yes | Column present; values empty (rolled into `precommit_check_ms`). |
| step_index (or step_id) | yes |  |
| step_name | yes |  |
| total_step_ms | yes |  |
| total_trace_ms or replay_total_ms | yes |  |
| trace_family | yes |  |
| trace_id | yes |  |

## 4. Figures generated

- **Figure A** `fig_overhead_breakdown.{pdf,png,svg}` — RAC step-level component distributions (horizontal boxplots, log-scaled x). **Suggested: main text** (core breakdown).
- **Figure B** `fig_step_latency_by_decision.{pdf,png,svg}` — `total_step_ms` by **benign vs violation** (fallback; no step-level decision in CSV). **Suggested: appendix** unless you add a join story.
- **Figure C** `fig_trace_latency_by_length.{pdf,png,svg}` — `total_trace_ms` by trace length bucket. **Suggested: appendix** (supporting).

## 5. Tables

- `../tables_paper_v3/table_overhead_by_component.md` — percentiles by component (+ total trace).
- `../tables_paper_v3/table_overhead_grouping.md` — benign vs violation step stats.

## 6. Figures not generated (if any)


## 7. Overhead rerun

**No rerun** — existing CSV was used.

## 8. Recommendation (main text)

**Figure A (`fig_overhead_breakdown`)** is the strongest overhead figure for the paper body: it shows RAC-internal splits (output-anchor / lineage / precommit vs total step) on the same instrumented path.

