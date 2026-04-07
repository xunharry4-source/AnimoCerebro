# Zentex (AnimoCerebro) 项目深度分析报告

## 1. 项目定位与核心愿景

**AnimoCerebro**（意为“灵魂大脑”）是基于 **Zentex** 框架构建的下一代智能体大脑运行时系统。它的核心目标是提供一个高度纪律化、可审计、且具有自我意识（Metacognition）的认知执行环境。

相比于传统的无状态 LLM 调用，Zentex 强调：

- **连续性 (Continuity)**：通过 `BrainSession` 与 `Transcript` 记录长期记忆。
- **纪律性 (Discipline)**：插件必须符合严格的生命周期与副作用约束。
- **透明度 (Observability)**：通过 Web Console 实时可视化认知的每一个微小步骤。

---

## 2. 系统分层架构

项目采用了清晰的分层设计，确保了核心逻辑与具体实现、展示层的彻底解耦：

### 2.1 契约层 (Contract Layer) - `src/zentex/core`

定义了系统运行的黄金准则（Defense Contracts）。

- **`plugin_base.py`**: 所有插件的基类，强制约束 `LifecycleStatus`（Candidate -> Verified -> Active）。
- **`cognitive_tools_spec.py`**: 认知工具必须满足 **只读 (Read-only)** 且 **无副作用 (Side-effect free)**。
- **`plugin_runtime.py`**: 定义 `PluginLoadResult` 与 `HealthProbe` 契约，确保插件操作可审计。

### 2.2 实现层 (Implementation Layer) - `src/zentex/runtime`

系统的大脑中枢，负责认知的物理执行。

- **`ThinkLoop`**: 核心执行引擎，将单次思考拆分为 **9 个标准阶段**。
- **`BrainRuntime`**: 顶层容器，管理共享存储（Stores）与调度器（Controllers）。
- **`BrainSession`**: 状态容器，通过回放 `Transcript` 录像带恢复内存状态。

---

## 3. 核心机制详解：ThinkLoop 9 阶段认知模型

ThinkLoop 是 Zentex 的灵魂，其执行过程体现了“谋定而后动”的哲学。最新的九阶段模型已完成从感知到巩固的全链路闭环：

1. **Observe (观测)**: 摄取、清洗并解释环境信号（通过 `sensory_ingest` 与 `sensory_sanitize` 插件）。
2. **Frame (框架化)**: 通过 9 问框架构建当前任务的语义边界（**LLM 强制介入**）。
3. **Update Working State (状态更新)**: 确定性地更新工作记忆（Working Memory）、时序议程（Temporal Agenda）与自模型（Living Self Model）。
4. **Detect Cognitive Risks (风险探测)**: 探测冲突（Conflict）、不确定性热点及信心漂移。
5. **Simulate (模拟)**: 并行运行反事实分支，并同步推断交互对象的 **社会心智（Interaction Mind）**。
6. **Metacognition (元认知)**: 根据负载、风险与模拟结果决定当前的思考模式（如 Fast/Deep）。
7. **Orchestrate (编排)**: 在安全边界内原子化调用已验证的认知插件。
8. **Synthesize (合成)**: 汇总所有输出，形成最终决策建议（**LLM 强制介入**）。
9. **Consolidate (固化)**: 启动“睡眠式”后台巩固，提炼稳定模式、规则与教训（Lessons），并清理记忆噪音。

---

## 4. 关键组件深度剖析

### 4.1 MetaCognition (元认知) - 思考的指挥官

- **确定性规则引擎**: 不依赖 LLM，通过硬性规则（如“若认知负荷过高则降低推理深度”）决定思考姿态。
- **输出**: `ReasoningModeDecision` (Fast/Deep), `ToolInvocationPlan`, `EscalationDecision`。

### 4.2 Working Memory (工作记忆) - 注意力管理

- **Slot-based Attention**: 严格限制 `FocusBudget` 槽位，防止上下文膨胀。
- **抢占机制**: 高风险任务可中断低优先级任务，并自动附加 `resume_hint`。

### 4.3 Simulation Engine (模拟引擎) - 反事实推演

- **并行分支**: 使用 `ThreadPoolExecutor` 并行运行多个 `ScenarioBranch`。
- **版本校验**: 通过 `snapshot_version` 确保在背景模拟期间若状态发生变化，陈旧的结果将被丢弃。

### 4.4 Transcript (事件流) - 录像带回放机制

- **JSONL 物理存证**: `BrainTranscriptStore` 记录所有原子事件。
- **Session 恢复**: `BrainSession` 不依赖持久化数据库，而是通过重放 Transcript 来重建内存快照。

### 4.5 Memory Consolidation (记忆巩固) - 睡眠机制

