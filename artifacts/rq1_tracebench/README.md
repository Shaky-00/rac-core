# RQ1 — TraceBench paired/core conformance

**Expected file:** `expected/paired_core_summary.json`

- **Type:** Paired/core **44-case** expected summary (17 oracle-ALLOW, 27 oracle-BLOCK).
- **Paper use:** Core-suite conformance (Table III); FULL_RAC should show zero missed blocks on oracle-BLOCK traces.
- **Replay:** Requires external paired TraceBench under `$RAC_DATA_DIR/tracebench/paired/` (not included in `rac-core`).

**Scripts (require `RAC_DATA_DIR`):**

```bash
export RAC_DATA_DIR=/path/to/rac-data-review
bash scripts/run_tracebench.sh
# or: python3 scripts/run_tracebench.py
```

**Outputs:** `results/` (gitignored), e.g. `tracebench_paired_summary.json`.

**Note:** `false_negative_by_variant` in summary JSON divides by **44** traces; paper missed-block rates for the core suite use **27** oracle-BLOCK as the denominator.
