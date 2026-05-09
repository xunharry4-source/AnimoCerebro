# nine-question-q4-what-can-i-do

- Name: Q4 What Can I Do
- Description: Answer the fourth nine-question prompt by turning objective signals and capability evidence into objective seeds.

## Product Semantics

Q4 is the "我能干什么 / 目标种子生成" stage from `Zentex_产品功能文档_V1-4.md`.

Q4 is not just a capability-boundary explorer. Capability discovery, permission evidence, probe results, failure receipts, and reflection gaps are inputs. The Q4 product output is an `ObjectiveSeedSet` / `ObjectiveCandidateSet`: what Zentex can now advance, upgrade, or solve.

Q4 candidates are not permission, not final tasks, and not execution plans. They must flow through Q5 compliance filtering, Q6 consequence constraints, Q7 lateral exploration, Q8 task/objective shaping, and Q9 implementation-plan drafting. Real task records, `task_id`, `subtask_id`, executor binding, resource locks, and state transitions belong to G31A/task-center only.

## Input Semantics

Q4 may consume the saved upstream LLM outputs and reflection query result:

- Q1-only `EnvironmentObjectiveSignal`
- Q2-only `SelfObservationObjectiveSignal`
- `CapabilityGapSignal`
- reflection results and historical experience
- Q3 role profile and mission boundary

Q1/Q2 objective signals cannot skip Q4. Only Q4-objectivized `ObjectiveCandidate` records may continue to Q5/Q6/Q7/Q8/Q9.

### User-Configured Workspace Task Goals

Users may manually add task goals on the settings page. These goals are stored on the selected workspace as `workspace.task_goals`.

When Q4 runs, it must read the current/default workspace task goals from the execution context or `workspace_store`. If the list is non-empty, Q4 must run a dedicated manual-goal lane-analysis LLM before the internal and external objective-candidate LLMs. That analysis must classify each user goal as `internal`, `external`, or `hybrid`, include both an internal-task analysis and external-task analysis, and explicitly compare the internal vs external handling path.

The internal Q4 lane must receive this lane-analysis result and separately generate extra internal objective candidates for user goals whose preferred lane is `internal` or `both`. The external Q4 lane must receive the same analysis and separately generate extra external objective candidates for user goals whose preferred lane is `external` or `both`. These extra candidates are in addition to the normal Q1/Q2/Q3/reflection-driven Q4 candidates; they do not replace the existing Q4 objective generation flow.

Manual task goals remain Q4 objective-candidate inputs only. They must not be converted into real task records, task IDs, subtasks, executor bindings, resource locks, or task-center state transitions inside Q4.

## Output Semantics

Q4 must produce objective candidates split by lane:

- Internal cognition lane: `InternalObjectiveCandidateSet`
  - reflection objectives
  - memory governance objectives
  - value prompting objectives
  - strategy patch objectives
  - learning objectives
  - shadow testing objectives
  - pure cognitive plugin objectives
  - self-evolution objectives
- External execution lane: `ExternalObjectiveCandidateSet`
  - agent delegation objectives
  - CLI objectives
  - MCP objectives
  - connector objectives
  - external service objectives
  - file or Office objectives
  - browser or SaaS objectives
  - information acquisition objectives
  - external problem-solving objectives

Each candidate must carry a unique Q4-local `objective_number` plus source/evidence references, including objective-signal refs and capability-boundary evidence refs. Internal lane output must never create external read/write actions, Agent delegation, CLI/MCP/Connector calls, real task IDs, or state-machine transitions. External lane output must remain a candidate objective and must not invoke tools directly.

The Q4 internal and external lanes use Instructor/Pydantic v2 contracts before persistence. The contracts reject non-schema analysis fields, unexpanded prompt variable names, empty capability evidence refs, tool-call descriptions, step-like outputs, nested compatibility output shapes, and candidate descriptions that start as analysis/assessment/checking instead of a lane-specific objective.

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

- Functional plugin outputs must first be merged into Q4's objective-generation evidence.
- Preferred input-side merge targets are:
  - `exec_domains`
  - `execution_domain_catalog`
  - `model_context["active_execution_domains"]`
- If the plugin preserves the derived effect in final outputs, the result must be reflected through:
  - `q4_objective_seed_set`
  - `q4_objective_candidate_set`
  - `q4_capability_boundary_evidence_refs`

Historical compatibility fields such as `q4_capability_boundary_profile` may still be written as evidence/read-model fields during migration. They must not be treated as the final Q4 product semantic.

## Constraints

- Functional plugin outputs must tighten or clarify the capability boundary, not bypass the anti-hallucination checks.
- Do not create a separate top-level Q4 result branch for this feature.
- Q4 must read upstream Q1/Q2/Q3 from the persisted nine-question SQLite per-question tables through the authoritative LLM output projection. It must not read legacy response blobs or non-SQLite compatibility data.
- Q4 must persist successful question output, LLM output, trace data, context updates, module runs, and module outputs through the split SQLite nine-question tables. These tables must keep schema version and timestamps.
- Q4 must not use fallback, degradation, compatibility, or synthesized replacement data when upstream Q3 inventory, functional capability execution, execution domains, LLM invocation, LLM output validation, or anti-hallucination validation fails.
- On exception, Q4 must raise the error and must not save a Q4 question snapshot. Only module outputs that completed successfully before the exception may be saved.
- A module retry may save only the module data it actually reran. It must not rewrite Q4 as a fallback/degraded answer and must not fabricate a new LLM output.
- Q4 must not generate final tasks, task IDs, subtasks, executor binding, or task-center state transitions.
- Q4 must not treat capability-boundary exploration as the final answer. Capability evidence must be converted into objective seeds or explicit evidence gaps.

## 持久化行为（Q4）

- Q4 按一次调用生成 `run_id`，并通过 `session_id + run_id` 作为持久化主键进行 LLM 运行记录。
- Q4 LLM 输入输出不再混在一列里，拆为内部轨与外部轨输入输出：
  - `nine_question_q4_llm_io`
    - 主运行记录表（一次 Q4 运行一行）
    - 包含字段：
      - `internal_llm_input_json`
      - `internal_llm_output_json`
      - `external_llm_input_json`
      - `external_llm_output_json`
    - 以及 `trace_id/request_id/decision_id/provider_name/model/status/error/attempt_count/token_usage/elapsed_ms/created_at/updated_at` 等运行元数据
  - `nine_question_q4_inferred_capabilities`
    - 迁移期兼容读模型：按能力逐行持久化 `inferred_capabilities`
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
- 目标语义迁移后，应新增或投影：
  - `q4_objective_seed_set`
  - `q4_objective_candidate_set`
  - `q4_internal_objective_candidates`
  - `q4_external_objective_candidates`
  - `q4_objective_signal_refs`
  - `q4_capability_boundary_evidence_refs`
- 当前 Q4 运行为单轮 LLM 逻辑，`external_llm_*` 在部分路径可写空对象；当双轨 LLM 调用完全落地后，同表应承载完整 internal/external 输入输出，不改主键与查询约束。
