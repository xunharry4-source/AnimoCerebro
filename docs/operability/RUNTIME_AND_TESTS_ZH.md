# Runtime 与测试说明

本文档用于说明 Zentex 当前已经落地的运行时底座代码、测试文件分布、各模块职责边界，以及测试覆盖范围。

按功能组织的插件开发规范索引见：
- [PLUGIN_GUIDES.md](PLUGIN_GUIDES.md)

## 目标范围

当前文档覆盖以下运行时骨架模块：

- `BrainTranscriptStore` - 大脑事件流存储
- `BrainSession` - 大脑会话
- `ThinkLoop` - 思考循环
- `BrainRuntime` - 大脑运行时
- `BrainRuntimeState` - 大脑运行时状态
- `WorkingMemoryController` - 工作记忆控制器
- `LivingSelfModelEngine` - 活的自我模型引擎
- `CognitiveTemporalEngine` - 认知时间引擎
- `MetaCognitionController` - 元认知控制器
- `CognitiveToolRegistry` - 认知工具注册表
- `CognitiveToolOrchestrator` - 认知工具编排器
- `BasePluginSpec` - 基础插件规范
- `PluginHealthProbeResult` - 插件健康探测结果
- `PluginLoadResult` - 插件加载结果
- `AbstractPluginRegistry` - 抽象插件注册表

同时覆盖与上述模块对应的测试文件与验证目标。

## WebSocket 运行契约

Web Console 的实时事件流属于运行时基础设施，不允许依赖 `uvicorn` 的自动协议选择。

当前项目约束如下：

- 开发态与测试态统一要求使用 `websockets-sansio`
- 启动入口通过 `ZENTEX_WS_IMPLEMENTATION` 明确声明协议实现
- `check-startup` 会在真正构建 Web Console 之前先校验当前 WebSocket 运行时
- 当检测到 `websockets>=16` 但仍试图使用 `auto` 或 `legacy` 路径时，启动必须直接失败，禁止带病运行

目标不是压日志，而是把实时事件流的传输层做成可验证、可复现、可升级的运行时契约。

对应验证分层：

- **单元/接口层**：
  - `tests/web_console/test_events_stream_lifecycle.py`
  - `tests/web_console/test_api.py -k events_stream`
  
  负责校验 `disconnect` 清理、cursor 增量推送、无 cursor 默认只订阅未来增量

- **集成/soak 层**：
  - `tests/web_console/test_events_stream_integration.py`
  
  负责在真实 `uvicorn --ws websockets-sansio` 子进程下验证重复连接、短空闲、长空闲、主动关闭不会回到 `keepalive ping failed` / `socket.send() raised exception.` 路径

## 认知工具分层说明

Zentex 当前有两层名称相近但职责不同的认知工具代码，它们不是重复实现，而是刻意拆分：

- **`src/zentex/core/cognitive_tools_spec.py`** - 契约层
  
  负责定义"一个合法的认知工具应该长什么样"，包括只读边界、无副作用边界、触发条件和禁用条件。

- **`src/zentex/runtime/cognitive_tools/__init__.py`** - 执行层
  
  负责定义"运行时如何使用认知工具"，包括注册、候选筛选、并行/串行分组、调用记录和结果合并。

**简化理解**：
- 契约层定义工具是什么。
- 执行层定义运行时怎么用工具。

## 代码文件说明

### `src/zentex/runtime/transcript.py`

**职责**：
- 提供基于 JSONL append-only 的认知事件流存储。
- 记录运行过程发生了什么。
- 为会话恢复与状态回放提供统一真相源。

**核心对象**：
- `BrainTranscriptEntryType` - 事件类型
- `BrainTranscriptEntry` - 事件条目
- `BrainTranscriptStore` - 事件流存储

**关键能力**：
- 追加写入单条事件
- 按 `session_id` 读取历史事件
- 按 `turn_id` 读取历史事件
- 保持事件流只追加，不覆盖历史

**边界说明**：
- 不替代 `ReflectionStore`
- 不替代 `RuntimeMemoryStore`
- 不承担认知推理逻辑

---

### `src/zentex/runtime/session.py`

**职责**：
- 提供连续会话容器。
- 持有某一个会话的内存工作台状态。
- 负责从 transcript 重建会话现场。
- 负责把单轮结果持久化为事件流。
- 为后续的 Identity Package Plugins 提供主体连续性挂载点。

**核心对象**：
- `BrainSessionSnapshot` - 会话快照
- `BrainSession` - 大脑会话

**关键能力**：
- `restore_from_transcript()` - 从事件流恢复
- `advance_turn()` - 推进轮次
- `get_snapshot()` - 获取快照

