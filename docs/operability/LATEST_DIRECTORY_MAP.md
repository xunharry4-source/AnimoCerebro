# 最新目录文档

本文档基于当前工作区实时生成，用于说明仓库的最新目录结构与各目录作用。

生成时间：
- `2026-04-03 21:44:51 CST`

说明：
- 当前项目已进入完全重构、重新开发阶段。
- 当前目录结构应视为重构后的新基线目录，而不是旧版本目录的局部修补。
- 本文档反映的是当前工作区在生成时刻的最新目录状态。
- 若后续新增、删除或迁移目录，应重新生成或更新本文件。
- 为保证可读性，以下目录树省略了 `.git`、`.idea`、`.pytest_cache` 与 `__pycache__`。

按功能组织的插件开发规范索引见：
- [PLUGIN_GUIDES.md](/Users/harry/Documents/git/AnimoCerebro/docs/operability/PLUGIN_GUIDES.md)

## 最新目录树

```text
.
├── docs
│   ├── logo.jpeg
│   └── operability
│       ├── FUNCTION_MODULES.md
│       ├── LATEST_DIRECTORY_MAP.md
│       └── RUNTIME_AND_TESTS.md
├── src
│   ├── admin-portal
│   │   ├── package.json
│   │   ├── vite.config.ts
│   │   └── src
│   │       ├── App.tsx
│   │       ├── main.tsx
│   │       ├── pages
│   │       │   └── dashboard
│   │       │       ├── RealtimeDashboard.test.tsx
│   │       │       └── RealtimeDashboard.tsx
│   │       └── test
│   │           └── setup.ts
│   ├── cloud-audit-admin
│   ├── cloud-audit-web
│   ├── plugins
│   │   ├── __init__.py
│   │   └── provider_tools.py
│   └── zentex
│       ├── bridge
│       ├── cluster
│       ├── cognition
│       ├── core
│       │   ├── models.py
│       │   ├── plugin_base.py
│       │   └── plugin_runtime.py
│       ├── memory
│       ├── network
│       ├── runtime
│       │   ├── cognitive_tools/
│       │   │   └── __init__.py
│       │   ├── metacognition.py
│       │   ├── runtime.py
│       │   ├── self_model.py
│       │   ├── session.py
│       │   ├── temporal.py
│       │   ├── think_loop.py
│       │   ├── transcript.py
│       │   └── working_memory.py
│       ├── safety
│       ├── 协议
│       └── common
│           ├── __init__.py
│           └── plugin_registry.py
├── test
│   └── runtime
│       └── test_transcript.py
└── tests
    ├── common
    │   └── test_plugin_registry.py
    ├── core
    │   ├── test_plugin_base.py
    │   └── test_plugin_runtime.py
    ├── plugins
    │   └── test_provider_tools.py
    ├── runtime
    │   ├── test_cognitive_tools.py
    │   └── test_session.py
    ├── test_cognitive_state.py
    ├── test_metacognition.py
    ├── test_runtime.py
    ├── test_temporal.py
    └── test_think_loop.py
```

## 目录作用说明

### `docs`

文档目录，存放项目说明、运行时说明、目录说明及其他运维或架构文档。

### `docs/operability`

运维与架构说明目录，当前主要承载以下文档：
- `FUNCTION_MODULES.md`：功能模块与技术架构总览。
- `RUNTIME_AND_TESTS.md`：运行时代码与测试覆盖说明。
- `LATEST_DIRECTORY_MAP.md`：当前最新目录结构说明。
- `STARTUP_AND_TEST.md`：前后端启动与测试执行说明。

### `src`

源码主目录，承载系统各业务模块与 Zentex 核心运行时模块。

### `src/admin-portal`

后台管理页面前端目录，用于系统通用管理端能力。

关键文件：
- `src/admin-portal/package.json`：前端依赖与脚本入口。
- `src/admin-portal/vite.config.ts`：Vite 与 Vitest 配置。
- `src/admin-portal/src/pages/dashboard/RealtimeDashboard.tsx`：实时指挥台页面。
- `src/admin-portal/src/pages/dashboard/RealtimeDashboard.test.tsx`：实时指挥台前端测试。
- `src/admin-portal/src/test/setup.ts`：前端测试初始化。

### `src/cloud-audit-admin`

云审计后台管理功能目录，用于规则、任务、策略和配置管理。

### `src/cloud-audit-web`

云审计业务 Web 页面目录，用于审计查询、风险展示、报表查看等前端能力。

### `src/plugins`

工具目录，用于承载第三方模型与外部能力的调用方法封装。

关键文件：
- `src/plugins/provider_tools.py`：OpenAI、ChatGPT、Gemini、Claude 的统一工具调用方法。
- `src/plugins/__init__.py`：plugins 包入口。

### `src/zentex`

Zentex 核心能力域目录，承载外部大脑的各核心子模块。

### `src/zentex/bridge`

宿主桥接与感知执行相关模块目录，用于宿主接入、协议门面和桥接适配。

### `src/zentex/cluster`

