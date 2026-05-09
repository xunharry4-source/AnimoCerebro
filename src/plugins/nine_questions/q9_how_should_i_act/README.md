# nine_question_q9_action_plan

- Name: Q9 How Should I Act
- Description: Answer the ninth nine-question prompt by producing a concrete ten-field ActionPlan.

This plugin is an independent unit.
Required files:
- startup.py
- plugin.json
- register.py
- README.md

## Public Methods

Q9 exposes two lane-specific public methods. Callers must choose the lane they need and must not ask downstream code to split, normalize, or clean a mixed Q9 payload.

### `run_internal_action_design(context)`

Use this method for internal cognition, memory, reasoning, safety-module, and verification planning only.

Returns a `CognitiveToolResult` with:

- `tool_id`: `<q9_plugin_id>:internal`
- `llm_output`:
  - `q9_internal_llm_input`
  - `q9_internal_llm_output`
- `context_updates`:
  - `q9_internal_action_design`
  - `q9_internal_execution_diagnosis`
- `proposals`:
  - one `q9_internal_action_design` proposal

The meaningful business contract is `q9_internal_action_design`. It is already validated by Q9 and has exactly this shape:

- `action_objective`
- `internal_steps`
- `required_internal_resources`
- `verification_checks`
- `stop_conditions`
- `evidence_refs`

If the LLM returns a missing `Q9InternalActionDesign`, unknown keys, empty strings, empty list fields, or otherwise meaningless content, Q9 raises an error. Downstream must not be responsible for interpreting raw LLM garbage.

### `run_external_action_design(context)`

Use this method for external execution, connector, CLI, MCP, browser, API, tenant, contact, and side-effect action design only.

Returns a `CognitiveToolResult` with:

- `tool_id`: `<q9_plugin_id>:external`
- `llm_output`:
  - `q9_external_llm_input`
  - `q9_external_llm_output`
- `context_updates`:
  - `q9_external_action_design`
  - `q9_external_execution_diagnosis`
- `proposals`:
  - one `q9_external_action_design` proposal

The meaningful business contract is `q9_external_action_design`. It is already validated by Q9 and has exactly this shape:

- `action_objective`
- `external_steps`
- `required_external_resources`
- `verification_checks`
- `stop_conditions`
- `evidence_refs`

If the LLM returns a missing `Q9ExternalActionDesign`, unknown keys, empty strings, empty list fields, or otherwise meaningless content, Q9 raises an error. Downstream must not be responsible for interpreting raw LLM garbage.

### `run_tool(context)`

`run_tool(context)` exists only as a compatibility orchestrator for callers that still execute Q9 as one cognitive plugin. It calls `run_internal_action_design(context)` and `run_external_action_design(context)` separately, then returns both lane results side by side.

`run_tool(context)` must not merge internal and external semantics into one action object. Its `context_updates` may contain both lane outputs, but the meaningful action designs remain:

- `q9_internal_action_design`
- `q9_external_action_design`

`run_tool(context)` also preserves the four separate raw LLM I/O fields in `context_updates` for audit/readback only:

- `q9_internal_llm_input`
- `q9_internal_llm_output`
- `q9_external_llm_input`
- `q9_external_llm_output`

Downstream code must consume those lane-specific fields directly. It must not parse raw `q9_*_llm_input`, raw `q9_*_llm_output`, or legacy merged fields as the business result.

## Functional Plugin Expansion Rules

- This cognitive plugin may discover and execute bound functional plugins only through `src/zentex/plugins/service.py`.
- Do not read relationship tables directly and do not bypass the public service boundary.
- Query enabled functional plugins with `query_cognitive_plugin_functionals_by_operational_status(..., operational_status="enabled")`.
- Execute functional plugins through `SystemPluginService.execute_plugin_once(...)` or `execute_plugin_once_sync(...)`.
- Every functional execution must pass `caller_plugin_id=<current cognitive plugin id>`.

## Write Locations

- Functional plugin outputs must first be merged into Q9's action-planning inputs.
- Preferred input-side merge targets are:
  - `posture_oracles`
  - `posture_catalog`
- Final LLM output must be reflected through:
  - `q9_action_plan`
- Compatibility projections may still be exposed for downstream task overlays through:
  - `q9_evaluation_profile`
  - `q9_evolution_profile`
  - `q9_escalation_profile`

## Constraints

- Functional plugin outputs are action-planning evidence and must not bypass the final Q8 decision context.
- Q9 must read authoritative Q1/Q2/Q3/Q8 LLM outputs from the SQLite nine-question snapshot tables before ActionPlan synthesis.
- Q9 requires completed Q1/Q2/Q3/Q8 upstream snapshots, real self-model input, real reasoning budget input, and at least one successful posture plugin result.
- Q9 must persist only its own successful module outputs into the SQLite module-output tables.
- Q9 must persist functional posture evidence, Q1/Q2/Q3/Q8 validation, self-model validation, reasoning-budget validation, posture baseline, and LLM ActionPlan projection as separate module records.
- Every persisted Q9 table row is versioned and timestamped by the shared SQLite nine-question store.
- Q9 must not return substitute, legacy, or incomplete responses. Exceptions propagate and failed exception payloads are not saved.

## Data Acquisition Enforcement

为了确保因果审计链（Causal Audit Chain）的完整性，Q9 **必须** 遵循以下数据获取规范：

1. **禁止手动提取 (No Manual Extraction)**:
   - 严禁使用 `context.get("q8_...")` 等方式获取 Q8 结果。
   - 严禁从 `nine_question_state` 的 `context_updates` 中直接读取上游数据。

2. **官方加载器路径 (Official Loader Methods)**:
   - 必须通过上游 Q8 提供的对外读取方法从 SQLite 权威状态库中读取数据。
   - 核心方法：`from plugins.nine_questions.q8_what_should_i_do_now.service import load_internal_public_output, load_external_public_output`

3. **因果处理**:
   - 加载器会自动处理数据清洗、空值过滤及结构化校验，确保进入 LLM Prompt 的上下文是经过因果验证的最新快照。
