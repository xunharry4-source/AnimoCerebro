# 最新目录文档

本文档基于当前工作区实时生成，用于说明仓库的最新目录结构与各目录作用。

**生成时间**：2026-04-09

**项目状态**：
- ✅ 当前项目已进入**生产就绪**阶段，核心功能全部实现
- ✅ 测试覆盖：**90个测试文件，291+测试用例**
- ✅ 后端路由：**18个API路由器**
- ✅ 前端页面：**26+九问页面 + 其他管理页面**
- ✅ 九问插件：**Q1-Q9完整覆盖，69+文件**

**说明**：
- 当前目录结构应视为稳定基线目录
- 本文档反映的是当前工作区在生成时刻的最新目录状态
- 若后续新增、删除或迁移目录，应重新生成或更新本文件
- 为保证可读性，以下目录树省略了 `.git`、`.idea`、`.pytest_cache` 与 `__pycache__`

**相关文档**：
- [项目总结](./项目总结_当前实现概览.md)
- [功能完成度报告](./功能完成度报告_2026-04-08.md)
- [启动与测试说明](./STARTUP_AND_TEST.md)

## 最新目录树

```text
AnimoCerebro-V2/
├── config/                         # 配置文件
│   └── provider_tools.yml          # LLM Provider 配置（openai, gemini, claude等）
├── docs/                           # 项目文档
│   ├── logo.jpeg                   # 项目Logo
│   ├── module_service_guidelines.md  # 模块服务门面规范
│   ├── zmsp_protocol_design.md     # 记忆共享协议设计
│   └── operability/                # 可操作性文档
│       ├── AGENT_AND_MCP.md        # Agent & MCP 管理指南
│       ├── FUNCTION_MODULES.md     # 功能模块与技术架构总览
│       ├── LATEST_DIRECTORY_MAP.md # 当前文档
│       ├── PLUGIN_GUIDES.md        # 插件开发指南
│       ├── RUNTIME_AND_TESTS.md    # 运行时代码与测试覆盖说明
│       ├── STARTUP_AND_TEST.md     # 前后端启动与测试执行说明
│       ├── THINK_LOOP_DEEP_DIVE.md # ThinkLoop 深度解析
│       ├── 功能完成度报告_2026-04-08.md
│       ├── 项目总结_当前实现概览.md
│       ├── 项目文件拆分_按功能.md
│       └── plugin_features/        # 插件特性文档（16个文件）
├── scripts/                        # 启动和管理脚本
│   ├── dev_all.sh                  # 一键启动所有服务（后端+前端）
│   ├── restart_dev.sh              # 重启开发环境（清理+重启）
│   ├── restart_backend.sh          # 单独重启后端
│   ├── restart_frontend.sh         # 单独重启前端
│   ├── setup_env.sh                # 环境初始化（后端.venv + 前端npm）
│   ├── test_all.sh                 # 运行所有测试
│   ├── ide_engineering_monitor.py  # IDE工程监控
│   ├── migrate_to_msgpack.py       # 数据迁移脚本
│   ├── pre_commit_engineering_check.py  # 预提交工程检查
│   └── test_engineering_validation.py   # 工程验证测试
├── src/
│   ├── admin-portal/               # React + Vite 管理前端（完整实现）
│   │   ├── package.json            # 前端依赖
│   │   ├── vite.config.ts          # Vite 配置
│   │   ├── tsconfig.json           # TypeScript 配置
│   │   ├── index.html              # HTML 入口
│   │   └── src/
│   │       ├── main.tsx            # 应用入口
│   │       ├── App.tsx             # 根组件
│   │       ├── i18n.ts             # 国际化配置（中英文）
│   │       ├── api/                # API 客户端
│   │       ├── components/         # 通用组件（12个）
│   │       ├── pages/              # 页面组件
│   │       │   ├── dashboard/      # 实时指挥台（6个文件）
│   │       │   ├── nine-questions/ # 九问页面（26个文件）
│   │       │   ├── agents/         # Agent 管理（4个文件）
│   │       │   ├── tasks/          # 任务管理（2个文件）
│   │       │   ├── plugins/        # 插件管理
│   │       │   ├── mcp/            # MCP 管理（2个文件）
│   │       │   ├── audit/          # 审计回放（2个文件）
│   │       │   ├── learning/       # 学习管理
│   │       │   ├── upgrades/       # 升级管理（3个文件）
│   │       │   ├── cli/            # CLI 适配器（2个文件）
│   │       │   └── test/           # 测试页面（3个文件）
│   │       └── test/               # 前端测试
│   │           └── setup.ts        # 测试初始化
│   ├── plugins/                    # 插件实现层（生产就绪）
│   │   ├── README.md               # 插件说明
│   │   ├── __init__.py             # 包入口
│   │   ├── provider_tools.py       # LLM Provider 工具装配
│   │   ├── nine_questions/         # Q1-Q9 完整插件家族（69+文件）
│   │   │   ├── q1_where_am_i/      # Q1: 环境感知（11个文件）
│   │   │   ├── q2_who_am_i/        # Q2: 角色假设（8个文件）
│   │   │   ├── q3_what_do_i_have/  # Q3: 资源盘点（8个文件）
│   │   │   ├── q4_what_can_i_do/   # Q4: 能力边界（5个文件）
│   │   │   ├── q5_allowed/         # Q5: 约束检查（5个文件）
│   │   │   ├── q6_consequences/    # Q6: 风险评估（9个文件）
│   │   │   ├── q7_alternatives/    # Q7: 替代方案（6个文件）
│   │   │   ├── q8_priority/        # Q8: 优先级决策（6个文件）
│   │   │   ├── q9_action/          # Q9: 行动确认（7个文件）
│   │   │   └── _shared.py          # 共享模块
│   │   ├── model_providers/        # LLM Provider 插件（3个文件）
│   │   ├── cognitive/              # 认知工具插件（5个文件）
│   │   ├── execution/              # 执行插件（CLI, MCP）（3个文件）
│   │   ├── sensory/                # 感知插件（4个文件）
│   │   ├── simulation/             # 模拟插件（3个文件）
│   │   ├── memory/                 # 记忆插件（2个文件）
│   │   ├── weights/                # 权重插件（3个文件）
│   │   └── reflection/             # 反思插件（2个文件）
│   └── zentex/                     # 核心后端与运行时（高度成熟）
│       ├── runtime/                # 运行时主链（九阶段认知循环）
│       │   ├── README.md
│       │   ├── runtime.py          # BrainRuntime 运行时大管家
│       │   ├── session.py          # BrainSession 会话容器
│       │   ├── think_loop.py       # ThinkLoop 九阶段认知执行器
│       │   ├── transcript.py       # BrainTranscriptStore 转录存储
│       │   ├── working_memory.py   # WorkingMemoryController 工作记忆
│       │   ├── metacognition.py    # MetacognitionController 元认知
│       │   ├── self_model.py       # LivingSelfModelEngine 活体自我模型
│       │   ├── temporal.py         # TemporalEngine 时间议程引擎
│       │   ├── conflict.py         # ConflictEngine 冲突检测引擎
│       │   ├── nine_question_executor.py  # NineQuestionExecutor 九问执行器
│       │   ├── nine_question_router.py    # NineQuestionRouter 九问路由器
│       │   ├── nine_question_state.py     # NineQuestionState 九问状态
│       │   ├── cognitive_tools/    # 认知工具注册与编排
│       │   └── intervention.py     # 人工干预控制平面
│       ├── web_console/            # FastAPI 控制台后端（完整 API）
│       │   ├── README.md
│       │   ├── dev_server.py       # 开发态 Web Console 服务（74.6KB）
│       │   ├── app.py              # 生产态应用装配
│       │   ├── api.py              # API 入口
│       │   ├── router.py           # 路由注册
│       │   ├── dependencies.py     # 依赖注入
│       │   ├── replay_builder.py   # Transcript 回放构建器
│       │   ├── service.py          # 服务层
│       │   ├── contracts/          # 数据契约（18个文件）
│       │   ├── routers/            # API 路由器（18个）
│       │   │   ├── overview.py     # 运行态概览
│       │   ├── services/           # 业务服务（11个文件）
│       │   └── errors.py           # 错误处理
│       ├── agents/                 # Agent 管理与协同（6个文件）
│       │   ├── README.md
│       │   ├── manager.py          # Agent 管理器
│       │   ├── collaboration.py    # Agent 协同服务
│       │   └── models.py           # Agent 模型
│       ├── tasks/                  # 任务分解与任务服务（22个文件）
│       │   ├── README.md
│       │   ├── models.py           # 任务模型
│       │   ├── decomposer.py       # 任务分解器
│       │   └── service.py          # 任务服务层
│       ├── mcp/                    # MCP 适配层（6个文件）
│       │   ├── README.md
│       │   ├── client.py           # MCP 客户端
│       │   └── server_manager.py   # MCP 服务器管理
│       ├── learning/               # G16 学习引擎（DSPy 集成）（12个文件）
│       │   ├── README.md
│       │   ├── engine.py           # G16 学习引擎
│       │   ├── dspy_adapter.py     # DSPy 适配器
│       │   ├── budget.py           # 预算管理
│       │   └── sandbox.py          # 沙箱执行
│       ├── upgrade/                # 受控自我进化系统（18个文件）
│       │   ├── README.md
│       │   ├── facade.py           # 升级Facade
│       │   ├── execution.py        # 执行服务
│       │   ├── evidence.py         # 证据服务
│       │   ├── audit.py            # 审计存储
│       │   └── plugin_evolution.py # 插件演化运行时
│       ├── memory/                 # 增强记忆系统（Kuzu 后端）（11个文件）
│       │   ├── README.md
│       │   ├── service.py          # 增强记忆服务
│       │   ├── kuzu_backend.py     # Kuzu 图数据库后端
│       │   ├── consolidation.py    # 记忆巩固引擎
│       │   └── management/         # 记忆管理层
│       ├── reflection/             # 元认知反思系统（11个文件）
│       │   ├── README.md
│       │   ├── DOCUMENTATION.md    # 完整文档
│       │   ├── service_facade.py   # 反思服务门面
│       │   ├── models.py           # 反思模型
│       │   └── persistence.py      # 持久化层
│       ├── cognition/              # 社会心智/模拟等认知模块（6个文件）
│       │   ├── README.md
│       │   ├── social_mind.py      # 社会心智
│       │   └── simulation.py       # 反事实模拟
│       ├── safety/                 # 风险与冲突控制（11个文件）
│       │   ├── README.md
│       │   ├── service.py          # 安全服务
│       │   └── policy.py           # 安全策略
│       ├── environment/            # 环境感知与指纹识别（19个文件）
│       │   ├── README.md
│       │   ├── fingerprint.py      # 环境指纹
│       │   └── detector.py         # 变化检测器
│       ├── core/                   # 统一模型、插件契约、配置（19个文件）
│       │   ├── README.md
│       │   ├── models.py           # BrainRuntimeState 统一运行态投影
│       │   ├── plugin_base.py      # BasePluginSpec 统一插件基类
│       │   ├── plugin_runtime.py   # 插件运行态契约
│       │   └── config.py           # 配置管理
│       ├── common/                 # 通用注册表与共享抽象（9个文件）
│       │   ├── README.md
│       │   ├── plugin_registry.py  # 统一插件生命周期注册表
│       │   └── event_bus.py        # 事件总线
│       ├── llm/                    # LLM 网关（5个文件）
│       │   ├── README.md
│       │   ├── gateway.py          # LLM 网关
│       │   └── guard.py            # LLM 守卫（fail-closed）
│       ├── cli/                    # CLI 适配器（5个文件）
│       │   ├── README.md
│       │   └── adapter.py          # CLI 适配器
│       └── tools/                  # 工具侧接口（4个文件）
│           ├── README.md
│           └── registry.py         # 工具注册表
├── tests/                          # 当前主要测试目录（全面覆盖）
│   ├── conftest.py                 # pytest 配置
│   ├── runtime/                    # 运行时测试
│   ├── plugins/                    # 插件测试
│   ├── web_console/                # Web Console 测试
│   ├── agents/                     # Agent 测试
│   ├── learning/                   # 学习系统测试
│   ├── upgrade/                    # 升级系统测试
│   ├── memory/                     # 记忆系统测试
│   ├── reflection/                 # 反思系统测试
│   ├── cognition/                  # 认知模块测试
│   ├── safety/                     # 安全模块测试
│   ├── mcp/                        # MCP 测试
│   ├── cli/                        # CLI 测试
│   ├── environment/                # 环境感知测试
│   ├── core/                       # 核心模块测试
│   ├── common/                     # 通用模块测试
│   ├── llm/                        # LLM 测试
│   ├── tools/                      # 工具测试
│   ├── test_phase1_e2e_integration.py  # Phase 1 端到端集成测试
│   ├── test_phase3_evolution.py        # Phase 3 进化系统测试（4个测试）
│   ├── test_phase4_memory.py           # Phase 4 记忆巩固测试（4个测试）
│   ├── test_real_business_cases.py     # 真实业务场景测试（5个测试）
│   ├── test_think_loop.py              # ThinkLoop 测试（5个测试）
│   ├── test_metacognition.py           # 元认知测试
│   ├── test_cognitive_state.py         # 认知状态测试
│   └── ...                             # 其他测试文件
├── test/                           # 早期测试目录（待迁移）
│   └── runtime/
│       └── test_transcript.py
├── config/                         # 配置文件
│   └── provider_tools.yml          # LLM Provider 配置
├── .env.example                    # 环境变量示例
├── .env                            # 环境变量（本地配置，不提交）
├── Makefile                        # 一键启动/测试入口
├── requirements.txt                # Python 生产依赖
├── requirements-dev.txt            # Python 开发依赖
├── pytest.ini                      # pytest 配置
├── README.md                       # 项目主文档
├── IMPLEMENTATION_SUMMARY.md       # 实现总结
├── WEB_API_TESTS_SUMMARY.md        # Web API 测试总结
├── LEARNING_TESTS_ANALYSIS.md      # 学习测试分析
├── MEMORY_TEST_RESULTS.md          # 记忆测试结果
├── Phase4_Implementation_Analysis.md  # Phase 4 实现分析
└── Zentex_产品功能文档/            # 产品功能文档
    ├── 01_系统总体定义.md
    ├── 02_核心架构.md
    ├── 03_运行时主链.md
    ├── 04_模拟学习.md
    ├── 05_协作执行.md
    ├── 06_社会与商业.md
    ├── 07_基础设施.md
    ├── 08_云审计.md
    ├── 09_Web控制台.md
    └── 10_实施计划.md
```

