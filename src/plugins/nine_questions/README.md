# Nine-Questions Plugin Group Rule

**STOP! READ THIS BEFORE ADDING ANY CODE HERE.**

## Directory Integrity Policy

This directory (`src/plugins/nine_questions/`) is a **PURE PLUGIN GROUP CONTAINER**. 

1. **NO SHARED CODE**: It is strictly forbidden to add any Python files (`.py`) directly to this directory.
2. **ONLY SUBDIRECTORIES**: This directory must only contain plugin implementation subdirectories (e.g., `q1_where_am_i/`, `q2_asset_inventory/`, `q3_role_inference/`).
3. **MANDATORY SHARED LOCATION**: All shared logic, utilities, or helpers used by multiple Nine-Questions plugins **MUST** be placed in `src/zentex/common/nine_questions_shared.py`.
4. **NO HIDDEN HELPERS**: Do not create files starting with `_` (e.g., `_partial_failure.py`) in this directory to bypass architectural rules.

**VIOLATIONS WILL BE TREATED AS A SYSTEM INTEGRITY THREAT AND AUTOMATICALLY DELETED.**

---
*Enforced by Zentex Clinical Standards.*

## 数据获取与因果完整性 (Data Acquisition & Causal Integrity)

为了确保认知链条的确定性和因果审计的完整性，九问插件必须遵循以下数据交互协议：

1. **禁止手动提取上下文 (No Manual Context Extraction)**:
   - 严禁通过 `context.get("q4_...")` 等方式直接从上下文对象中提取上游认知结果。
   - 上下文对象仅用于传递环境参数（如 `session_id`, `trace_id`），不作为认知数据的权威来源。

2. **必须使用官方加载器 (Must Use Official Loaders)**:
   - 必须通过上游插件目录下的 `llm_output_table.py` 中提供的对外方法获取数据。
   - 这些方法确保从 `data/sessions.db`（SQLiteAuthoritativeState）中读取经过因果验证的快照。

3. **标准方法签名**:
   - `load_llm_output_from_table(session_id=...)`: 获取该阶段的完整 LLM I/O。
   - `load_internal_llm_output_from_table(...)`: 仅获取内部轨（Internal Lane）结果。
   - `load_external_llm_output_from_table(...)`: 仅获取外部轨（External Lane）结果。

4. **强制持久化**:
   - 所有具备 `run_tool` 能力的插件必须在 `execute` 阶段将原始 LLM 输入/输出持久化至 SQLite 对应的 Snapshot 表。
   - 持久化必须在 `zentex/common/nine_questions_shared.py` 的白名单投影下进行，确保审计链无断点。
