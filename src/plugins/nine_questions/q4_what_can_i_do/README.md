# nine-question-q4-what-can-i-do

- Name: Q4 What Can I Do
- Description: Answer the fourth nine-question prompt about available actions.

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

- Functional plugin outputs must first be merged into Q4's capability-boundary inputs.
- Preferred input-side merge targets are:
  - `exec_domains`
  - `execution_domain_catalog`
  - `model_context["active_execution_domains"]`
- If the plugin preserves the derived effect in final outputs, the result must be reflected through:
  - `q4_capability_boundary_profile`

## Constraints

- Functional plugin outputs must tighten or clarify the capability boundary, not bypass the anti-hallucination checks.
- Do not create a separate top-level Q4 result branch for this feature.
- Q4 must read upstream Q1/Q2/Q3 from the persisted nine-question SQLite per-question tables through the authoritative LLM output projection. It must not read legacy response blobs or non-SQLite compatibility data.
- Q4 must persist successful question output, LLM output, trace data, context updates, module runs, and module outputs through the split SQLite nine-question tables. These tables must keep schema version and timestamps.
- Q4 must not use fallback, degradation, compatibility, or synthesized replacement data when upstream Q3 inventory, functional capability execution, execution domains, LLM invocation, LLM output validation, or anti-hallucination validation fails.
- On exception, Q4 must raise the error and must not save a Q4 question snapshot. Only module outputs that completed successfully before the exception may be saved.
- A module retry may save only the module data it actually reran. It must not rewrite Q4 as a fallback/degraded answer and must not fabricate a new LLM output.

## 持久化行为（Q4）

- Q4 现在按一次调用生成 `run_id`，并通过 `session_id + run_id` 作为持久化主键进行 LLM 运行记录。
- Q4 LLM 输入输出不再混在一列里，拆为两个独立表：
  - `nine_question_q4_llm_io`
    - 主运行记录表（一次 Q4 运行一行）
    - 包含字段：
      - `internal_llm_input_json`
      - `internal_llm_output_json`
      - `external_llm_input_json`
      - `external_llm_output_json`
    - 以及 `trace_id/request_id/decision_id/provider_name/model/status/error/attempt_count/token_usage/elapsed_ms/created_at/updated_at` 等运行元数据
  - `nine_question_q4_inferred_capabilities`
    - 按能力逐行持久化 `inferred_capabilities`
    - 每行包含 `capability_name`、`capability_description`，并拆分保存 `q1_resources` 与 `q2_capabilities`
    - 增加过滤维度字段（默认不过滤）：
      - `q5_filtered`（0/1，默认 0）、`q5_filter_reason`（默认空字符串）
      - `q6_filtered`（0/1，默认 0）、`q6_filter_reason`（默认空字符串）
      - `q7_filtered`（0/1，默认 0）、`q7_filter_reason`（默认空字符串）
    - 通过 `session_id + run_id` 外键关联到 `nine_question_q4_llm_io`

- 对应的持久化入口：
  - `persist_q4_llm_io(...)`
  - `persist_q4_inferred_capabilities(...)`
- 对应读取入口：
  - `load_q4_llm_io_latest(...)`
  - `load_q4_inferred_capabilities(...)`
- 当前 Q4 运行为单轮 LLM 逻辑，`external_llm_*` 在当前版本可写空对象；当未来引入双路（内外）调用时同表可直接承载，不改主键与查询约束。