## 目录作用说明

### `config`

配置文件目录，存放系统配置。

关键文件：
- `provider_tools.yml`：LLM Provider 配置，支持 openai_compat、openai、gemini、claude 等多个提供商

### `docs`

文档目录，存放项目说明、架构设计、API文档等。

关键子目录：
- `docs/operability/`：可操作性文档，包含启动、测试、插件开发等实用指南

### `docs/operability`

运维与架构说明目录，当前主要承载以下文档：
- `FUNCTION_MODULES.md`：功能模块与技术架构总览
- `RUNTIME_AND_TESTS.md`：运行时代码与测试覆盖说明
- `LATEST_DIRECTORY_MAP.md`：当前最新目录结构说明（本文档）
- `STARTUP_AND_TEST.md`：前后端启动与测试执行说明
- `THINK_LOOP_DEEP_DIVE.md`：ThinkLoop 九阶段认知循环深度解析
- `AGENT_AND_MCP.md`：Agent & MCP 管理指南
- `PLUGIN_GUIDES.md`：插件开发指南
- `项目总结_当前实现概览.md`：项目整体实现状态总结
- `功能完成度报告_2026-04-08.md`：功能完成度详细报告
- `plugin_features/`：插件特性文档（16个文件）

### `scripts`

启动和管理脚本目录，提供一键式操作命令。

