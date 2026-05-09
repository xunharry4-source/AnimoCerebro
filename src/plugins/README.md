# Zentex Plugins

This directory houses the concrete implementations of various Zentex plugins.
- **One plugin = one independent directory**.
- **Allowed plugin paths**:
	- `src/plugins/<plugin>`
	- `src/plugins/<group>/<plugin>`
- **Disallowed plugin path**:
	- `src/plugins/<plugin>/<plugin>` (nested plugin directory is not registered)
- **Standard Invocation**: Plugins must ONLY be called through the centralized service in `src/zentex/plugins`. Direct cross-imports between plugins or from other modules are prohibited.
- **Required files per plugin directory**:
	- `startup.py`
	- `plugin.json`
	- `register.py`
	- `README.md`
- **No shared logic/services**: Service implementations (e.g. `service.py`) and shared utilities for a plugin group must reside in `src/zentex/`. The plugin directory is reserved for independent plugin units.
- **Loader entry**: `src/plugins/startup.py`
- **Guide**: `src/plugins/PLUGIN_STARTUP_GUIDE.md`
- **Current independent plugin units**:
	- `src/plugins/sensory/environment_interpreter/`
	- `src/plugins/sensory/prompt_injection_sanitizer/`
	- `src/plugins/sensory/webhook_ingest/`
	- `src/plugins/sensory/host_telemetry/`
	- `src/plugins/memory/memory_extractor/`
	- `src/plugins/oracle/alternative/`
	- `src/plugins/oracle/objective/`
	- `src/plugins/oracle/posture/`
	- `src/plugins/oracle/redline/`
	- `src/plugins/nine_questions/q1_where_am_i/`
	- `src/plugins/nine_questions/q2_asset_inventory/`
	- `src/plugins/nine_questions/q3_role_inference/`
	- `src/plugins/nine_questions/q4_what_can_i_do/`
	- `src/plugins/nine_questions/q5_what_am_i_allowed_to_do/`
	- `src/plugins/nine_questions/q6_what_should_i_not_do/`
	- `src/plugins/nine_questions/q7_what_else_can_i_do/`
	- `src/plugins/nine_questions/q8_what_should_i_do_now/`
	- `src/plugins/nine_questions/q9_how_should_i_act/`
- **`cognitive/`**: Implementation of cognitive tools (e.g., conflict checking, ranking).
- **`sensory/`**: Environmental signal ingestion and sanitization.
- **`simulation/`**: Counterfactual and branch simulation tools.
- **`execution/`**: Plugins responsible for interaction with the external environment.
- **`model_providers/`**: Adapters for various LLM backends (Gemini, OpenAI, etc.).

---

# Zentex 插件目录

该目录存放了 Zentex 各种插件的具体实现。
- **一个插件 = 一个独立目录**。
- **允许的插件路径**：
	- `src/plugins/<插件>`
	- `src/plugins/<目录>/<插件>`
- **禁止的插件路径**：
	- `src/plugins/<插件>/<插件>`（嵌套插件目录不会被注册）
- **每个插件目录必须包含**：
	- `startup.py`
	- `plugin.json`
	- `register.py`
	- `README.md`
- **标准调用方式**：所有插件必须且仅能通过 `src/zentex/plugins` 的中心化服务进行调用。严禁插件之间直接进行跨目录导入，或从其他模块直接导入插件代码。
- **禁止共享逻辑/服务**：服务实现（如 `service.py`）和插件组的共享工具必须存放在 `src/zentex/` 目录下。插件目录仅允许存放独立的插件单元，中性代码（如 Nine-Questions 共享 prompt 逻辑）已迁移至 `src/zentex/common/nine_questions_prompts.py`。
- **加载入口**：`src/plugins/startup.py`
- **规则说明**：`src/plugins/PLUGIN_STARTUP_GUIDE.md`
- **当前已落地的独立插件单元**：
	- `src/plugins/sensory/environment_interpreter/`
	- `src/plugins/sensory/prompt_injection_sanitizer/`
	- `src/plugins/sensory/webhook_ingest/`
	- `src/plugins/sensory/host_telemetry/`
	- `src/plugins/memory/memory_extractor/`
	- `src/plugins/oracle/alternative/`
	- `src/plugins/oracle/objective/`
	- `src/plugins/oracle/posture/`
	- `src/plugins/oracle/redline/`
	- `src/plugins/nine_questions/q1_where_am_i/`
	- `src/plugins/nine_questions/q2_asset_inventory/`
	- `src/plugins/nine_questions/q3_role_inference/`
	- `src/plugins/nine_questions/q4_what_can_i_do/`
	- `src/plugins/nine_questions/q5_what_am_i_allowed_to_do/`
	- `src/plugins/nine_questions/q6_what_should_i_not_do/`
	- `src/plugins/nine_questions/q7_what_else_can_i_do/`
	- `src/plugins/nine_questions/q8_what_should_i_do_now/`
	- `src/plugins/nine_questions/q9_how_should_i_act/`
- **`cognitive/`**: 认知工具的实现（如：冲突检查、排名等）。
- **`sensory/`**: 环境信号的摄取与清洗。
- **`simulation/`**: 反事实与分支模拟工具。
- **`execution/`**: 负责与外部环境交互的插件。
- **`model_providers/`**: 不同 LLM 后端（Gemini, OpenAI 等）的适配层。

---

# 🛑 核心系统稳定性红线 (Strict Operation Rules)

**所有的插件和核心模块开发，必须绝对遵守以下红线：**

1. **禁止静默吞噬异常**：禁止把异常都吐掉了，假装后台运行正常，不打印日志的行为。发现这样的行为，马上重写，并且在代码处标明禁止这种假装系统正常，严重破坏系统稳定的行为。
2. **禁止功能假实现**：禁止功能假实现，发现马上重写，并且在代码处标明禁止这种假装功能已实现，严重破坏系统正常运行行为。
