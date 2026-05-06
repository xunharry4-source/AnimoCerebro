# nine-question-q3-role-inference

- Name: Q3 我是谁
- Product semantics: 基于 Q1 我在那 与 Q2 我有什么，推断当前角色一致性、任务角色和使命边界。

This plugin is an independent unit.
Required files:
- startup.py
- plugin.json
- register.py
- README.md

## Functional Plugin Boundary

- Q3 must not discover, execute, or introduce internal functional plugins while inferring the role.
- Q3 may read Q2's authoritative LLM business output, but it must compact that output before invoking the Q3 LLM.
- Q3 must consume only Q2's external functional tool LLM output as structured per-item `q2_external_tool_asset_inventory` evidence (`asset_name`, `description`, `source`, `plugin_category`, `trust_level`, `validity`) because role inference needs concrete external tool descriptions, not aggregate inventories or unified tool-name summaries.
- Internal functional plugins belong to Q2 asset inventory or later execution planning; Q3 must not execute them or copy plugin names into `identity_role` / `active_role`.

## Runtime Write Locations

- Q1/Q2 精简业务输出、身份内核与用户配置共同构建“我是谁”角色推断上下文，必须写入：
  - `role_payload`
  - `constraint_payload`
  - `identity_kernel_snapshot`
- Canonical live-LLM result 是 `RoleInference`，持久化为：
  - `q3_role_profile`
  - `q3_mission_boundary`
- 上下文与追踪中可见：
  - `q3_risk_weight`
  - `q3_execution_diagnosis`
  - `llm_trace_payload`

## Constraints

- Q3 live LLM output must be strict JSON and must contain root `Q3InferenceResult` with `RoleProfile` and `MissionContinuityBoundary`（各自字段齐全、非空、无额外字段）。
- Q3 role inference may validate Q1/Q2 authoritative SQLite snapshots, but it must pass only compact LLM business outputs into the Q3 LLM request as `q1_authoritative_llm_output` and `q2_authoritative_llm_output`; never pass upstream full snapshots, traces, module runs, context updates, raw runtime inventories, or plugin execution outputs as downstream reasoning context.
- Q3 prompt assembly must use explicit rendered modules (`Q1_Environment_State`, `Q2_Asset_Inventory`, `Identity_Kernel`, `Human_Intervention_Receipts`, `Strict_Output_Contract`) and template placeholder replacement; it must not degrade into ad-hoc concatenation of upstream content.
- The model-facing schema uses exact root key `Q3InferenceResult`; old aliases are not accepted.
- `RoleProfile` 每次推理都必须保留 `identity_role`、`active_role`、`inferred_reference_role`、`role_alignment_gap`、`task_role`。
- `identity_role` 必须来源于 `Identity_Kernel`，但输出语义应抽象为“AI系统本体”级身份溯源标记，不得直接作为 `active_role` 或 `inferred_reference_role` 的任务角色候选；用户手工锁定角色时，`active_role` 必须逐字等于用户角色并附带 `[User Locked]` 标记，推断结果仅供对比，不得自动替换用户角色。
- `MissionContinuityBoundary.continuity_boundaries` 必须继承身份内核的 `non_bypassable_constraints`、`self_binding_constraints`、连续性锁与红线约束；运行时会补齐 LLM 遗漏的身份边界。
- Q3 must read upstream Q1/Q2 from persisted SQLite authoritative snapshots via `get_authoritative_question_snapshot` / `merge_authoritative_question_payload`, then compact them before LLM invocation.
- 失败路径不能降级为兼容回退回答；必须通过 fail-closed 失败并保留模块失败审计。
- On exception, Q3 must raise the error and must not save a Q3 question snapshot. Only module outputs that completed successfully before the exception may be saved.
- A module retry may save only the module data it actually reran. It must not rewrite Q3 as a fallback/degraded answer and must not fabricate a new LLM output.
- Web console Q3 views must separate low-confidence or unverified role evidence with MUI `Alert` instead of mixing it with confirmed role/mission fields.
