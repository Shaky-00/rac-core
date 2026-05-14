# Optional helper scripts

These scripts are **not** part of the minimal anonymous artifact evaluation path. They may require
`matplotlib`, extra CSV/JSON inputs under `artifacts/results/` (from running the core `scripts/run_*.sh`
entry points) or under `artifacts/expected/summaries` / `artifacts/expected/data`, and they write
under `artifacts/generated/` by default.

Run from repository root, for example:

```bash
python3 scripts/paper_optional/build_rq2_missed_block_compact.py
python3 scripts/paper_optional/build_rac_paper_artifacts.py
```

Input resolution is implemented in `io_paths.py` (prefers `artifacts/results/`, then `artifacts/expected/`).
