| Component | p50_ms | p95_ms | p99_ms | mean_ms |
| --- | ---: | ---: | ---: | ---: |
| Output-anchor precheck | 0.001415 | 0.0030131 | 0.0166964 | 0.00204643 |
| Lineage resolution | 0.007791 | 0.012163 | 0.0180003 | 0.00782346 |
| PreCommit check | 0.10028 | 0.205385 | 0.265152 | 0.102067 |
| Total step | 0.110764 | 0.219135 | 0.283874 | 0.112828 |
| Total trace | 0.26536 | 0.477419 | 0.626904 | 0.277387 |

*Source: `results/rac_tracebench_v06_overhead.csv`. Step-level components treat empty cells as 0 ms (same as v3 paper table). Total trace: one sample per (iteration, trace_id).*
