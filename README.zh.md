# AnimoCerebro

![AnimoCerebro Logo](docs/logo.jpeg)

[English + 中文](README.md) | 中文详细版

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

当前公开协议已经不再是单一 `Z-JSON` 包，而是分层协议：

- 节点注册
- 能力发现
- 委托
- 回执
- 升级
- 经验交换
- 宿主适配

主协议文档：

- [当前对接协议.md](当前对接协议.md)
- [CORE_FOUNDATIONS.md](docs/architecture/CORE_FOUNDATIONS.md)
- [帮助文档.md](帮助文档.md)
- [详细部署与集成说明.md](详细部署与集成说明.md)

## 文档入口

- [技术白皮书](WHITEPAPER.md)（设计理念）
- [快速开始与启动](docs/operability/STARTUP_AND_TEST.md)（一键启动方法）
- [运行时与测试说明](docs/operability/RUNTIME_AND_TESTS.md)（详细架构与测试覆盖）
- [功能模块说明](docs/operability/FUNCTION_MODULES.md)（功能拆解与技术架构）
- [核心架构说明](docs/architecture/CORE_FOUNDATIONS.md)（认知循环与分层）
- [GitHub 公开范围](docs/operability/GITHUB_PUBLIC_SCOPE.md)（提交规则）
- [Agent 接入说明](Agent/README.md)（外部 Agent 标准接口）
- [Agent 接入指南](Agent/INTEGRATION_GUIDE.md)（如何对接您的系统）

## 接入模型

AnimoCerebro 的设计目标是最小侵入：

- 宿主继续保留自己的执行架构
- AnimoCerebro 提供思考、记忆、协同和审计
- 适配层只负责注册宿主、同步能力、接收委托任务、回写结果

## 当前能力

- 主脑循环
- 常驻与 daemon 模式
- 本地云审计服务
- Web 控制台
- JSONL 或 SQLite 长期记忆
- 委托、回执、升级、经验交换
- OpenClaw 宿主适配路径

## 真实性边界

凡是产品链路声称“使用了 LLM”，AnimoCerebro 都不允许用规则逻辑、模板拼装、固定样本、fake transport、stub completion 或任何“只是看起来像调用了 LLM”的代码替代真实 live LLM 调用。

如果某项功能要求 live LLM，就必须真的发生 live 调用。密钥缺失、网络失败、provider 异常或返回不合法时，系统必须真实失败或真实降级，并在适用处明确标注为非 live、非真实结果，不能继续冒充 AI 推理成功。

同样的标准也适用于测试：任何不执行被测真实项目逻辑的测试，都是无效且禁止的。mock 或 stub 可以隔离外部不稳定依赖，但不能替代产品自身核心逻辑后还被当成功能正确证据。

## 📦 安装指南

### 环境准备

在开始安装之前，请确保您的环境满足以下要求：
- **Python**: 3.11 或更高版本
- **Node.js**: LTS 版本（用于 Web 控制台）
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
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]

# 前端
cd src/admin-portal && npm install
```

## 🚀 快速启动

### 一键启动

同时启动后端服务（Uvicorn）与前端控制台（Vite）：

```bash
make start
```

*注：该命令实际运行的是 `./scripts/dev_all.sh`。*

### 手动启动

单独启动各组件：

```bash
# 使用脚本启动全部（由 make start 封装）
./scripts/dev_all.sh

# 仅启动后端
animocerebro

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
```

## LLM Provider 配置

`animocerebro_vision.yaml` 现在支持以下 `llm.provider`：

- `google`：Gemini，默认环境变量 `GOOGLE_API_KEYS`
- `openai` 或 `openapi`：OpenAI 兼容 chat completions，默认环境变量 `OPENAI_API_KEY`
- `anthropic` 或 `claude`：Claude Messages API，默认环境变量 `ANTHROPIC_API_KEY`

现在可以用三种更正常的方式配置 key：

1. 直接写在配置文件里
2. 写到本地 `credentials_file`
3. 继续用环境变量，作为兼容路径

示例：

```yaml
llm:
  provider: gemini
  model: gemini-3.1-flash-lite-preview
  api_keys:
    - your-key-here
```

或者：

```yaml
llm:
  provider: gemini
  model: gemini-3.1-flash-lite-preview
  credentials_file: .animocerebro/llm_keys.json
```

其中 `.animocerebro/llm_keys.json` 可以写成：

```json
{"api_keys": ["your-key-here"]}
```

或者：

```json
{"api_key": "your-key-here"}
```

零参数启动：

```bash
animocerebro
```

运行一次主脑：

```bash
animocerebro run --state-dir .animocerebro/state --config animocerebro_vision.yaml --pretty
```

常驻模式：

```bash
animocerebro run --state-dir .animocerebro/state --config animocerebro_vision.yaml --resident --interval 60
```

启动 Web 控制台：

```bash
animocerebro web start --state-dir .animocerebro/state --config animocerebro_vision.yaml --host 127.0.0.1 --port 8899
```

## 接入模型

AnimoCerebro 的设计目标是最小侵入：
- **执行权保留在宿主**：您的系统继续保持完全控制。
- **大脑作为顾问**：AnimoCerebro 提供推理、委托建议和记忆支持。
- **标准协议对接**：使用 `Agent/` 提供的标准 REST/WebSocket 接口进行接入。

详见：[Agent 接入指南](Agent/INTEGRATION_GUIDE.md)。

## OpenClaw 接入

OpenClaw 是主要的宿主适配器历史实例。虽然 `integrations/` 目录已整合到标准化的 `Agent/` 中，但协议保持兼容。

详见：
- [OPENCLAW_INTEGRATION_GUIDE.md](docs/integrations/OPENCLAW_INTEGRATION_GUIDE.md)
- [OPENCLAW_HOST_ADAPTER_PROTOCOL.md](docs/integrations/OPENCLAW_HOST_ADAPTER_PROTOCOL.md)
- [OPENCLAW_HOST_ADAPTER_ARCHITECTURE.md](docs/integrations/OPENCLAW_HOST_ADAPTER_ARCHITECTURE.md)

## 仓库结构

- `src/zentex`: 核心后端与服务（包括认知、记忆、安全等模块）
- `src/plugins`: 功能插件实现（模型提供商、感知、模拟等）
- `src/admin-portal`: Web 后台管理前端
- `Agent/`: 独立的外部测试 Agent 与集成示例
- `tests/`: 自动化端到端测试与单元测试
- `scripts/`: 主要的开发、启动与维护脚本
- `docs/`: 完整的技术架构与运维文档
- `config/`: 中央系统配置文件目录

## 下一步阅读

- [快速开始与启动说明](docs/operability/STARTUP_AND_TEST.md)
- [功能实现概览](docs/operability/FUNCTION_MODULES.md)
- [核心架构说明](docs/architecture/CORE_FOUNDATIONS.md)
- 更多文档见 `docs/` 目录。

## 联系我们

**希望大家一起创建一个有灵魂的大脑！**

- 欢迎通过 [GitHub Issues](https://github.com/xunharry4-source/AnimoCerebro/issues) 或 [GitHub Discussions](https://github.com/xunharry4-source/AnimoCerebro/discussions) 参与讨论。
- 如果你有任何想法或建议，请随时提交 Pull Request 或发起 Issue。

## 开源协议

本项目采用 [GNU GPL v3](LICENSE) 开源协议。

