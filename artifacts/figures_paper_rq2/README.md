# RQ2 — missed-block rate (compact)

| Output | Description |
|--------|-------------|
| `fig_missed_block_rate_compact.pdf` / `.png` | **v1:** missed-block rate over **all 32 traces** (= `false_negative_by_variant` × 100). |
| `fig_missed_block_rate_compact_v2.pdf` / `.png` | **v2 (Fig.~2):** same false-negative **counts** (`fn × 32`), denominator **oracle-BLOCK traces only** (27): `(fn × 32) / 27 × 100`. |
| `fig_missed_block_rate_compact.tex` | v1 LaTeX snippet. |
| `fig_missed_block_rate_compact_v2.tex` | v2 LaTeX snippet + caption (`\\label{fig:ablation-missed-block-v2}`). |

Regenerate (both v1 and v2):

```bash
python3 scripts/build_rq2_missed_block_compact.py
```