- **离线提炼**: `ConsolidationEngine` 在后台将高复用模式、规则与教训（Lessons）从原始记忆中提炼出来，并提升为长期知识。
- **清理噪音**: 自动识别并“遗忘”低价值的反思与过期的假设，通过 `snapshot_version` 实现乐观锁。

### 4.6 Interaction Mind (社会心智) - 对方建模

- **推断意图**: `InteractionMindEngine` 维护对交互对象的动态建模，包括其知识边界、表达偏好及误解风险。
- **安全降级**: 当推断失败时，系统自动切入“澄清优先”的保守策略（Clarification Mode）。

---

## 5. 项目目录与文件结构增强清单 (Enhanced Manifest)

### 5.1 核心契约与模型 (`src/zentex/core`)

| 文件名 | 核心对象/类 | 职责描述 | 防御性约束 (Defenses) |
| :--- | :--- | :--- | :--- |
| **`plugin_base.py`** | `BasePluginSpec` | 定义所有 Zentex 插件的原子身份与生命周期。 | 强制校验版本语义与健康状态枚举. |
| **`models.py`** | `BrainRuntimeState` | 定义运行时全局快照，包含工具注册表版本、降级模式标志等。 | 实现 `CognitiveToolSpec` 的只读边界检查。 |
| **`plugin_runtime.py`** | `PluginLoadResult` | 记录插件加载、切换、回滚及撤销的审计轨迹。 | **审计要求**：降级或回滚必须携带物理证据（HealthProbe）。 |
| **`cognitive_tools_spec.py`** | `CognitiveToolSpec` | 定义单向认知工具（Inspect, Rank, Compare）的契约。 | **红线**：严禁 `read_only=False` 或存在 `side_effects`。 |

### 5.2 认知运行时与引擎 (`src/zentex/runtime`)

| 文件名 | 核心对象/类 | 职责描述 | 逻辑流/交互 |
| :--- | :--- | :--- | :--- |
| **`runtime.py`** | `BrainRuntime` | 运行时大管家，负责全局依赖注入（LLM, Stores, Registry）。 | 作为 `BrainSession` 的工厂，提供全局配置透传。 |
| **`session.py`** | `BrainSession` | 纯内存状态容器。负责通过 Transcript 录像带重放恢复状态。 | **核心逻辑**：所有 `advance_turn` 产生的状态必须物理落盘。 |
| **`think_loop.py`** | `ThinkLoop` | 思考循环控制器。执行 9 阶段认知模型。 | **编排者**：协调元认知、工作记忆与模拟引擎。 |
| **`metacognition.py`** | `MetaCognitionController` | 确定性调度规则引擎。 | 根据 `CognitivePressure` 决定是否升级（Escalation）。 |
| **`working_memory.py`** | `WorkingMemoryController` | 模拟生物大脑的注意力分配与槽位管理。 | 管理 `Active` 与 `Suspended` 状态的焦点。 |
| **`temporal.py`** | `CognitiveTemporalEngine` | 内部 agenda 与任务感知引擎。 | **算法**：基于 Staleness 与 Impact 计算 `DelayRiskScore`。 |
| **`simulation_engine.py`** | `CounterfactualSimulationEngine` | 并行反事实分支模拟器。 | **并发安全**：背景任务结果需通过 `snapshot_version` 校验。 |
| **`transcript.py`** | `BrainTranscriptStore` | 追加式物理存储层（JSONL）。 | 提供 `append_entry` 与 `iter_entries` 原子接口. |
| **`memory/`** | `ConsolidationEngine` | **睡眠机制**：后台提炼高复用模式并清理噪音。 | 采用乐观锁保证背景巩固不污染热记忆。 |
| **`cognition/`** | `InteractionMindEngine` | **社会心智**：建模交互对象的意图、知识边界与误解。 | 在模拟阶段推断对方状态，失败时强制降级. |

### 5.3 插件扩展与外部支持 (`src/plugins`)

| 目录/文件名 | 职责描述 | 关键点 |
| :--- | :--- | :--- |
| **`cognitive/`** | 具体的认知工具实现（如：冲突检查、证据权重、排名等）。 | 必须严格继承 `CognitiveToolSpec`。 |
| **`model_providers/`** | 不同模型（Gemini, OpenAI）的接入封装。 | 提供一致的 `generate_json` 接口。 |
| **`simulation/`** | 行业/领域特定的模拟插件（如代码模拟、风险试算）。 | 作为 `SimulationEngine` 的下游算力。 |
| **`provider_tools.py`** | 统一构建入口。 | 负责解析 `provider_tools.yml` 并初始化工厂. |

---

## 6. 关键改进点建议

- **插件热加载**: 当前插件状态在 `dev_server` 中硬编码种子数据，建议将其状态持久化至数据库。
- **多模型竞合**: 在 `Synthesize` 阶段可引入多模型投票机制以增强鲁棒性。
- **Transcripts 回放**: 完善前端的事件流回放功能，支持“时光倒流”式的调试体验。
