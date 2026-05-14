# Artifacts layout (anonymous minimal artifact)

| Path | Role |
|------|------|
| `expected/summaries/` | Small reference **JSON** summaries for optional comparison |
| `expected/data/` | Optional small auxiliary files (e.g. benign suite CSV); large CSVs are not shipped—run core scripts first |
| `artifacts/results/` | **Runtime outputs** (gitignored except `.gitkeep`; no root `results/` directory) |
| `generated/` | Optional outputs from helper scripts under `scripts/paper_optional/` (tracked as empty + `.gitkeep`) |

Core reproduction writes to `artifacts/results/` via `scripts/run_*.sh`. Optional table or figure regeneration lives in `scripts/paper_optional/` and writes to `artifacts/generated/`.