关键脚本：
- `dev_all.sh`：一键启动所有服务（后端 + 前端），带依赖检查和健康检查
- `restart_dev.sh`：重启开发环境，清理旧进程和大型运行时文件
- `restart_backend.sh`：单独重启后端服务
- `restart_frontend.sh`：单独重启前端服务
- `setup_env.sh`：环境初始化，安装后端.venv和前端npm依赖
- `test_all.sh`：运行所有测试（Python + 前端）
- `pre_commit_engineering_check.py`：预提交工程检查
- `migrate_to_msgpack.py`：数据迁移脚本（JSON -> MsgPack）

### `src`

源码主目录，承载系统各业务模块与 Zentex 核心运行时模块。

### `src/admin-portal`

后台管理页面前端目录，基于 React + Vite + TypeScript 构建。

关键文件：
- `package.json`：前端依赖与脚本入口
- `vite.config.ts`：Vite 与 Vitest 配置
- `src/main.tsx`：应用入口
- `src/App.tsx`：根组件，路由配置
- `src/i18n.ts`：国际化配置（中英文）
- `src/pages/dashboard/RealtimeDashboard.tsx`：实时指挥台页面
- `src/pages/nine-questions/`：九问相关页面（26个组件）
- `src/api/`：API 客户端封装
- `src/components/`：通用组件库（12个组件）

