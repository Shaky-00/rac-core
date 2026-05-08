| field | value |
|-------|-------|
| iterations | 100 |
| total_runs | 3200 |
| total_step_records | 7600 |
| p50_step_ms | 0.11076350165240001 |
| p95_step_ms | 0.21913514683546956 |
| p99_step_ms | 0.2838737398269588 |
| mean_step_ms | 0.11282773631759674 |
| max_step_ms | 2.7515400033735204 |
| mean_trace_ms | 0.27738723722336545 |
| p95_trace_ms | 0.47741894795763073 |

**coarse_grained_measurement_notes**

Fine-grained: output_anchor_precheck_ms, lineage_resolution_ms (outer resolve_predecessor only, same as TraceRunner), precommit_check_ms (entire RACPreCommitChecker.check), total_step_ms, total_trace_ms / replay_total_ms. Coarse / not instrumented separately: resource_origin_verification_ms and action_coverage_check_ms (both are included in precommit_check_ms); internal lineage resolve inside check() is not subtracted from lineage_resolution_ms.

**Figure (overhead) display**

- Step panel: overall `total_step_ms` (all step records); y-axis clipped to 0–0.8 ms for the body of the distribution.
- Trace panel: overall `total_trace_ms`, one value per `(iteration, trace_id)`; y-axis clipped to 0–1.1 ms.
- Tukey fliers not drawn (`showfliers=False`); full data retained; global max remains in `max_step_ms` above.
- On-figure note: max step ≈ 2.75 ms (see table).

