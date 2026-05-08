# RAC v0.6 — 实现与《RAC 技术规格 v0.6》对照

## 规范来源

- **中文工程技术规格**：`RAC_技术规格_v0.6.md`（你提供的版本：例如 Windows `c:\study\论文投递\acsac\tech_spec\RAC_技术规格_v0.6.md`；在 WSL 下可能为 `/mnt/c/study/论文投递/acsac/tech_spec/RAC_技术规格_v0.6.md`）。
- **建议**：若需仓库内可引用副本，可将该文件**复制**到 `docs/RAC_技术规格_v0.6.md`（本仓库默认**不**随附全文，以免与论文稿源分叉）。
- 本文档是**实现索引**：表格与「差距说明」随 `rac-core` 代码更新；**不以**本文替代规范正文。

## 规范中的技术主轴（§3）与代码对应

规范给出的链路：

`Trusted Event Construction → Output Anchor Verification → Resource Origin Verification → Runtime-resolved Causal Lineage → Authorization Basis Propagation → Pre-commit Consistency Checking`

| 主轴环节 | 本仓库主要位置 |
|---|---|
| Trusted Event Construction | `adapter/event_adapter.py`（`EventAdapter.construct_event`）、`adapter/profile_validator.py` |
| Output Anchor Verification | `verification/output_anchor.py`、`store/lineage_store.py`（持久化约束）、`checker/precommit.py`（`require_verified_output_anchor`） |
| Resource Origin Verification | `verification/resource_origin.py`、`checker/precommit.py` |
| Runtime-resolved Causal Lineage | `store/lineage_store.py`（`resolve_predecessor`、`append_step`）、`models/lineage.py` |
| Authorization Basis Propagation | `store/basis_store.py`、`models/basis.py`、`checker/basis_tightening.py`、`checker/precommit.py` |
| Pre-commit Consistency Checking | `checker/precommit.py`（`RACPreCommitChecker.check`） |

## 授权语义规范化路径（§0 中文表述）

`Grant Template Expansion → Compiled Grant … → Tool Manifest Authorization Profile → Leaf Action Label Normalization → Explicit Action Coverage Check`

| 环节 | 本仓库主要位置 | 测试 |
|---|---|---|
| Grant Template / Profile 展开 | `action_semantics/grant_template.py`、`configs/default_grant_templates.yaml` | `tests/test_grant_profile_expander.py`、`tests/test_basis_profile_bridge.py` |
| Manifest authorization_profile | `models/manifest.py`、`adapter/profile_validator.py` | `tests/test_manifest_authorization_profile.py`、`tests/test_manifest_profile_validator.py` |
| Leaf 标签 + 偏序 | `action_semantics/registry.py`、`partial_order.py`、`configs/default_action_semantics.yaml` | `tests/test_action_semantics_registry.py` |
| 显式动作覆盖 | `action_semantics/coverage.py`、`checker/precommit.py`（`_check_action_coverage_v06`） | `tests/test_precommit_action_coverage_v06.py`、`tests/test_action_coverage_checker.py` |

## Reference Action Semantics 与 taxonomy（§2.4、§0 第 8 点）

- **规范**：Action Taxonomy 定位为 **Reference Action Semantics**；**taxonomy 用于覆盖组织，不作为 checker 的检测目标**。
- **本仓库**：默认语义 YAML（`configs/default_action_semantics.yaml`）与 `ActionSemanticsRegistry` 提供 **leaf + partial order**；`validation/taxonomy_traces.py` 等用于**受控评估覆盖**。`RACPreCommitChecker` 执行的是 **NoMorePermissive 式一致性**（动作覆盖、资源、目的、委托、条件等），**不是**对「taxonomy 类别」的分类器式检测。

## 主对照表