### `src/plugins`

插件实现层，承载各种类型的插件扩展能力。

关键文件：
- `provider_tools.py`：OpenAI、ChatGPT、Gemini、Claude 的统一工具调用方法
- `nine_questions/`：Q1-Q9 完整插件家族（69+文件）
- `model_providers/`：LLM Provider 插件
- `cognitive/`：认知工具插件
- `execution/`：执行插件（CLI, MCP）
- `sensory/`：感知插件
- `simulation/`：模拟插件
- `memory/`：记忆插件
- `weights/`：权重插件
- `reflection/`：反思插件

### `src/zentex`

Zentex 核心能力域目录，承载外部大脑的各核心子模块。

### `src/zentex/runtime`

运行时实现目录，是当前已落地代码最集中的核心目录，实现完整的九阶段认知循环。

关键文件：
- `runtime.py`：BrainRuntime 运行时大管家，负责装配依赖、管理会话、维护状态
- `session.py`：BrainSession 会话容器，支持从 transcript 完全恢复
- `think_loop.py`：ThinkLoop 九阶段认知执行器，实现观察→框架化→工作状态刷新→风险检测→模拟→元认知→工具编排→决策综合→巩固
- `transcript.py`：BrainTranscriptStore JSONL 事件流存储，支持按 session_id/turn_id 高效读取
- `working_memory.py`：WorkingMemoryController 工作记忆控制器，支持注意力项管理
- `metacognition.py`：MetacognitionController 元认知控制器，生成推理模式和工具计划
- `self_model.py`：LivingSelfModelEngine 活体自我模型引擎，动态更新认知状态画像
- `temporal.py`：TemporalEngine 时间议程引擎，评估时间敏感事项
- `conflict.py`：ConflictEngine 冲突检测引擎，识别认知风险和置信度漂移
- `nine_question_executor.py`：NineQuestionExecutor 九问执行器，支持批量问题执行和脏标记管理
- `nine_question_router.py`：NineQuestionRouter 九问路由器，发布和管理九问事件
- `nine_question_state.py`：NineQuestionState 九问状态，缓存问题快照和驱动引用
- `intervention.py`：人工干预控制平面，支持暂停、角色变更等操作
- `cognitive_tools/`：认知工具注册与编排

