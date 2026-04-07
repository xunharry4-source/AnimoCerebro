![AnimoCerebro Logo](docs/logo.jpeg)

# AnimoCerebro

[English + 中文](README.md) | 中文详细版

## 概览

AnimoCerebro 是 Agent 与宿主系统的大脑层，负责思考、角色推演、目标生成、风险判断、记忆沉淀、委托建议和长期经验交换。它不是默认执行器，不是默认回复器，也不是用来强行替换现有宿主架构的总控器。

## 它是什么

AnimoCerebro 围绕九问认知循环工作：

1. 我在哪
2. 我是谁
3. 我有什么
4. 我能干什么
5. 我可以干什么
6. 我还能干什么
7. 我不应该也能干什么
8. 我应该干什么
9. 我应该怎么做

## 产品定位

适合把 AnimoCerebro 理解为：

- 单个 Agent 的大脑层
- 现有系统的顾问侧挂层
- 多 Agent 环境的协同大脑
- 挂接到 OpenClaw 之类宿主上的外部大脑

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

- 快速开始：[快速开始-复制即用.md](快速开始-复制即用.md)
- 部署与集成：[详细部署与集成说明.md](详细部署与集成说明.md)
- 单机 Docker：[SINGLE_PROD_DOCKER.md](docs/operability/SINGLE_PROD_DOCKER.md)
- 集群 Docker：[CLUSTER_CORE_DOCKER.md](docs/operability/CLUSTER_CORE_DOCKER.md)
- 公开架构：[CORE_FOUNDATIONS.md](docs/architecture/CORE_FOUNDATIONS.md)
- 公开认知工具接口：[COGNITIVE_TOOL_INTERFACE.md](docs/architecture/COGNITIVE_TOOL_INTERFACE.md)
- 公开 OpenClaw 适配文档：[OPENCLAW_HOST_ADAPTER_PROTOCOL.md](docs/integrations/OPENCLAW_HOST_ADAPTER_PROTOCOL.md)
- OpenClaw 集成手册：[OPENCLAW_INTEGRATION_GUIDE.md](docs/integrations/OPENCLAW_INTEGRATION_GUIDE.md)
- 公开发布清单：[PUBLIC_RELEASE_CHECKLIST.md](docs/operability/PUBLIC_RELEASE_CHECKLIST.md)
- GitHub 公开提交范围：[GITHUB_PUBLIC_SCOPE.md](docs/operability/GITHUB_PUBLIC_SCOPE.md)
- 公开暂存命令：[PUBLIC_GIT_ADD_COMMANDS.md](docs/operability/PUBLIC_GIT_ADD_COMMANDS.md)
- 帮助文档：[帮助文档.md](帮助文档.md)
- 简短帮助入口：[helo.md](helo.md)
- 测试文档：[测试文档.md](测试文档.md)

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

## 安装

推荐 Python 3.11+

```bash
bash scripts/start.sh
```

手动安装：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

CLI：

- `animocerebro`

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

## 快速启动

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

前端热更新：

```bash
bash scripts/web-dev.sh
```

## OpenClaw 接入

OpenClaw 是当前第一个落地的宿主适配实例。适配器不会接管 OpenClaw，而是把 OpenClaw 注册到 AnimoCerebro，同步宿主能力与运行状态，接收委托任务，并回写回执、升级和经验。

Web 控制台现在可以显示并复制当前本地 AnimoCerebro 进程里已配置的 OpenClaw bridge token。

详见：

- [当前对接协议.md](当前对接协议.md)
- [OPENCLAW_INTEGRATION_GUIDE.md](docs/integrations/OPENCLAW_INTEGRATION_GUIDE.md)
- [OPENCLAW_HOST_ADAPTER_PROTOCOL.md](docs/integrations/OPENCLAW_HOST_ADAPTER_PROTOCOL.md)
- [OPENCLAW_HOST_ADAPTER_ARCHITECTURE.md](docs/integrations/OPENCLAW_HOST_ADAPTER_ARCHITECTURE.md)

## 仓库结构

- `src/zentex`: 核心后端与服务
- `src/studio`: Web 前端
- `integrations/`: 各类宿主适配器
- `tests/`: 自动化测试
- `scripts/`: 启动、开发和真实验收脚本
- `docs/`: 运维和设计文档

## 下一步阅读

- 只想复制就跑：[快速开始-复制即用.md](快速开始-复制即用.md)
- 想看部署细节：[详细部署与集成说明.md](详细部署与集成说明.md)
- 想看接入帮助：[帮助文档.md](帮助文档.md)
- 想看协议细节：[当前对接协议.md](当前对接协议.md)
