# AnimoCerebro

![AnimoCerebro Logo](docs/logo.jpeg)

> **⚠️ 项目状态**：本项目目前处于**功能测试和积极开发阶段**。核心功能已实现，但仍在测试和完善中。API 和配置可能会发生变化。在生产环境中使用请谨慎。

[English README](README.md) | 中文详细版

## 概览

AnimoCerebro 是 Agent 与宿主系统的**大脑**，提供 Agent, openCLaw 等所有 AI 的**外挂大脑**。它赋予 AI **自主、反思、学习和自我升级**的能力，能够根据“九问”认知循环的结果**自主做事**。

AnimoCerebro 负责思考、角色推演、目标生成、风险判断、记忆沉淀、委托建议和长期经验交换。它不仅是辅助组件，更是 AI 实现高级认知与独立行动的核心。

## 它是什么

AnimoCerebro 围绕**九问认知循环**工作，并基于此实现 AI 自主决策：

1. 我在哪
2. 我是谁
3. 我有什么
4. 我能干什么
5. 我可以干什么
6. 我还能干什么
7. 我不应该也能干什么
8. 我应该干什么
9. 我应该怎么做

**AI 能够根据这九问的结果，在明确目标与边界后，自主驱动后续任务。**

## 产品定位

AnimoCerebro 是：

- **AI 的核心大脑**：为 Agent 提供思考、学习、反思与自我进化的能力。
- **万能外挂大脑**：可挂接到 OpenClaw、各类 Agent 框架或现有宿主系统上。
- **自主行为引擎**：基于认知分析实现 AI 的自主决策与行动。
- **长期经验沉淀层**：让 AI 具备跨任务、跨时间的持续学习能力。

不应该把它理解为：

- 强制接管用户回复的主引擎
- 硬接管层
- 逼迫你重写现有宿主架构的理由

## 当前协议

当前公开协议是分层协议，包含：

- 节点注册
- 能力发现
- 委托
- 回执
- 升级
- 经验交换
- 宿主适配

主协议文档：

- [协议设计](docs/zmsp_protocol_design.md)
- [功能模块总览](docs/operability/FUNCTION_MODULES.md)
- [启动指南](docs/启动指南.md)
- [配置指南](docs/配置指南.md)

## 文档入口

- [项目进度报告](docs/项目进度报告.md)（技术白皮书与架构设计）
- [快速开始与启动](docs/operability/STARTUP_AND_TEST.md)（一键启动方法）
- [运行时与测试说明](docs/operability/RUNTIME_AND_TESTS.md)（详细架构与测试覆盖）
- [功能模块说明](docs/operability/FUNCTION_MODULES.md)（功能拆解与技术架构）
- [最新目录映射](docs/operability/LATEST_DIRECTORY_MAP.md)（当前项目结构）
- [插件开发指南](docs/operability/PLUGIN_GUIDES.md)（插件开发规范）
- [Agent 接入说明](Agent/README.md)（外部 Agent 标准接口）
- [Agent 接入指南](Agent/INTEGRATION_GUIDE.md)（如何对接您的系统）

## 接入模型

AnimoCerebro 的设计目标是最小侵入：

- 宿主继续保留自己的执行架构
- AnimoCerebro 提供思考、记忆、协同和审计
- 适配层只负责注册宿主、同步能力、接收委托任务、回写结果

## 技术规范

### 模块独立性原则

AnimoCerebro 的所有模块遵循严格的独立性原则：

1. **模块自治**：每个模块独立运行，边界清晰
2. **插件化升级**：模块功能可通过插件扩展和升级，无需修改核心代码
3. **代码隔离**：插件之间必须保持独立，禁止跨插件依赖

### 插件架构

AnimoCerebro 实现双插件系统：

#### 外部插件（`plugins/`）

**用途**：将外部功能作为组件连接到主脑，扩展大脑能力

**核心特征**：
- 作为外部系统与主脑之间的桥梁
- 使大脑能够从外部源获得额外能力
- **严格规则**：外部插件**禁止**导入或调用 `src/` 目录下的任何代码
- 必须仅通过定义的 API 和协议与主脑交互
- 专为第三方集成和自定义扩展设计

