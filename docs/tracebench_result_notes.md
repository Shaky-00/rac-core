# TraceBench experiment summaries

This note explains fields in summary JSON emitted by static replay scripts. Reviewer-facing runs via `scripts/run_tracebench.py` write **paired** suite files with neutral prefixes:

## Typical output files

- `tracebench_paired_summary.json` — full variant sweep
- `tracebench_paired_benign_summary.json` — benign-only subset metrics
- `tracebench_paired_baselines_summary.json` / `tracebench_paired_ablations_summary.json` — split runs
- `rac_tracebench_v1_expanded_*` — expanded suite (+ optional composite overlay)

## Missed-block metrics (expanded summaries)

Expanded experiment summaries add **`missed_block_by_variant`**: per variant,

- `missed_block_count` — oracle BLOCK workflows where the variant ALLOWed
- `missed_block_rate` — `missed_block_count / block_cases`
- `oracle_block_denominator` — equals `block_cases` (from oracle labels)

Legacy field **`false_negative_by_variant`** still uses **all traces** as denominator (`missed / total_cases`).

## False-negative rate: paired summary JSON vs paper (core only)

For the **44-case / 27 oracle-BLOCK** paired core suite, `false_negative_by_variant` in JSON used the full 44-trace denominator while paper plots often normalize by 27. **Expanded replay** uses `include_mixed=true` plus the composite overlay (~1248 workflows, ~1008 oracle-BLOCK). Do not reuse paired-suite denominators on expanded outputs.

## Main paired summary JSON

Key fields:

- `match_rate_by_variant`, `false_negative_by_variant`, `false_positive_by_variant`
- `per_family_results`, `missed_block_by_variant` (when present)
- `matched_oracle` counts per row in CSV companion file

Row-level detail: `tracebench_paired_results.csv` (or `tracebench_paired_baselines_results.csv` for baseline-only runs).

## Regression checking

1. Re-run the same command with the **same** bundle path (`RAC_TRACEBENCH_ROOT` or `RAC_DATA_DIR`).
2. Compare `artifacts/results/..._summary.json` to `artifacts/expected/summaries/...` when provided.
3. **Oracle alignment** (`matched_oracle`, missed-block **counts**) should agree for the same bundle and revision. **Latency-only** artifacts are environment-dependent.

## Non-regression artifacts

- **Latency and overhead CSV/JSON:** machine-dependent; use oracle alignment for strict checks.
