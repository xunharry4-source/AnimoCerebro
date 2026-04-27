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
│       │   └── adapter.py          # MCP 适配器
│       ├── cognition/              # 认知模块（社会心智、反事实模拟）
│       ├── learning/               # 学习系统（G16 DSPy集成）（12个文件）
│       ├── upgrade/                # 升级系统（受控自我进化）（18个文件）
│       ├── memory/                 # 记忆系统（Kuzu图数据库）（11个文件）
│       ├── reflection/             # 反思系统（元认知反思）（11个文件）
│       ├── safety/                 # 安全模块（风险检测、冲突解决）
│       ├── environment/            # 环境感知（环境指纹、变化检测）
│       ├── supervision/            # 监督模块（AI监督器集成）
│       └── common/                 # 通用模块（插件注册表等）
├── tests/                          # 测试套件（90个测试文件）
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
│   └── core/                       # 核心模块测试
├── Agent/                          # LangGraph + CrewAI Agent 系统
│   ├── browser_automation/         # 浏览器自动化
│   ├── core_agents/                # 核心Agent实现
│   ├── posting_workflows/          # 发布工作流
│   ├── social_promotion/           # 社交媒体推广
│   ├── docs/                       # Agent 文档
│   └── tests/                      # Agent 测试
├── chrome_custom_profile/          # Chrome 自定义配置文件
├── chrome_social_profile/          # Chrome 社交配置文件
├── browser_sessions/               # 浏览器会话存储
├── screenshots/                    # 截图文件
├── playwright_tmp/                 # Playwright 临时文件
├── tmp/                            # 临时文件
├── .env                            # 环境变量配置
├── .env.example                    # 环境变量示例
├── requirements.txt                # Python 依赖
├── requirements-dev.txt            # 开发依赖
├── Makefile                        # Make 命令
├── pytest.ini                      # Pytest 配置
└── README.md                       # 项目主文档
```

## 核心目录说明

### 1. `src/zentex/` - 核心后端

Zentex 是 AnimoCerebro 的核心后端系统，实现了完整的九问认知循环。

**主要子模块**：

#### Runtime（运行时）
- **BrainRuntime**: 运行时大管家，协调整个认知流程
- **ThinkLoop**: 九阶段认知执行器，执行 Q1-Q9
- **BrainSession**: 会话容器，维护会话连续性
- **Transcript**: 事件流存储，记录所有认知事件
- **WorkingMemory**: 工作记忆控制器
- **Metacognition**: 元认知控制器
- **Self Model**: 活的自我模型引擎
- **Temporal**: 时间议程引擎
- **Conflict**: 冲突检测引擎

#### Web Console（Web 控制台）
- **dev_server.py**: 开发态服务器（74.6KB，最大文件）
- **18个 API 路由器**: 完整的 RESTful API
- **WebSocket 实时事件流**: 实时监控
- **服务层**: 业务逻辑封装

#### Agents（Agent 管理）
- **Manager**: Agent 生命周期管理
- **Collaboration**: Agent 协同服务
- **Models**: Agent 数据模型

#### Tasks（任务系统）
- **Decomposer**: 任务分解引擎
- **Service**: 任务管理服务
- **Models**: 任务数据模型

#### Learning（学习系统）
- **G16 Engine**: DSPy 集成的学习引擎
- **Budget Management**: 预算管理
- **Sandbox**: 沙箱执行

#### Upgrade（升级系统）
- **Controlled Evolution**: 受控自我进化
- **Plugin Evolution**: 插件演化运行时
- **Evidence Tracking**: 证据追踪

#### Memory（记忆系统）
- **Kuzu Backend**: Kuzu 图数据库后端
- **Enhanced Service**: 增强记忆服务
- **Consolidation**: 记忆巩固引擎

#### Reflection（反思系统）
- **Metacognitive Reflection**: 元认知反思
- **Pattern Analysis**: 模式分析
- **Improvement Suggestions**: 改进建议

### 2. `src/plugins/` - 插件系统

双插件系统架构，支持外部插件和内部插件。

#### Nine Questions（九问插件家族）
完整的 Q1-Q9 插件实现，共 69+ 文件：

- **Q1 Where Am I**: 环境感知（11个文件）
- **Q2 Who Am I**: 角色假设（8个文件）
- **Q3 What Do I Have**: 资源盘点（8个文件）
- **Q4 What Can I Do**: 能力边界（5个文件）
- **Q5 Allowed**: 约束检查（5个文件）
- **Q6 Consequences**: 风险评估（9个文件）
- **Q7 Alternatives**: 替代方案（6个文件）
- **Q8 Priority**: 优先级决策（6个文件）
- **Q9 Action**: 行动确认（7个文件）

#### 其他插件家族
- **Model Providers**: Gemini, OpenAI, Claude 适配器
- **Cognitive Tools**: 认知工具插件
- **Execution**: CLI, MCP 执行插件
- **Sensory**: 感知插件
- **Simulation**: 模拟插件
- **Memory**: 记忆插件
- **Weights**: 权重插件
- **Reflection**: 反思插件

### 3. `src/admin-portal/` - 前端管理界面

React + Vite + TypeScript 实现的完整管理前端。

**主要页面**：
- **Dashboard**: 实时指挥台（6个文件）
- **Nine Questions**: 九问页面（26个文件）
- **Agents**: Agent 管理（4个文件）
- **Tasks**: 任务管理（2个文件）
- **Plugins**: 插件管理
- **MCP**: MCP 管理（2个文件）
- **Audit**: 审计回放（2个文件）
- **Learning**: 学习管理
- **Upgrades**: 升级管理（3个文件）
- **CLI**: CLI 适配器（2个文件）

**技术栈**：
- React 18
- Vite
- TypeScript
- WebSocket 实时通信
- i18n 国际化（中英文）

### 4. `tests/` - 测试套件

全面的测试覆盖，90个测试文件，291+测试用例。

**测试分类**：
- **Runtime Tests**: 运行时测试
- **Plugin Tests**: 插件测试
- **Web Console Tests**: Web Console 测试
- **Agent Tests**: Agent 测试
- **Learning Tests**: 学习系统测试
- **Upgrade Tests**: 升级系统测试
- **Memory Tests**: 记忆系统测试
- **Reflection Tests**: 反思系统测试
- **Cognition Tests**: 认知模块测试
- **Safety Tests**: 安全模块测试
- **MCP Tests**: MCP 测试
- **CLI Tests**: CLI 测试
- **Environment Tests**: 环境感知测试
- **Core Tests**: 核心模块测试

**覆盖率**: >80%

### 5. `Agent/` - LangGraph + CrewAI Agent 系统

基于 LangGraph 和 CrewAI 的智能 Agent 系统。

**主要模块**：
- **Browser Automation**: 浏览器自动化
- **Core Agents**: 核心 Agent 实现
- **Posting Workflows**: 发布工作流
- **Social Promotion**: 社交媒体推广

**功能特性**：
- X.com 自动发帖
- Reddit 智能发帖
- GitHub Discussion 创建
- 社区规则管理

### 6. `scripts/` - 启动和管理脚本

便捷的开发和运维脚本。

**常用脚本**：
- **dev_all.sh**: 一键启动所有服务
- **restart_dev.sh**: 重启开发环境
- **setup_env.sh**: 环境初始化
- **test_all.sh**: 运行所有测试

## 项目统计

### 代码规模
| 指标 | 数量 |
|------|------|
| 测试文件 | 90 个 |
| 测试用例 | 291+ 个 |
| 后端路由 | 18 个 |
| 前端页面 | 26+ 九问页面 |
| 九问插件 | 69+ 文件 |
| 最大文件 | dev_server.py (74.6KB) |
| 最大路由 | nine_questions.py (98.9KB) |

### 核心模块状态
| 模块 | 文件数 | 状态 |
|------|--------|------|
| Runtime | 13 | ✅ 生产就绪 |
| Nine Questions | 69+ | ✅ 生产就绪 |
| Web Console | 18路由 | ✅ 生产就绪 |
| Admin Portal | 26+页面 | ✅ 生产就绪 |
| Tests | 90文件 | ✅ 全面覆盖 |
| Learning | 12 | ✅ 生产就绪 |
| Upgrade | 18 | ✅ 生产就绪 |
| Memory | 11 | ✅ 生产就绪 |
| Reflection | 11 | ✅ 生产就绪 |
| Agent | 6 | ✅ 生产就绪 |
| Task | 22 | ✅ 生产就绪 |
| MCP | 6 | ✅ 生产就绪 |

## 快速开始

### 安装依赖
```bash
make install
```

### 启动开发环境
```bash
make dev
```

### 运行测试
```bash
make test
```

### 重启开发环境
```bash
make restart-dev
```

## 相关文档

- [启动与测试说明](STARTUP_AND_TEST.md)
- [功能模块总览](FUNCTION_MODULES.md)
- [Agent & MCP 管理](AGENT_AND_MCP.md)
- [ThinkLoop 深度解析](THINK_LOOP_DEEP_DIVE.md)
- [运行时与测试](RUNTIME_AND_TESTS.md)
- [插件开发指南](PLUGIN_GUIDES.md)

---

**最后更新**: 2026-04-27  
**维护者**: AnimoCerebro Team  
**许可证**: GNU GPL v3