补充说明：
- `src/zentex/core/cognitive_tools_spec.py` 是认知工具契约层
- `src/zentex/runtime/cognitive_tools/__init__.py` 是认知工具执行层
- 两者职责不同，不是重复实现

### `src/zentex/web_console`

FastAPI 控制台后端，向前端暴露完整的 API 接口。

关键文件：
- `dev_server.py`：开发态 Web Console 服务（74.6KB，最大文件）
- `app.py`：生产态应用装配
- `routers/`：API 路由器（18个）
  - `overview.py`：运行态概览
  - `events.py`：实时事件流（WebSocket）
  - `nine_questions.py`：九问数据接口（98.9KB，最大路由）
  - `cognition.py`：认知状态接口
  - `agents.py`：Agent 管理
  - `tasks.py`：任务管理
  - `plugins.py`：插件管理
  - `mcp.py`：MCP 接入
  - `cli.py`：CLI 适配器
  - `learning.py`：学习引擎
  - `upgrades.py`：升级管理
  - `memory.py`：增强记忆
  - `audit.py`：审计回放
  - `interventions.py`：人工干预
  - `replay.py`：Transcript 回放
  - `environment.py`：环境感知
  - `evolution.py`：进化监控
  - `model_feature_tests.py`：模型能力测试
- `services/`：业务服务层（11个文件）
- `contracts/`：数据契约（18个文件）
- `replay_builder.py`：Transcript 回放构建器
- `dependencies.py`：依赖注入

