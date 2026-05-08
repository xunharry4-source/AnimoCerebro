# nine_question_q8_decision

- Name: Q8 What Should I Do Now
- Description: Answer the eighth nine-question prompt about immediate decision making.

This plugin is an independent unit.
Required files:
- startup.py
- plugin.json
- register.py
- README.md

## Functional Plugin Expansion Rules

- This cognitive plugin may discover and execute bound functional plugins only through `src/zentex/plugins/service.py`.
- Do not read relationship tables directly and do not bypass the public service boundary.
- Query enabled functional plugins with `query_cognitive_plugin_functionals_by_operational_status(..., operational_status="enabled")`.
- Execute functional plugins through `SystemPluginService.execute_plugin_once(...)` or `execute_plugin_once_sync(...)`.
- Every functional execution must pass `caller_plugin_id=<current cognitive plugin id>`.

## Write Locations

- Functional plugin outputs must first be merged into Q8's objective-synthesis inputs.
- Preferred input-side merge targets are:
  - `obj_oracles`
  - `objective_catalog`
  - task-priority or queue-shaping inputs derived from `persistent_task_state`
- If the plugin preserves the derived effect in final outputs, the result must be reflected through:
  - `q8_objective_and_queue`
  - `q8_objective_profile`
  - `q8_task_queue`

## Public Methods

Q8 exposes two branch-specific public output methods on
`WhatShouldIDoNowPlugin`. Downstream callers must use these methods when they
need Q8 internal or external branch results. Do not consume raw branch runtime
payloads directly.

### `build_internal_public_output(internal_task_result)`

- Input: the raw result returned by `internal_tasks.run_q8_internal_task_generation(...)`.
- Output scope: `internal`.
- Output shape:
  - `scope`
  - `objective_profile`
  - `task_queue`
  - `task_plan`
- Meaning: internal cognitive work only. This method returns the usable public
  internal plan and hides branch-local LLM request/response details.

### `build_external_public_output(external_task_result)`

- Input: the raw result returned by `external_tasks.run_q8_external_task_generation(...)`.
- Output scope: `external`.
- Output shape:
  - `scope`
  - `objective_profile`
  - `task_queue`
  - `task_plan`
- Meaning: external execution-facing intent only. This method returns the usable
  public external plan and hides branch-local LLM request/response details.

### Public Output Boundary

- These two methods must not merge internal and external outputs.
- These two methods must not return raw branch internals such as `raw_result`,
  `llm_input`, `llm_output`, `trace_payload`, `reasoning`,
  `persistent_task_state`, `q8_priority_baseline`, `q8_functional_objectives`,
  or `q8_staged_reasoning`.
- Empty or meaningless branch output is a hard error:
  - `q8_internal_public_output_empty`
  - `q8_external_public_output_empty`
- `q8_objective_and_queue` may include the two public branch results as
  `q8_internal_result` and `q8_external_result`, but must not inline branch-local
  LLM I/O or trace payloads. LLM trace data belongs only in the dedicated
  `llm_trace_payload` field.

## Constraints

- Functional plugin outputs must influence prioritization, not bypass Q1/Q2/Q3/Q7 constraints.
- Do not create a separate top-level Q8 output branch for this feature.
- Q8 must read the authoritative Q1/Q2/Q3/Q7 LLM outputs from the SQLite nine-question snapshot tables before synthesis.
- Q8 requires Q1/Q2/Q3/Q7 upstream snapshots to be completed. Any incomplete upstream is a hard error.
- Q8 must persist only its own successful module outputs into the SQLite module-output tables.
- Q8 must persist the LLM decision projection and task persistence outputs as separate module records; do not combine them into a single table-shaped blob.
- Every persisted Q8 table row is versioned and timestamped by the shared SQLite nine-question store.
- Q8 must not return substitute or legacy responses. Exceptions propagate and failed exception payloads are not saved.

## Data Acquisition Enforcement

为了确保因果审计链（Causal Audit Chain）的完整性，Q8 **必须** 遵循以下数据获取规范：

1. **禁止手动提取 (No Manual Extraction)**:
   - 严禁使用 `context.get("q4_...")`, `context.get("q5_...")`, `context.get("q6_...")`, `context.get("q7_...")` 等方式获取上游结果。
   - 严禁从 `nine_question_state` 的 `context_updates` 中直接读取上游数据。

2. **官方加载器路径 (Official Loader Methods)**:
   - 必须通过上游插件提供的官方加载器从 SQLite 权威状态库中读取数据。
   - Q4 目标：`from plugins.nine_questions.q4_what_can_i_do.llm_output_table import load_llm_output_from_table` (Wait, Q4 should have this unified one)
   - Q5 安全：`from plugins.nine_questions.q5_what_am_i_allowed_to_do.llm_output_table import load_llm_output_from_table`
   - Q6 限制：`from plugins.nine_questions.q6_what_should_i_not_do.llm_output_table import load_internal_llm_output_from_table, load_external_llm_output_from_table`
   - Q7 探索：`from plugins.nine_questions.q7_what_else_can_i_do.llm_output_table import load_internal_llm_output_from_table, load_external_llm_output_from_table`

3. **因果处理**:
   - 加载器会自动处理数据清洗、空值过滤及结构化校验，确保进入 LLM Prompt 的上下文是经过因果验证的最新快照。