| v0.6 设计项 | 当前实现位置 | 测试覆盖 | 备注 |
|---|---|---|---|
| TypedAuthorizationEvent | `models/event.py` | `tests/test_core_objects.py`, `tests/test_event_adapter.py`, `tests/test_event_required_actions_bridge.py` | 含 `required_actions`、`input_anchors` 等 |
| 事件字段 `effect`（规范列举） | **未**作为 `TypedAuthorizationEvent` 一等字段 | — | `EffectProfile` 在 manifest `authorization_profile.effects`；**未**在 checker 中实现规范中的 **EffectBoundaryPreservation** 对事件级 `effect` 的独立判定（见下「差距」） |
| GrantEnvelope | `models/grant.py` | `tests/test_core_objects.py`、controlled-trace tests | |
| ToolManifest / authorization_profile | `models/manifest.py`, `adapter/profile_validator.py` | `tests/test_manifest_*.py` | 粗粒度 `operation`/`resource_arg` 与 v0.6 profile 并存 |
| VerifiedStructuredOutputAnchor | `models/anchor.py` | `tests/test_output_anchor_verification.py` 等 | `verified_by_controller`；store 强约束 |
| Controller-side output verification | `store/lineage_store.py`, `verification/output_anchor.py` | `tests/test_lineage_store.py` 等 | `output_anchor_integrity_precheck`（TraceBench / 重放） |
| Resource Origin Verification | `verification/resource_origin.py`, `precommit.py` | `tests/test_resource_origin_verification.py` | `RESOURCE_ORIGIN_UNVERIFIABLE` |
| AuthorizationBasis | `models/basis.py` | `tests/test_basis_store.py`, `tests/test_basis_profile_bridge.py` | `allowed_action_labels` 等 |
| Basis propagation / tightening | `checker/basis_tightening.py`, `precommit.py` | `tests/test_basis_tightening.py` | 规范 §15：沿可信 lineage 传播；下游收缩 |
| Action partial order | `action_semantics/partial_order.py`, `registry.py`, `checker/action_lattice.py` | `tests/test_action_semantics_registry.py` | 未列偏序对默认不可比（保守） |
| NoMorePermissive：ActionCoverage | `precommit.py` `_check_action_coverage_v06` | `tests/test_precommit_action_coverage_v06.py` | 与规范「仅对 leaf required_actions」一致 |
| NoMorePermissive：Resource / Purpose / Delegation / Condition | `precommit.py` `_check_consistency`, `checker/conditions.py` | `tests/test_precommit_checker.py`, `tests/test_condition_tightening.py` | 对应 `RESOURCE_EXPANSION`、`PURPOSE_DRIFT` 等 |
| ProvenanceSupport / `origin_anchors` | `models/basis.py` 字段存在 | 无 dedicated 规则测试于 `precommit` | **差距**：规范公式中含 `ProvenanceSupport(input_anchors, origin_anchors)`；当前 **未** 在 `precommit` 中单独强制 input 与 `basis.origin_anchors` 的对照（若需完全对齐规范，为后续工作） |
| Lineage / advisory hints | `lineage_store.resolve_predecessor` | `tests/test_lineage_store.py` | 与规范 §14：hint 不单独建立因果；冲突时以 runtime lineage 为准（见 `warnings`） |
| Single-predecessor；multi-predecessor → BLOCK | `lineage_store.py` §14.5 对齐策略 | `tests/test_lineage_store.py`, `tests/test_precommit_checker.py`, TraceBench | `MULTI_PREDECESSOR_UNSUPPORTED`；**不**实现 `ConservativeMerge` |
| Decision：`ALLOW` / `BLOCK` / `ALLOW_WITH_ALERT` | `models/decision.py`, `precommit.py` | — | **规范**允许三值及低严重度 `ALLOW_WITH_ALERT`。**本仓库**：`RACPreCommitChecker` **仅** 返回 `ALLOW`/`BLOCK`；`ALLOW_WITH_ALERT` 为 **ENUM 预留**，无 alert 策略实现 |
| Controlled traces / Evaluation | `validation/trace.py`, `rac_tracebench_*.py`, `taxonomy_traces.py` | `tests/test_controlled_trace_validation.py`, `tests/test_rac_tracebench_v06_*.py` 等 | 规范 §6 种子+变异、paired traces、oracle 等由 TraceBench 资产承载 |

## 与规范仍存在的差距（本轮不补机制，仅记录）

以下项在《RAC 技术规格 v0.6》中有定义或出现在 NoMorePermissive 公式中，但 **本 prototype 未完整落地**（避免本轮引入大规模语义变更）：

1. **事件级 `effect` 与 EffectBoundaryPreservation**：规范要求从 manifest 构造 `event.effect` 并在 basis 上校验 effect 边界；当前事件模型无独立 `effect` 字段，checker 无 `EFFECT_BOUNDARY_VIOLATION` 路径。
2. **`ProvenanceSupport` / `origin_anchors`**：`AuthorizationBasis` 含 `origin_anchors`，`precommit` 未对其做独立一致性规则。
3. **`ALLOW_WITH_ALERT`**：规范描述为决策空间之一；实现仅预留枚举，无低严重度告警策略。

## Related notes

- [`authorization_event_mapper.md`](authorization_event_mapper.md) — AEM 边界（工程补充）。
- [`mcp_case_study_plan.md`](mcp_case_study_plan.md) — MCP 案例计划。