### `src/zentex/agents`

Agent 管理与协同模块。

关键文件：
- `manager.py`：Agent 管理器，支持注册、查询、生命周期管理
- `collaboration.py`：Agent 协同服务，支持多 Agent 协作和任务分配
- `models.py`：Agent 数据模型

### `src/zentex/tasks`

任务分解与任务服务模块。

关键文件：
- `models.py`：任务模型，定义任务结构和状态
- `decomposer.py`：任务分解器，支持复杂任务的自动分解
- `service.py`：任务服务层，提供任务 CRUD 和执行跟踪
- `registry.py`：任务注册表，管理可用任务类型

### `src/zentex/mcp`

MCP（Model Context Protocol）适配层。

关键文件：
- `client.py`：MCP 客户端实现
- `server_manager.py`：MCP 服务器管理，支持添加、删除、监控

### `src/zentex/learning`

G16 学习引擎，基于 DSPy 的学习管道。

关键文件：
- `engine.py`：G16 学习引擎主类
- `dspy_adapter.py`：DSPy 适配器，集成 DSPy 优化框架
- `budget.py`：预算管理，控制学习成本和频率
- `sandbox.py`：沙箱执行，安全地执行学习实验
- `directions.py`：学习方向管理，定义学习目标和评估标准

### `src/zentex/upgrade`

受控自我进化系统，支持插件演化和代码级自我进化。

关键文件：
- `facade.py`：升级Facade，统一的升级管理入口
- `execution.py`：执行服务，支持插件演化和代码级自我进化
- `evidence.py`：证据服务，追踪升级证据和影响分析
- `audit.py`：审计存储，记录所有升级操作的审计日志
- `plugin_evolution.py`：插件演化运行时，支持插件的动态演化和测试
- `versioning.py`：版本管理，支持升级版本控制和回滚

### `src/zentex/memory`

增强记忆系统，支持语义/程序/情景三层记忆，集成 Kuzu 图数据库后端。

关键文件：
- `service.py`：增强记忆服务，协调三层记忆的存储与检索
- `kuzu_backend.py`：Kuzu 图数据库后端，高效的图记忆存储和检索
- `consolidation.py`：记忆巩固引擎，支持记忆的整合和优化
- `management/`：记忆管理层，包含 enhanced.py 等

