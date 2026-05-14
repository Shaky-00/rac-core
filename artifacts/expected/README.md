# Expected reference snapshots

- **`summaries/`** — small JSON summaries (TraceBench, overhead summary, MCP summaries) for optional comparison after a fresh run.
- **`data/`** — optional small auxiliary files listed in the root `.gitignore` allowlist. Large CSVs (e.g. full overhead grid) are **not** committed; generate them with `bash scripts/run_tracebench_overhead.sh` or place them locally under `artifacts/expected/data/` if you need optional `paper_optional` scripts offline.

Fresh experiment output belongs in **`artifacts/results/`** (gitignored).
