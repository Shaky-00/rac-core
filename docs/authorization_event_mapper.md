# Authorization Event Mapper

> **说明：**本文为 **工程补充说明**，描述与本仓库 **RAC v0.6 prototype** 一致的 MCP 侧映射思路；**不**替代仓库外部的 *RAC Technical Specification v0.6* 正文。实现与设计的逐项对照见 [`rac_v06_alignment.md`](rac_v06_alignment.md)。

## 定位

`Authorization Event Mapper`（AEM）是位于 MCP client / gateway 边界上的 **pre-call mapping layer**。

它处理的是一个 **pending `tools/call`**，而不是离线 synthetic trace benchmark。AEM 在 `session.call_tool(...)` 真正发往 MCP server 之前，基于 `tool_name + arguments + trusted tool manifest` 生成一个规范化的授权事件，再交给 RAC checker 做一致性检查。

## 为什么需要 AEM

- MCP runtime 暴露的是待调用工具名与参数，不直接携带统一的授权语义。
- 不同 MCP server 的参数命名和工具粒度不同，但 RAC checker 需要稳定的 canonical authorization event。
- 授权决策必须发生在真正调用 MCP server 之前，否则 BLOCK 无法阻止副作用发生。

因此，AEM 的职责不是“回放 benchmark trace”，而是把 **MCP-native pending call** 转换成 RAC 可消费的规范化输入。

## 核心调用路径

1. Guarded MCP client 生成一个 pending `tools/call`。
2. AEM 读取 `tool_name`、`arguments`、会话上下文和 trusted tool manifest。
3. AEM 输出 canonical authorization event。
4. RAC checker 对该事件执行 pre-call 检查。
5. 若结果为 `ALLOW`，客户端才调用 MCP server。
6. 若结果为 `BLOCK`，则不发送 `tools/call`，并记录 `issued_to_server=false`。

## Mapper 的输入

- Pending MCP `tools/call`
  - `tool_name`
  - `arguments`
- Trusted tool manifest
  - `canonical_action`
  - `resource_args`
  - `artifact_args`
  - `recipient_args`
  - `consumes_anchor`
  - `produces_anchor`
  - `external_effect`
  - `output_anchor_type`
  - `action_relation_class`
- RAC session / grant context
- Resource registry or resource resolver
- Verified input anchors / provenance state
- Optional runtime metadata
  - `session_id`
  - timestamp
  - request id

## Mapper 的输出

- `canonical_action`
- `resource_references`
- `artifact_references`
- `recipient_metadata`
- `purpose` / delegation / runtime conditions
- `input_anchors`
- expected `output_anchor` metadata
- `mapping_warnings`

这些字段应直接服务于 RAC checker，而不是服务于某个 benchmark 专用 schema。

## MCP Call Input Contract

对 AEM 来说，最小可消费输入是：

- 一个待发出的 MCP 工具调用：`tool_name` + `arguments`
- 一个可信 manifest 条目，至少定义：
  - `canonical_action`
  - `resource_args`
- 当前会话的授权边界（grant / basis / lineage state）

推荐 manifest 继续补充：

- `artifact_args`
- `recipient_args`
- `consumes_anchor`
- `produces_anchor`
- `external_effect`
- `output_anchor_type`
- `action_relation_class`

映射规则：

- `resource_args` 中声明的字段都应被完整提取，不能只取单个主资源字段。
- `artifact_args` 表示待消费的前序产物引用。
- `recipient_args` 用于外发类动作的接收方抽取。
- `consumes_anchor=true` 时，输入侧应能解析到已验证 anchor。
- `produces_anchor=true` 时，输出侧应声明可被 lineage 跟踪的产物类型。
- `external_effect=true` 的工具必须在 canonical event 中显式保留副作用与接收方信息。

## 可信边界

- `tool_result_summary`、planner 自由文本、LLM chain-of-thought：**不是授权证据**。
- AEM 不依赖 synthetic labels、benchmark rationale 或离线注释做 runtime 授权。
- 授权证据应来自：
  - 当前 session 状态
  - grants / basis
  - trusted tool manifest
  - controller-observed arguments
  - verified anchors / lineage
  - resource registry

## AEM 与 RAC checker 的关系

- AEM 负责“把待发出的 MCP 调用变成 canonical authorization event”。
- RAC checker 负责对该事件做 no-more-permissive consistency checking。
- Guarded client / gateway 负责执行最终 enforcement。

也就是说：

- `ALLOW` => 允许真正调用 MCP server
- `BLOCK` => 不调用 MCP server，并记录 `issued_to_server=false`

## 示例工具集合

在论文 case study 中，AEM 应覆盖一组 MCP-native 工具，例如：

- `read_report`
- `search_reports`
- `summarize_report`
- `extract_metrics`
- `create_internal_report`
- `save_internal_report`
- `send_email`

这些工具的差异应通过 manifest 映射到统一的 canonical actions，而不是在 checker 中写工具名特判。