### `src/zentex/reflection`

元认知反思系统，支持深度反思和模式分析。

关键文件：
- `service_facade.py`：反思服务门面，管理反思记录的生成、治理、验证与模式分析
- `models.py`：反思模型，定义反思记录的数据结构
- `persistence.py`：持久化层，支持反思记录的持久化存储
- `DOCUMENTATION.md`：完整的反思系统文档

### `src/zentex/cognition`

社会心智和模拟模块，已有基础实现，持续优化中。

关键文件：
- `social_mind.py`：社会心智，支持多智能体协作认知
- `simulation.py`：反事实模拟，探索不同决策路径的结果

### `src/zentex/safety`

安全和风险控制模块，已有冲突检测和降级机制。

关键文件：
- `service.py`：安全服务，执行内容安全检查、策略 enforcement 及审计日志记录
- `policy.py`：安全策略，定义安全规则和约束

### `src/zentex/environment`

环境感知与指纹识别模块。

关键文件：
- `fingerprint.py`：环境指纹，自动生成环境特征标识
- `detector.py`：变化检测器，识别重大环境变化并触发九问刷新

### `src/zentex/core`

核心共享模型目录，用于承载运行时状态投影、统一插件基类与插件运行态契约。

关键文件：
- `models.py`：BrainRuntimeState 统一运行态投影
- `plugin_base.py`：BasePluginSpec 统一插件基类，定义插件基础契约、生命周期状态、回退与撤销约束
- `plugin_runtime.py`：插件健康、回退、撤销、加载结果等运行态契约
- `config.py`：配置管理，加载和验证系统配置

### `src/zentex/common`

common 目录，用于沉淀跨模块共享的规则依据、约束模型与基础抽象。

关键文件：
- `plugin_registry.py`：统一插件生命周期注册表与状态机海关，支持按 feature_code 和 plugin_kind 双重索引
- `event_bus.py`：事件总线，支持模块间解耦通信

### `src/zentex/llm`

LLM 网关，统一管理 LLM 调用。

关键文件：
- `gateway.py`：LLM 网关，支持多种 provider 配置
- `guard.py`：LLM 守卫，实现 fail-closed 机制，API Key 缺失时阻止相关操作

### `src/zentex/cli`

CLI 适配器，支持命令行工具调用。

关键文件：
- `adapter.py`：CLI 适配器，封装命令行工具的执行和结果解析

### `src/zentex/tools`

工具侧接口，定义工具的注册和调用规范。

关键文件：
- `registry.py`：工具注册表，管理可用工具

### `tests`

当前主测试目录，新的测试文件主要集中在这里。**90个测试文件，291+测试用例**。

当前主要测试分层：
- `tests/runtime/`：运行时子模块测试
- `tests/plugins/`：插件系统测试
- `tests/web_console/`：Web Console API 测试
- `tests/agents/`：Agent 系统测试
- `tests/learning/`：学习系统测试
- `tests/upgrade/`：升级系统测试
- `tests/memory/`：记忆系统测试
- `tests/reflection/`：反思系统测试
- `tests/cognition/`：认知模块测试
- `tests/safety/`：安全模块测试
- `tests/mcp/`：MCP 测试
- `tests/cli/`：CLI 测试
- `tests/environment/`：环境感知测试
- `tests/core/`：核心模块测试
- `tests/common/`：通用模块测试
- `tests/llm/`：LLM 测试
- `tests/tools/`：工具测试
- `test_phase1_e2e_integration.py`：Phase 1 端到端集成测试
- `test_phase3_evolution.py`：Phase 3 进化系统测试（4个测试）
- `test_phase4_memory.py`：Phase 4 记忆巩固测试（4个测试）
- `test_real_business_cases.py`：真实业务场景测试（5个测试）
- `test_think_loop.py`：ThinkLoop 测试（5个测试）
- `test_metacognition.py`：元认知测试
- `test_cognitive_state.py`：认知状态测试

