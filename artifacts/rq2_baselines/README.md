# RQ2 — Baseline coverage on expanded TraceBench

**Expected file:** `expected/expanded_baselines_summary.json`

- **Type:** Paper-level **expanded baseline** summary (committed reference counts).
- **Paper use:** Fig. 4 cross-check — 1248 workflows; Static+History **509/1008** missed-block (**50.5%** rate); FULL_RAC **0** missed.
- **Replay:** Full regeneration requires the **expanded** TraceBench bundle and composite overlay under `$RAC_DATA_DIR` (not included in `rac-core`).

**Script (requires `RAC_DATA_DIR`):**

```bash
export RAC_DATA_DIR=/path/to/rac-data
bash scripts/run_rq2_tracebench.sh
```

**Outputs:** `results/` (gitignored).

Reviewers without the bundle can still verify the paper’s headline counts against this committed JSON.