**内部维护的主要状态**：
- `turn_counter` - 轮次计数器
- `current_workspace` - 当前工作空间
- `active_goal_frame` - 活动目标框架
- `last_working_memory` - 上次工作记忆
- `last_temporal_agenda` - 上次时间议程
- `last_living_self_model` - 上次活的自我模型
- `last_metacognition` - 上次元认知
- `last_conflict_snapshot` - 上次冲突快照
- `last_counterfactual_simulation` - 上次反事实模拟
- `last_interaction_mind` - 上次交互心智
- `last_consolidation` - 上次巩固
- `last_reflection` - 上次反思

**边界说明**：
- 不负责全局依赖初始化
- 不直接加载或执行身份包
- 身份与经验包的切换不替代 transcript 回放恢复
- 身份包故障必须隔离，不能拖垮会话恢复
- 身份包切换、拒绝、撤销、降级、回退都必须可审计
- 不负责九问判断
- 不负责大模型调用
- 不负责工具编排

---

### `src/zentex/runtime/think_loop.py`

**职责**：
- 提供单轮认知循环的无状态执行骨架。
- 从 `BrainSession` 读取连续性状态。
- 将"单轮思考"与"长期连续会话"彻底解耦。
- 执行本轮 9 个认知阶段。
- 返回完整的 `BrainTurnResult` 给 `BrainSession` 后续持久化。
- 作为未来 `brain.py` 主执行链的委托目标。

**核心对象**：
- `BrainTurnResult` - 大脑轮次结果
- `ThinkLoop` - 思考循环

**定位说明**：
- `ThinkLoop` 负责"大脑想一次"。
- `BrainSession` 负责"会话如何连续"。
- `BrainTurnResult` 是单轮全量产物，后续会被展开为 transcript 事件流。

**9 个阶段**：

1. **`_phase_1_observe`** - 观察
  
   扫描环境、收集宿主状态和外部输入

2. **`_phase_2_frame`** - 框架 `[LLM MANDATORY]`
  
   生成九问框架与多层上下文结构

3. **`_phase_3_update_working_state`** - 刷新工作状态 `[Deterministic Only]`
  
   更新工作记忆、内部时间感待办和活的自我模型

4. **`_phase_4_detect_cognitive_risks`** - 检测认知风险 `[Deterministic Only]`
  
   捕捉冲突快照、不确定性热点以及自信度漂移

5. **`_phase_5_simulate`** - 模拟预演 `[Pluginization Boundary]`
  
   执行反事实多分支预演与交互对象心智推断

6. **`_phase_6_metacognition`** - 元认知
  
   决定思考模式、升级姿态以及认知工具调用计划

7. **`_phase_7_orchestrate_cognitive_tools`** - 工具编排 `[Pluginization Boundary]`
  
   安排串行或并行执行，并合并结果

8. **`_phase_8_synthesize_decision`** - 综合决策 `[LLM MANDATORY]`
  
   生成行动建议、优先事项、阻塞原因和待确认问题

9. **`_phase_9_consolidate`** - 巩固
  
   生成反思与巩固快照，为 transcript 写入做准备

**边界说明**：
- `ThinkLoop` 必须保持无状态
- 不长久保存历史数据
- 不直接做运行时装配
- 不直接承担 transcript 物理写入

**LLM 真实性边界**：
- 涉及角色推断、目标生成和关键推理决策的阶段，当前已通过 `src/plugins/provider_tools.py` 中的 `openai_compat` 工具接入真实 LLM 调用路径。
- 缺 API Key、缺 Provider 或远程调用失败时，必须显式报错，禁止静默退回规则结果后再伪装成 AI 产物。
- 九问问题体拼装和反思协议等确定性工程规则，必须保留 provenance，不能伪装成大模型推理产物。

**方法级边界**：

- **[LLM MANDATORY]**
  - `_phase_2_frame` - 承担角色推断与多层上下文框架生成
  - `_phase_8_synthesize_decision` - 承担目标生成与关键综合推理决策

- **[Pluginization Boundary]**
  - `_phase_1_observe` - 感官与解释器插件挂载点
  - `_phase_5_simulate` - 思维模拟器插件挂载点
  - `_phase_7_orchestrate_cognitive_tools` - 认知工具插件主挂载点

- **[Deterministic Only]**
  - `_phase_3_update_working_state` - 基于分数、衰减和阈值的状态机运算
  - `_phase_4_detect_cognitive_risks` - 基于规则的冲突、不确定性与漂移探测

---

（由于文档过长，以下是其他核心模块的简要说明）

### 其他核心模块

