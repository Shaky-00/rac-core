| Evaluation | Scale | Main result |
|------------|-------|-------------|
| Controlled TraceBench | 32 traces × 13 variants | FULL_RAC 32/32, FP=0, FN=0 |
| Ablation | Baselines + 7 component removals | Removing components increases missed-block rate vs FULL |
| Overhead | 100 iterations / 7600 step records | p95 step ≈ 0.219 ms (coarse instrumentation) |
| Real MCP planner | 6 plans / 10 steps per variant (FULL vs NO_RAC) | NO_RAC materializes 2 unauthorized writes; FULL_RAC 0 |