弹性运行时底座目录，用于集群、高可用、调度和共享状态接入相关能力。

### `src/zentex/cognition`

核心认知中枢目录，用于推理流程、决策编排和认知主链能力。

### `src/zentex/core`

核心共享模型目录，用于承载运行时状态投影、统一插件基类与插件运行态契约。

关键文件：
- `src/zentex/core/models.py`：`BrainRuntimeState` 统一运行态投影。
- `src/zentex/core/plugin_base.py`：`BasePluginSpec` 统一插件基类。
- `src/zentex/core/plugin_runtime.py`：插件健康、回退、撤销、加载结果等运行态契约。

### `src/zentex/memory`

记忆与自我演化目录，用于长期记忆、经验沉淀和记忆治理能力。

### `src/zentex/network`

组织协作网络目录，用于多智能体通信、发现、共识和经验交换能力。

### `src/zentex/runtime`

运行时实现目录，是当前已落地代码最集中的核心目录，主要包含：
- transcript 事件流存储
- session 会话容器
- think loop 单轮认知循环
- runtime 运行时大管家
- cognitive tools 工具注册与编排
- metacognition 元认知调度
- working memory 工作记忆控制
- self model 活的自我模型
- temporal 内部时间感引擎

关键文件：
- `src/zentex/runtime/transcript.py`
- `src/zentex/runtime/session.py`
- `src/zentex/runtime/think_loop.py`
- `src/zentex/runtime/runtime.py`
- `src/zentex/runtime/cognitive_tools/__init__.py`
- `src/zentex/runtime/metacognition.py`
- `src/zentex/runtime/working_memory.py`
- `src/zentex/runtime/self_model.py`
- `src/zentex/runtime/temporal.py`

补充说明：
- `src/zentex/core/cognitive_tools_spec.py` 是认知工具契约层。
- `src/zentex/runtime/cognitive_tools/__init__.py` 是认知工具执行层。
- 两者职责不同，不是重复实现。

### `src/zentex/safety`

安全风控与人类监督目录，用于风险识别、权限控制、审计联动和人工监督。

### `src/zentex/协议`

协议目录，用于对外协议定义、接口契约和消息模型约定。

### `src/zentex/common`

common 目录，用于沉淀跨模块共享的规则依据、约束模型与基础抽象。

关键文件：
- `src/zentex/common/plugin_registry.py`：统一插件生命周期注册表与状态机海关。
- `src/zentex/common/__init__.py`：common 包入口。

### `test`

历史测试目录，当前仍保留较早创建的测试文件。

### `test/runtime`

历史运行时测试目录，当前保留 `test_transcript.py`。

### `tests`

当前主测试目录，新的测试文件主要集中在这里。

当前主要测试分层：
- `tests/core`：核心基类与插件运行态契约测试。
- `tests/common`：通用注册表与生命周期状态机测试。
- `tests/plugins`：外部模型工具方法测试。
- `tests/runtime`：运行时子模块测试。

### `tests/runtime`

运行时子模块测试目录，当前主要包含：
- `test_cognitive_tools.py`
- `test_session.py`

### `tests/core`

核心插件基类与运行时契约测试目录，当前主要包含：
- `test_plugin_base.py`
- `test_plugin_runtime.py`

### `tests/common`

通用基础抽象测试目录，当前主要包含：
- `test_plugin_registry.py`

### `tests/plugins`

外部工具方法测试目录，当前主要包含：
- `test_provider_tools.py`

### `tests/test_cognitive_state.py`

用于测试 `WorkingMemoryController` 与 `LivingSelfModelEngine`。

### `tests/test_metacognition.py`

用于测试 `MetaCognitionController` 的硬规则与边界。

### `tests/test_runtime.py`

用于测试 `BrainRuntime` 的装配、会话管理与运行态投影。

### `tests/test_temporal.py`

用于测试 `CognitiveTemporalEngine` 的时间窗口、过期治理、冷却抑制与可序列化能力。

### `tests/test_think_loop.py`

用于测试 `ThinkLoop` 的无状态执行、9 阶段顺序与结果组装。

## 当前状态结论

截至 `2026-04-03 21:44:51 CST`，仓库已经形成以下结构特征：

- 项目处于完全重构、重新开发后的新阶段。
- 当前目录结构用于承载新的运行时主链与新的测试体系。
- 文档集中在 `docs/operability`
- 源码集中在 `src`
- Zentex 核心能力集中在 `src/zentex`
- 运行时代码集中在 `src/zentex/runtime`
- 插件基类与运行态契约集中在 `src/zentex/core`
- 通用插件注册表集中在 `src/zentex/common`
- 外部模型调用工具方法集中在 `src/plugins/provider_tools.py`
- 测试目录目前仍存在 `test` 与 `tests` 并存的历史状态

## 后续建议

- 将历史 `test/runtime/test_transcript.py` 逐步迁移到 `tests/runtime`
- 在 `src/zentex/runtime` 下继续保持模块化拆分，避免重新回到单体 `brain.py`
- 每次新增核心目录或测试目录后，同步更新本文件，保证目录文档始终是最新版本
