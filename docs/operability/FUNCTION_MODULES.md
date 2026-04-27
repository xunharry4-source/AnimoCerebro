# Function Modules Documentation | 功能模块文档

## English Version

This document explains the responsibilities and technical architecture of the functional modules in the `src` directory, facilitating unified boundaries for future development, collaboration, and deployment.

For plugin development guidelines organized by function, see:
- [PLUGIN_GUIDES.md](PLUGIN_GUIDES.md)

### One-Click Development Commands (Most Commonly Used)

This repository provides front-end and back-end "one-click start / one-click restart" entry points to ensure that Web pages bind to real backend services (not mock).

- One-click start: `make dev` (equivalent to `./scripts/dev_all.sh`, default uses `websockets-sansio`)
- One-click restart: `make restart-dev` (equivalent to `./scripts/restart_dev.sh`, will first clean up port occupancy before pulling up)

For more complete startup, port override, and testing instructions, see:
- [STARTUP_AND_TEST.md](STARTUP_AND_TEST.md)

---

## 中文版本

本文档说明 `src` 目录中功能模块的职责和技术架构，为未来的开发、协作和部署提供统一的边界。

按功能组织的插件开发指南，请参阅：
- [PLUGIN_GUIDES.md](PLUGIN_GUIDES.md)

### 一键开发命令（最常用）

本仓库提供前后端"一键启动/一键重启"入口，确保 Web 页面绑定到真实的后端服务（而非 mock）。

- 一键启动：`make dev`（等同于 `./scripts/dev_all.sh`，默认使用 `websockets-sansio`）
- 一键重启：`make restart-dev`（等同于 `./scripts/restart_dev.sh`，会先清理端口占用再拉起）

更完整的启动、端口覆盖和测试说明，请参阅：
- [STARTUP_AND_TEST.md](STARTUP_AND_TEST.md)

## Directory List | 目录列表

### English Version

### `src/plugins`

Tool capability directory, used to carry third-party model and external capability call method encapsulation.

**Scope of application**:
- Third-party model call encapsulation
- External platform HTTP call methods
- Unified request body and response body standardization
- Provide tool methods that can be directly accessed by the runtime

**Suggested content**:
- Tool call entry point
- Provider configuration model
- Request body and response body encapsulation
- External call method description

**Current key files**:
- `src/plugins/provider_tools.py`
  Responsible for encapsulating OpenAI, ChatGPT, Gemini, and Claude call methods.

**Plugin development guidelines**:
- First check the function-organized general index `docs/operability/PLUGIN_GUIDES.md`
- Then enter the corresponding plugin directory to view the family-level `DEVELOPMENT_GUIDE.md`
- `src/plugins/model_providers/DEVELOPMENT_GUIDE.md`
- `src/plugins/cognitive/DEVELOPMENT_GUIDE.md`
- `src/plugins/execution/DEVELOPMENT_GUIDE.md`
- `src/plugins/sensory/DEVELOPMENT_GUIDE.md`
- `src/plugins/simulation/DEVELOPMENT_GUIDE.md`
- `src/plugins/weights/DEVELOPMENT_GUIDE.md`

---

### 中文版本

### `src/plugins`

工具能力目录，用于承载第三方模型和外部能力调用方法的封装。

**适用范围**：
- 第三方模型调用封装
- 外部平台 HTTP 调用方法
- 统一的请求体和响应体标准化
- 提供运行时可直接访问的工具方法

**建议内容**：
- 工具调用入口
- Provider 配置模型
- 请求体和响应体封装
- 外部调用方法说明

**当前关键文件**：
- `src/plugins/provider_tools.py`
  负责封装 OpenAI、ChatGPT、Gemini 和 Claude 的调用方法。

**插件开发指南**：
- 首先查看按功能组织的总索引 `docs/operability/PLUGIN_GUIDES.md`
- 然后进入对应的插件目录查看家族级的 `DEVELOPMENT_GUIDE.md`
- `src/plugins/model_providers/DEVELOPMENT_GUIDE.md`
- `src/plugins/cognitive/DEVELOPMENT_GUIDE.md`
- `src/plugins/execution/DEVELOPMENT_GUIDE.md`
- `src/plugins/sensory/DEVELOPMENT_GUIDE.md`
- `src/plugins/simulation/DEVELOPMENT_GUIDE.md`
- `src/plugins/weights/DEVELOPMENT_GUIDE.md`

### `src/admin-portal`

#### English Version

Web management portal directory, providing visual operation interface for Zentex system.

**Main functions**:
- System status monitoring
- Agent management
- Task tracking
- Plugin management
- MCP management
- Real-time event streaming display

**Technology stack**:
- React + Vite + TypeScript
- WebSocket real-time communication
- RESTful API interaction

---

#### 中文版本

Web 管理门户目录，为 Zentex 系统提供可视化操作界面。

**主要功能**：
- 系统状态监控
- Agent 管理
- 任务跟踪
- 插件管理
- MCP 管理
- 实时事件流显示

**技术栈**：
- React + Vite + TypeScript
- WebSocket 实时通信
- RESTful API 交互

### `src/zentex`

#### English Version

Core business logic directory, containing all core modules of Zentex system.

**Core Modules**:

1. **Cognition Module** (`src/zentex/cognition/`)
   - Nine Questions cognitive loop implementation
   - Decision reasoning engine
   - Goal generation and planning

2. **Memory Module** (`src/zentex/memory/`)
   - Memory storage and retrieval
   - Experience accumulation
   - Knowledge consolidation