**典型应用场景**：
- 自定义数据源连接器
- 第三方服务集成
- 专用工具适配器

#### 内部插件（`src/plugins/`）

**用途**：支持内部自我迭代和系统升级

**核心特征**：
- 核心系统自我进化机制的组成部分
- 可以访问并与 `src/zentex/` 核心模块交互
- 支持热重载和动态升级
- 实现核心认知功能（如 Q1-Q9 九问）
- 由内部插件注册系统管理

**典型应用场景**：
- 九问认知循环实现
- 模型提供商适配器（Gemini, OpenAI, Claude）
- 认知工具、感知处理、模拟引擎
- 内部系统增强和优化

### 插件开发规则

1. **独立性**：每个插件必须自包含，不依赖其他插件
2. **清晰接口**：插件仅通过明确定义的 API 进行通信
3. **升级安全**：插件升级不得破坏现有功能
4. **隔离边界**：外部插件（`plugins/`）不能从 `src/` 导入；内部插件（`src/plugins/`）可以访问核心模块

## 当前能力

- 九问主脑循环（Q1-Q9 完整实现）
- 常驻与 daemon 模式
- Web 控制台与实时指挥台
- SQLite 持久化存储
- 插件系统支持热重载
- 委托、回执、升级、经验交换
- OpenClaw 及自定义宿主适配路径

## 真实性边界

凡是产品链路声称“使用了 LLM”，AnimoCerebro 都不允许用规则逻辑、模板拼装、固定样本、fake transport、stub completion 或任何“只是看起来像调用了 LLM”的代码替代真实 live LLM 调用。

如果某项功能要求 live LLM，就必须真的发生 live 调用。密钥缺失、网络失败、provider 异常或返回不合法时，系统必须真实失败或真实降级，并在适用处明确标注为非 live、非真实结果，不能继续冒充 AI 推理成功。

同样的标准也适用于测试：任何不执行被测真实项目逻辑的测试，都是无效且禁止的。mock 或 stub 可以隔离外部不稳定依赖，但不能替代产品自身核心逻辑后还被当成功能正确证据。

## 📦 安装指南

### 环境准备

在开始安装之前，请确保您的环境满足以下要求：
- **Python**: 3.10 或更高版本
- **Node.js**: 18+ LTS 版本（用于 Web 控制台）
- **npm**: 9+
- **API 密钥**: 您需要从 Google (Gemini)、OpenAI 或 Anthropic (Claude) 等提供商处获取 API 密钥，以启用完整的认知能力。

### 一键安装

一次性安装后端与前端的所有依赖：

```bash
make install
```

*注：该命令实际运行的是 `./scripts/setup_env.sh`。*

### 手动安装

如果你更喜欢手动分步骤安装：

```bash
# 后端
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# 前端
cd src/admin-portal && npm install
```

## 🚀 快速启动

### 一键启动

同时启动后端服务（Uvicorn）与前端控制台（Vite）：

```bash
make dev
```

*注：该命令实际运行的是 `./scripts/dev_all.sh`。*

访问地址：
- 前端：http://127.0.0.1:5173
- 后端：http://127.0.0.1:8000
- API 文档：http://127.0.0.1:8000/docs

### 重启开发环境

如果端口被占用或进程卡住：

```bash
make restart-dev
```

这将清理旧进程并干净地重启所有服务。

### 手动启动

单独启动各组件：

```bash
# 使用脚本启动全部（由 make dev 封装）
./scripts/dev_all.sh

# 仅启动后端
export PYTHONPATH=src
python -m uvicorn zentex.web_console.dev_server:app --reload --ws websockets-sansio --host 127.0.0.1 --port 8000

# 仅启动前端（带热更新）
cd src/admin-portal && npm run dev
```

## ⚙️ 配置说明

系统通过 YAML 文件进行配置，主要的配置目录为 `config/`。

- **模型提供商 (Model Providers)**: `config/provider_tools.yml` 定义了各个 LLM 提供商的 API 基地址、模型名称以及环境变量密钥。
- **系统设置**: 可以通过本地运行态状态和环境变量进一步微调主脑的行为。