### `test`

历史测试目录，当前仍保留较早创建的测试文件，建议逐步迁移到 `tests` 目录。

### `test/runtime`

历史运行时测试目录，当前保留 `test_transcript.py`。

## 当前状态结论

截至 `2026-04-09`，仓库已经形成以下结构特征：

- 项目处于**生产就绪**阶段，核心功能全部实现并经过充分测试
- 当前目录结构用于承载完整的运行时主链、九问认知链、插件体系与测试体系
- 文档集中在 `docs/operability`
- 源码集中在 `src`
- Zentex 核心能力集中在 `src/zentex`
- 运行时代码集中在 `src/zentex/runtime`
- 九问插件集中在 `src/plugins/nine_questions`（Q1-Q9 完整覆盖，69+ 文件）
- 插件基类与运行态契约集中在 `src/zentex/core`
- 通用插件注册表集中在 `src/zentex/common`
- Web Console 后端集中在 `src/zentex/web_console`（18个路由）
- Admin Portal 前端集中在 `src/admin-portal`（React + Vite）
- LLM Provider 工具集中在 `src/plugins/provider_tools.py`
- 测试目录目前仍存在 `test` 与 `tests` 并存的历史状态
- **测试规模**：90 个测试文件，291+ 个测试用例
- 配置集中在 `config/provider_tools.yml`
- 启动脚本集中在 `scripts/`

## 关键统计数据（2026-04-09）

### 代码规模
- **测试文件数**：90 个
- **测试用例数**：291+ 个
- **后端路由数**：18 个 API 路由器
- **前端页面组件**：26+ 个九问页面 + 其他管理页面
- **九问插件文件**：69+ 个文件（Q1-Q9 完整覆盖）
- **Web Console 最大文件**：dev_server.py (74.6KB)
- **最大路由文件**：nine_questions.py (98.9KB)

### 核心模块状态
| 模块 | 文件数估算 | 状态 |
|------|----------|------|
| Runtime | 13个核心文件 | ✅ 生产就绪 |
| Nine Questions Plugins | 69+ 文件 | ✅ 生产就绪 |
| Web Console Routers | 18个路由 | ✅ 生产就绪 |
| Admin Portal Pages | 26+ 九问页面 | ✅ 生产就绪 |
| Tests | 90个测试文件 | ✅ 全面覆盖 |
| Learning System | 12个文件 | ✅ 生产就绪 |
| Upgrade System | 18个文件 | ✅ 生产就绪 |
| Memory System | 11个文件 | ✅ 生产就绪 |
| Reflection System | 11个文件 | ✅ 生产就绪 |
| Agent System | 6个文件 | ✅ 生产就绪 |
| Task System | 22个文件 | ✅ 生产就绪 |
| MCP System | 6个文件 | ✅ 生产就绪 |

### 启动方式
- **一键启动**：`make dev` 或 `./scripts/dev_all.sh`
- **一键重启**：`make restart-dev` 或 `./scripts/restart_dev.sh`
- **环境初始化**：`./scripts/setup_env.sh`
- **运行测试**：`make test` 或 `./scripts/test_all.sh`
- **默认端口**：后端 8000，前端 5173
- **自定义端口**：`BACKEND_PORT=8001 FRONTEND_PORT=5174 make dev`

### 配置管理
- **环境变量**：`.env`（从 `.env.example` 复制）
- **LLM Provider**：`config/provider_tools.yml`
- **支持 Provider**：openai_compat, openai, gemini, claude

## 后续建议

- [ ] 将历史 `test/runtime/test_transcript.py` 逐步迁移到 `tests/runtime`
- [ ] 统一测试目录规范，避免长期双目录并存
- [ ] 每次新增核心目录或测试目录后，同步更新本文件，保证目录文档始终是最新版本
- [x] 为各主要模块补充独立的 README.md（已完成）
- [x] 创建项目根目录 README.md（已完成）
- [x] 更新启动和测试文档（已完成）
