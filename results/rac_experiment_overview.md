# RAC experiment overview

Generated: `2026-05-06T09:21:19.230564Z` (reads committed ``results/*.json`` artifacts only).

## Controlled TraceBench

- **total_traces**: 32
- **FULL_RAC match_rate**: 1.0
- **NO_RAC match_rate**: 0.15625
- **ENTRY_ONLY match_rate**: 0.25
- **STATIC_TOOL_ALLOWLIST match_rate**: 0.40625
- **false_positive (FULL_RAC)**: 0.0
- **false_negative (FULL_RAC)**: 0.0
- **false_negative (NO_RAC)**: 0.84375

## Ablation (RAC_WITHOUT_*)

Match rates (controlled replay):

- **RAC_WITHOUT_ACTION**: 0.90625
- **RAC_WITHOUT_CONDITION**: 0.90625
- **RAC_WITHOUT_DELEGATION**: 0.96875
- **RAC_WITHOUT_LINEAGE**: 0.875
- **RAC_WITHOUT_OUTPUT_ANCHOR**: 0.90625
- **RAC_WITHOUT_PURPOSE**: 0.90625
- **RAC_WITHOUT_RESOURCE_ORIGIN**: 0.875

**FN signal (summary)**:
- Lowest match_rate: `0.875` (variants: RAC_WITHOUT_LINEAGE, RAC_WITHOUT_RESOURCE_ORIGIN)

## Overhead (controlled TraceBench replay)

- **iterations**: 100
- **p50_step_ms**: 0.11076350165240001
- **p95_step_ms**: 0.21913514683546956
- **p99_step_ms**: 0.2838737398269588
- **mean_step_ms**: 0.11282773631759674
- **mean_trace_ms**: 0.27738723722336545
- **coarse_grained_measurement_notes**: Fine-grained: output_anchor_precheck_ms, lineage_resolution_ms (outer resolve_predecessor only, same as TraceRunner), precommit_check_ms (entire RACPreCommitChecker.check), total_step_ms, total_trace_ms / replay_total_ms. Coarse / not instrumented separately: resource_origin_verification_ms and action_coverage_check_ms (both are included in precommit_check_ms); internal lineage resolve inside check() is not subtracted from lineage_resolution_ms.

## Real filesystem MCP (demo script)

- **total_scenarios**: 3
- **match_rate**: 1.0
- **blocked attack steps (server not called)**: 2
- **side_effect_block_success_count**: 1

## Planner-style filesystem MCP

```json
{
  "total_plans": 6,
  "total_steps_by_variant": {
    "FULL_RAC": 10,
    "NO_RAC": 10
  },
  "match_rate_by_variant": {
    "FULL_RAC": 1.0,
    "NO_RAC": 0.6
  },
  "server_call_issued_count_by_variant": {
    "FULL_RAC": 6,
    "NO_RAC": 10
  },
  "side_effect_materialized_count_by_variant": {
    "FULL_RAC": 0,
    "NO_RAC": 2
  },
  "full_rac_blocked_side_effects": 2,
  "no_rac_materialized_side_effects": 2,
  "variants": [
    "FULL_RAC",
    "NO_RAC"
  ],
  "source_generated_at": "2026-05-06T09:19:25.366320Z"
}
```

## Conclusion

FULL_RAC matches controlled TraceBench expectations while weaker baselines (NO_RAC, ENTRY_ONLY, static allowlist) and RAC_WITHOUT ablations show authorization drift and missed blocks (higher false negatives). Ablation sweep indicates component necessity via match-rate drops. Replay overhead percentiles on controlled traces stay low at coarse instrumentation granularity. Real filesystem MCP runs show NO_RAC materializing unauthorized write side effects while FULL_RAC prevents them (compare planner variant summaries when present).
