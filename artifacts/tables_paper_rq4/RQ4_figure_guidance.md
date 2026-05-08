# RQ4（Runtime Overhead）论文图表使用说明

本文档说明 **ACSAC 主文** 建议采用的 RQ4 素材，以及现有 overhead 图中哪些不宜原样进主文。数据均来自已提交的 TraceBench 仪器化重放（未重跑实验）。

## 不建议直接用于主文的现有图

| 现有产物 | 原因 |
|----------|------|
| `artifacts/figures_paper_v3/fig_overhead_breakdown.*` | **横轴为对数刻度**，跨数量级展示分布；对一般读者偏「技术报告」风格，且与主文常见「线性 ms」叙述不一致。 |
| `artifacts/figures_paper_v3/fig_step_latency_by_decision.*` | 按 **benign / violation** 分组，但 overhead CSV **无逐步 ALLOW/BLOCK**（README 已说明），分组实为 `trace_family` 启发式代理，**易被误读为决策路径对比**。 |
| `artifacts/figures_paper_v3/fig_trace_latency_by_length.*` | 由 **TraceBench** 按步数分桶的 trace 时长；若主文已有 **组件分解**，该图可作附录；与下述 **workflow scaling** 勿混为一谈。 |
| `latency_workflow_scaling_summary.csv` 驱动的 scaling 图 | 来自 **`artifacts/performance/`** 下另一套 **微基准**（各长度桶 **n=5/25/50**），与 TraceBench **RQ4 主叙事** 不同源；**不建议在主文作为核心 scaling 证据**。若需提及，应明确为独立 micro-benchmark 或省略。 |

## 建议进入主文的新产物

| 文件 | 用途 |
|------|------|
| `artifacts/tables_paper_rq4/table_overhead_component_summary.md` | 主文或附录 **Table**：含 **Total trace** 在内的五类组件。 |
| `artifacts/tables_paper_rq4/table_overhead_component_summary.tex` | 同上（LaTeX）。 |
| `artifacts/tables_paper_rq4/table_overhead_interval.tex` | **仅四步级组件**（无 Total trace）的 LaTeX 表；与 **interval 图**配套。 |
| `artifacts/figures_paper_rq4/fig_overhead_interval.pdf`（及 `.png`） | **推荐主文 Figure**：单栏 **horizontal interval plot**（p50 点、p50–p95 实线、p95–p99 浅虚线 + p99 端标记），无柱状图。 |
| `artifacts/figures_paper_rq4/fig_overhead_component_clean.pdf`（及 `.png`） | 备选：线性分组柱形（若审稿方坚持条形对比时使用）。 |

数据来源：`results/rac_tracebench_v06_overhead.csv`（与 `artifacts/tables_paper_v3/table_overhead_by_component.md` 的聚合语义一致：空字段按 0 ms；Total trace 按 `(iteration, trace_id)` 去重）。

## `latency_breakdown_summary.csv` 与 `rac_tracebench_v06_overhead_summary.json`

- **`latency_breakdown_summary.csv`**：列为 `construct_event` / `tool_run` / `verify_anchor` / `precommit`，**n=10**，与 TraceBench 仪器化 **不是同一套分解**；**不宜与主表混为一张「RQ4 总表」**，除非单独定义为 micro-benchmark 小节。
- **`rac_tracebench_v06_overhead_summary.json`**：提供 **全局** `p50_step_ms`、`p95_step_ms` 等与表中 **Total step** 行一致的高层摘要；主文数字以 **组件表 + 图** 为准即可。

## Trace-length scaling 清洁版（`fig_trace_latency_by_length_clean`）

**未生成。** 理由：`latency_workflow_scaling_summary.csv` 属于 **小样本、独立 workflow 微基准**，与 TraceBench 主结果 **不同源**；在主文再放一张「按长度」图易与 TraceBench 的 `fig_trace_latency_by_length` 混淆。若审稿人或附录需要 **步数分桶**，优先复用已有 **`fig_trace_latency_by_length`**（来自 `rac_tracebench_v06_overhead.csv`），而非 performance 下的 scaling 摘要。

## 推荐的最终 RQ4 组合

**推荐：1 表 + 1 图（主文）**

1. **表**：`table_overhead_interval.tex`（或补一行 **Total trace** 时改用 `table_overhead_component_summary`）— 步级分位数 + mean；**Total trace** 在正文或全量表中单独说明。  
2. **图**：`fig_overhead_interval` — 单栏 **interval plot**（非柱状图），与表一致的四组件。

**可选（附录）**：`fig_overhead_component_clean`（柱形）或 `fig_trace_latency_by_length`（v3）— 仅作补充，避免主文重复多种 latency 可视化。

## 再生命令

```bash
python3 scripts/build_rq4_paper_artifacts.py
```

仅读写 `artifacts/` 下 RQ4 产物；不调用 checker、不重跑 `run_rac_tracebench_overhead.py`。
