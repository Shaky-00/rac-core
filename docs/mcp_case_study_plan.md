# MCP Case Study Plan

> **说明：**本文为 **工程计划 / 案例设计笔记**，与当前仓库的 **v0.6 prototype** 评估主线一致；规范级定义以外部 *RAC Technical Specification v0.6* 为准。实现索引见 [`rac_v06_alignment.md`](rac_v06_alignment.md)。

## Goal

将论文主线收敛为一个 MCP-native live enforcement case study：

- RAC 运行在 MCP client / gateway 边界
- 对 pending `tools/call` 做 pre-call enforcement
- 只有 `ALLOW` 才真正调用 MCP server
- `BLOCK` 时不发送调用，并记录 `issued_to_server=false`

## Stub MCP Servers

使用一组可控的 stub MCP servers 来承载案例，而不是依赖外部 synthetic trace 仓库。stub servers 应提供稳定、可复现实验语义，并允许精确观察 “是否真的发起了 server call”。

## MCP Tools

案例工具集合：

- `read_report`
- `search_reports`
- `summarize_report`
- `extract_metrics`
- `create_internal_report`
- `save_internal_report`
- `send_email`

这些工具应覆盖：

- 直接读取
- 搜索/检索
- 派生总结
- 结构化指标提取
- 内部写入
- 外发 disclosure

## Guarded MCP Client

实验入口应是一个 guarded MCP client，而不是离线 trace replay runner。

基本流程：

1. 应用侧产生一个待执行的 MCP 工具调用。
2. 在 `session.call_tool(...)` 之前保留 pending `tools/call`。
3. 将该 pending call 交给 Authorization Event Mapper。
4. 将 mapper 输出交给 RAC checker。
5. 根据决策决定是否真正调用 MCP server。

## Authorization Event Mapper

AEM 的职责是将：

- MCP `tool_name`
- MCP `arguments`
- trusted tool manifest

映射为 canonical authorization event。

manifest 至少应描述：

- `canonical_action`
- `resource_args`
- `artifact_args`
- `recipient_args`
- `consumes_anchor`
- `produces_anchor`
- `external_effect`
- `output_anchor_type`
- `action_relation_class`

## Enforcement Semantics

- `ALLOW`：调用 MCP server，记录 `issued_to_server=true`
- `BLOCK`：不调用 MCP server，记录 `issued_to_server=false`

重点不是只记录“理论上应拦截”，而是证明 BLOCK 时 server side effect 根本不会发生。

## Trace / Audit Record

实验记录应保留 MCP-native 字段，而不是 synthetic benchmark schema。

每次 pending call 至少记录：

- MCP tool call（名称、参数、会话上下文）
- AEM 产生的 canonical authorization event
- RAC decision
- `issued_to_server`
- 若调用发生，则记录 server response metadata

## Suggested Scenarios

- Benign read: `read_report` on authorized report
- Resource drift: authorized read A, attempted read B
- Benign derive: `read_report -> summarize_report`
- Unauthorized external disclosure: `summarize_report -> send_email`
- Internal write allowed: `create_internal_report` / `save_internal_report`
- Search boundary check: `search_reports` only within allowed corpus
- Metric extraction from authorized report, then attempted disclosure

## Main Evaluation Narrative

论文主线应聚焦：

- controlled scenarios
- taxonomy-aligned drift cases
- component ablation
- latency / overhead evaluation
- MCP-native live enforcement case study

不再依赖 synthetic external trace benchmark 或外部 trace bundle 生产链路。
