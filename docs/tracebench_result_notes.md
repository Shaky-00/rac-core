# TraceBench summary fields and comparison

This note documents the **machine-readable** TraceBench aggregates produced by `scripts/run_tracebench.sh` (and related runners). It does not replace the TraceBench bundle’s own trace/oracle definitions.

## Where summaries live

- **Reference snapshots (small JSON):** `artifacts/expected/summaries/`
- **Fresh runs:** `artifacts/results/` (default output root; gitignored except `.gitkeep`)

Typical filenames include `rac_tracebench_v06_summary.json`, `rac_tracebench_v06_benign_summary.json`, and split runs such as `rac_tracebench_v06_baselines_summary.json` / `rac_tracebench_v06_ablations_summary.json` when those scripts are used.

## Main summary JSON (`rac_tracebench_v06_summary.json`)

| Field | Meaning |
|-------|---------|
| `match_rate_by_variant` | Per checker variant: share of controlled traces whose final checker decision equals the TraceBench oracle label. |
| `false_negative_by_variant` | Per variant: rate of **oracle BLOCK** traces classified as **ALLOW** (missed blocks). |
| `false_positive_by_variant` | Per variant: rate of **oracle ALLOW** traces classified as **BLOCK** (over-blocks). |
| `per_family_results` | Map keyed by trace **family** id; each entry aggregates traces in that family (useful for coverage-style tables). |
| `benign_suite_summary` | Sub-object summarizing benign (oracle-ALLOW) traces only: admitted counts, blocked benign false positives, and benign false-positive rates per variant. |

Row-level detail for spreadsheet workflows is emitted as `rac_tracebench_v06_results.csv` alongside the summary.

## Comparing reference vs generated summaries

1. Re-run the same command (for example `bash scripts/run_tracebench.sh`) with the **same** TraceBench bundle path (`RAC_TRACEBENCH_ROOT` or the default search under `data/tracebench/` / sibling `mcp_data/`).
2. Compare `artifacts/results/rac_tracebench_v06_summary.json` to `artifacts/expected/summaries/rac_tracebench_v06_summary.json`.
3. **Oracle alignment** (`matched_oracle` / match rates / FN–FP counts) should agree for the same bundle and repository revision. **Latency-only** artifacts may differ slightly in floating-point milliseconds.

## Common benign differences

- **Latency and overhead CSV/JSON:** wall-clock and instrumented timings are environment-dependent; use oracle alignment fields for strict regression checks.
- **Path strings inside CSV:** may differ while semantic columns match.