`config/provider_tools.yml` 示例配置：
```yaml
gemini:
  provider_name: gemini
  api_base: https://generativelanguage.googleapis.com/v1beta
  api_key_env: GEMINI_API_KEY
  default_model: gemini-1.5-pro
  timeout_seconds: 30
```

## LLM Provider 配置

系统通过 `config/provider_tools.yml` 支持以下 LLM 提供商：

- `openai_compat`: OpenAI 兼容端点（默认：localhost:8317/v1）
- `openai`: OpenAI API (api.openai.com/v1)
- `chatgpt`: 备用 OpenAI 端点
- `gemini`: Google Gemini API (generativelanguage.googleapis.com)
- `claude`: Anthropic Claude API (api.anthropic.com/v1)

通过环境变量配置 API 密钥：

```bash
export GEMINI_API_KEY=your-key-here
export OPENAI_API_KEY=sk-your-key
export ANTHROPIC_API_KEY=your-key-here
```

或者在 `config/provider_tools.yml` 中修改 `api_key_env` 字段。

## 测试

运行所有测试：

```bash
make test
```

这将执行：
- **Python 测试**：90个测试文件，291+测试用例
- **前端测试**：React 组件测试

运行特定测试套件：

```bash
# 仅后端测试
make backend-test

# 仅前端测试
make frontend-test

# WebSocket 集成测试
pytest tests/web_console/test_events_stream_integration.py -m integration
```

## 仓库结构

- **`src/zentex/`**: 核心后端源码与服务
  - 包含认知、记忆、安全、运行时、任务、升级等模块
  - Web 控制台 API 实现
  - 这是项目的主要源代码目录
  
- **`src/plugins/`**: 内部插件系统（可升级）
  - Q1-Q9 九问插件完整实现
  - 模型提供商（Gemini, OpenAI, Anthropic 适配器）
  - 认知、感知、模拟、执行等功能插件
  - 插件可独立开发和升级
  
- **`src/admin-portal/`**: Web 管理前端
  - React + Vite + TypeScript
  - 实时指挥台、Agent 管理、任务跟踪
  - 插件和 MCP 管理界面
  
- **`scripts/`**: 启动和管理脚本集合
  - `dev_all.sh`: 一键启动所有服务
  - `restart_dev.sh`: 清理并重启开发环境
  - `setup_env.sh`: 环境初始化
  - `test_all.sh`: 运行所有测试
  - 各种迁移和工具脚本
  
- **`Agent/`**: 独立的外部测试 Agent 与集成示例
  - 标准协议实现
  - 外部系统集成指南
  
- **`tests/`**: 自动化端到端测试与单元测试
  - 90个测试文件覆盖所有主要模块
  - WebSocket、运行时、插件、Agent 测试
  
- **`docs/`**: 完整的技术文档
  - 操作指南、启动说明
  - 架构详情、插件开发指南
  - 项目进度报告
  
- **`config/`**: 中央系统配置文件
  - Provider 工具配置
  - 系统设置

## 下一步阅读

- [启动指南](docs/启动指南.md) - 详细的启动说明
- [快速开始与测试](docs/operability/STARTUP_AND_TEST.md) - 一键命令
- [功能实现概览](docs/operability/FUNCTION_MODULES.md) - 功能总览
- [最新目录映射](docs/operability/LATEST_DIRECTORY_MAP.md) - 当前项目结构
- [项目总结](docs/operability/项目总结_当前实现概览.md) - 实现概览
- 更多文档见 `docs/` 目录。

## 联系我们

**希望大家一起创建一个有灵魂的大脑！**

- 欢迎通过 [GitHub Issues](https://github.com/xunharry4-source/AnimoCerebro/issues) 或 [GitHub Discussions](https://github.com/xunharry4-source/AnimoCerebro/discussions) 参与讨论。
- 如果你有任何想法或建议，请随时提交 Pull Request 或发起 Issue。

## 开源协议

本项目采用 [GNU GPL v3](LICENSE) 开源协议。