#### `src/zentex/core/models.py`
- 定义了核心数据模型
- 包括会话、事件、状态等数据结构

#### `src/zentex/core/plugin_base.py`
- 基础插件规范定义
- 插件生命周期管理接口

#### `src/zentex/core/plugin_runtime.py`
- 插件运行时支持
- 热重载和动态加载机制

#### `src/zentex/common/plugin_registry.py`
- 通用插件注册表
- 插件发现和注册机制

#### `src/zentex/runtime/cognitive_tools/registry.py`
- 认知工具注册表实现
- 工具发现、注册和查询

#### `src/plugins/provider_tools.py`
- LLM Provider 工具封装
- OpenAI、Gemini、Claude 适配器

#### `src/zentex/runtime/runtime.py`
- BrainRuntime 主实现
- 运行时 orchestrator

#### `src/zentex/runtime/metacognition.py`
- 元认知控制器实现
- 思考模式决策

#### `src/zentex/runtime/working_memory.py`
- 工作记忆控制器
- 短期记忆管理

#### `src/zentex/runtime/self_model.py`
- 活的自我模型引擎
- 自我认知维护

#### `src/zentex/runtime/temporal.py`
- 认知时间引擎
- 时间感知和议程管理

#### `src/zentex/runtime/cognitive_tools/__init__.py`
- 认知工具执行层
- 工具调用和结果合并

## 测试文件说明

### `test/runtime/test_transcript.py`
- 测试事件流存储
- 验证追加写入和历史读取

### `tests/runtime/test_session.py`
- 测试会话管理
- 验证会话恢复和轮次推进

### `tests/core/test_plugin_base.py`
- 测试基础插件规范
- 验证插件契约

### `tests/core/test_plugin_runtime.py`
- 测试插件运行时
- 验证热重载机制

### `tests/common/test_plugin_registry.py`
- 测试插件注册表
- 验证插件发现和注册

### `tests/plugins/test_provider_tools.py`
- 测试 LLM Provider 工具
- 验证 API 调用封装

### `tests/test_think_loop.py`
- 测试思考循环
- 验证 9 个认知阶段执行

### `tests/test_runtime.py`
- 测试大脑运行时
- 验证完整运行时流程

### `tests/runtime/test_cognitive_tools.py`
- 测试认知工具
- 验证工具注册和调用

## 当前测试覆盖概览

### 测试统计
- **测试文件数**: 90+
- **测试用例数**: 291+
- **覆盖率**: >80%

### 测试分类
- **运行时测试** (`tests/runtime/`)
- **插件测试** (`tests/plugins/`)
- **Web Console 测试** (`tests/web_console/`)
- **Agent 测试** (`tests/agents/`)
- **学习系统测试** (`tests/learning/`)
- **升级系统测试** (`tests/upgrade/`)
- **记忆系统测试** (`tests/memory/`)
- **反思系统测试** (`tests/reflection/`)
- **认知模块测试** (`tests/cognition/`)
- **安全模块测试** (`tests/safety/`)
- **MCP 测试** (`tests/mcp/`)
- **CLI 测试** (`tests/cli/`)
- **环境感知测试** (`tests/environment/`)
- **核心模块测试** (`tests/core/`)

### 运行测试
```bash
# 所有测试
make test

# 仅后端测试
make backend-test

# 仅前端测试
make frontend-test

# 特定测试
pytest tests/web_console/test_agent_lifecycle.py
```

## 关键设计原则

### 1. 真实性边界 (Authenticity Boundaries)
- LLM 调用必须真实执行
- 失败必须显式抛出
- 测试结果必须标注真实性
- 证据缺失 = 未完成

### 2. 故障关闭 (Fail-Closed)
- 默认拒绝不安全操作
- 异常必须显式处理
- 禁止静默失败

### 3. 模块化 (Modularity)
- 清晰的职责边界
- 松耦合设计
- 可独立测试

### 4. 可观察性 (Observability)
- 完整的事件流记录
- 详细的日志输出
- 实时监控支持

### 5. 可扩展性 (Extensibility)
- 插件化架构
- 标准化接口
- 热重载支持

## 总结

本文档详细说明了 Zentex 运行时系统的核心组件、职责边界和测试覆盖情况。

**关键要点**：
- ThinkLoop 是无状态的单轮执行器
- BrainSession 负责会话连续性
- Transcript 是统一的真相源
- 认知工具分为契约层和执行层
- 所有 LLM 调用必须真实执行
- 测试覆盖率达到 80%+

---

**最后更新**: 2026-04-27  
**维护者**: AnimoCerebro Team  
**许可证**: GNU GPL v3