3. **Safety Module** (`src/zentex/safety/`)
   - Safety gate mechanisms
   - Risk assessment
   - Conflict detection and resolution

4. **Tasks Module** (`src/zentex/tasks/`)
   - Task decomposition engine
   - Task execution management
   - Verification and validation

5. **Upgrade Module** (`src/zentex/upgrade/`)
   - System upgrade framework
   - AI-driven executors
   - Skills-based debugging and reviewing

6. **Environment Module** (`src/zentex/environment/`)
   - Environmental awareness
   - Sensory processing
   - Context interpretation

7. **Web Console** (`src/zentex/web_console/`)
   - API endpoints
   - WebSocket services
   - Real-time monitoring

8. **Plugins Module** (`src/zentex/plugins/`)
   - Plugin registry
   - Plugin lifecycle management
   - Hot-reload support

9. **Agents Module** (`src/zentex/agents/`)
   - Agent management
   - Agent coordination
   - Communication protocols

10. **Learning Module** (`src/zentex/learning/`)
    - Learning mechanisms
    - Experience exchange
    - Knowledge evolution

11. **Supervision Module** (`src/zentex/supervision/`)
    - AI supervisor integration
    - Oversight mechanisms
    - Audit trails

12. **Reflection Module** (`src/zentex/reflection/`)
    - Self-reflection capabilities
    - Performance analysis
    - Improvement suggestions

---

#### 中文版本

核心业务逻辑目录，包含 Zentex 系统的所有核心模块。

**核心模块**：

1. **认知模块** (`src/zentex/cognition/`)
   - 九问认知循环实现
   - 决策推理引擎
   - 目标生成和规划

2. **记忆模块** (`src/zentex/memory/`)
   - 记忆存储和检索
   - 经验积累
   - 知识巩固

3. **安全模块** (`src/zentex/safety/`)
   - 安全门机制
   - 风险评估
   - 冲突检测和解决

4. **任务模块** (`src/zentex/tasks/`)
   - 任务分解引擎
   - 任务执行管理
   - 验证和确认

5. **升级模块** (`src/zentex/upgrade/`)
   - 系统升级框架
   - AI 驱动的执行器
   - 基于技能的调试和审查

6. **环境模块** (`src/zentex/environment/`)
   - 环境感知
   - 感官处理
   - 上下文解释

7. **Web 控制台** (`src/zentex/web_console/`)
   - API 端点
   - WebSocket 服务
   - 实时监控

8. **插件模块** (`src/zentex/plugins/`)
   - 插件注册表
   - 插件生命周期管理
   - 热重载支持

9. **Agent 模块** (`src/zentex/agents/`)
   - Agent 管理
   - Agent 协调
   - 通信协议

10. **学习模块** (`src/zentex/learning/`)
    - 学习机制
    - 经验交换
    - 知识进化

11. **监督模块** (`src/zentex/supervision/`)
    - AI 监督器集成
    - 监督机制
    - 审计追踪

12. **反思模块** (`src/zentex/reflection/`)
    - 自我反思能力
    - 性能分析
    - 改进建议

## Architecture Overview | 架构概览

### English Version

Zentex follows a layered architecture design:

1. **Perception Layer**: Environmental sensing and data ingestion
2. **Cognitive Layer**: Nine Questions reasoning and decision-making
3. **Orchestration Layer**: Task planning and coordination
4. **Execution Layer**: Action execution and result collection
5. **Reflection Layer**: Self-evaluation and improvement

---

### 中文版本

Zentex 采用分层架构设计：

1. **感知层**：环境感知和数据摄入
2. **认知层**：九问推理和决策
3. **编排层**：任务规划和协调
4. **执行层**：行动执行和结果收集
5. **反思层**：自我评估和改进

## Key Design Principles | 关键设计原则

### English Version

1. **Modularity**: Each module has clear boundaries and responsibilities
2. **Plugin-Based**: Extensible through plugin architecture
3. **Autonomy**: Enables AI autonomous decision-making
4. **Safety**: Built-in safety mechanisms and risk control
5. **Observability**: Comprehensive logging and monitoring
6. **Evolution**: Self-upgrading and learning capabilities

---

### 中文版本

1. **模块化**：每个模块有清晰的边界和职责
2. **插件化**：通过插件架构可扩展
3. **自主性**：支持 AI 自主决策
4. **安全性**：内置安全机制和风险控制
5. **可观察性**：全面的日志记录和监控
6. **进化性**：自我升级和学习能力

## Integration Points | 集成点

### English Version

- External agents connect through standardized protocols
- Plugins extend functionality without modifying core code
- Web console provides real-time monitoring and control
- API endpoints enable programmatic access

---

### 中文版本

- 外部 Agent 通过标准化协议连接
- 插件在不修改核心代码的情况下扩展功能
- Web 控制台提供实时监控和控制
- API 端点支持编程访问

## Testing Strategy | 测试策略

### English Version

- Unit tests for individual components
- Integration tests for module interactions
- E2E tests for complete workflows
- Performance tests for critical paths

---

### 中文版本

- 针对单个组件的单元测试
- 针对模块交互的集成测试
- 针对完整工作流的端到端测试
- 针对关键路径的性能测试

## Deployment Considerations | 部署考虑

### English Version

- Support for local, distributed, and cloud deployments
- Configuration-driven behavior customization
- Health check and monitoring endpoints
- Graceful shutdown and restart mechanisms

---

### 中文版本

- 支持本地、分布式和云部署
- 配置驱动的行为定制
- 健康检查和监控端点
- 优雅关闭和重启机制
