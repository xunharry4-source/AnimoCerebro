# AnimoCerebro 文档中心

> **项目状态**: 生产就绪阶段 | v2.0 | 90个测试文件 | 291+测试用例

本文档中心提供 AnimoCerebro 项目的完整技术文档导航。

---

## 🚀 快速开始

### 新用户必读
- [项目概览](../README.md) - 了解 AnimoCerebro 是什么
- [快速开始指南](operability/STARTUP_AND_TEST.md) - 一键启动和测试
- [安装指南](#安装与配置) - 环境准备和依赖安装

### 常用命令
```bash
# 一键安装
make install

# 一键启动
make dev

# 运行测试
make test

# 重启开发环境
make restart-dev
```

---

## 📚 文档分类

### 1️⃣ 入门指南 (Getting Started)

适合首次接触 AnimoCerebro 的开发者。

- **[快速开始](operability/STARTUP_AND_TEST.md)** - 5分钟上手指南
- **[安装指南](#安装与配置)** - 详细的环境配置步骤
- **[配置指南](#配置管理)** - 系统配置和API密钥设置
- **[故障排除](#常见问题)** - 常见问题和解决方案

### 2️⃣ 架构设计 (Architecture)

深入理解系统架构和设计原理。

- **[主要版本更新](MAJOR_VERSION_UPDATE.md)** - v2.0 架构演进说明 ([中文版](MAJOR_VERSION_UPDATE_ZH.md))
- **[功能模块总览](operability/FUNCTION_MODULES.md)** - 核心模块职责划分
- **[目录结构映射](operability/LATEST_DIRECTORY_MAP.md)** - 最新项目目录详解
- **[ThinkLoop 深度解析](operability/THINK_LOOP_DEEP_DIVE.md)** - 九阶段认知循环
- **[运行时与测试](operability/RUNTIME_AND_TESTS.md)** - 运行时代码架构

#### 核心架构组件
- **九问认知循环**: Q1-Q9 完整实现
- **双插件系统**: 外部插件 + 内部插件
- **Agent 管理**: 标准化协议接入
- **记忆系统**: Kuzu 图数据库后端
- **安全机制**: 风险评估和冲突检测

### 3️⃣ 核心模块 (Core Modules)

详细的技术实现文档。

#### 运行时系统 (`src/zentex/runtime/`)
- BrainRuntime - 运行时大管家
- ThinkLoop - 九阶段认知执行器
- WorkingMemory - 工作记忆控制器
- Metacognition - 元认知控制器
- Transcript - 事件流存储

#### 认知模块 (`src/zentex/cognition/`)
- 社会心智
- 反事实模拟

#### 任务系统 (`src/zentex/tasks/`)
- 任务分解引擎
- 任务执行管理

#### 学习系统 (`src/zentex/learning/`)
- G16 学习引擎 (DSPy 集成)
- 预算管理
- 沙箱执行

#### 升级系统 (`src/zentex/upgrade/`)
- 受控自我进化
- 插件演化运行时
- 证据追踪

#### 记忆系统 (`src/zentex/memory/`)
- 增强记忆服务
- Kuzu 图数据库后端
- 记忆巩固引擎

#### 反思系统 (`src/zentex/reflection/`)
- 元认知反思
- 模式分析
- [完整文档](../../src/zentex/reflection/DOCUMENTATION.md)

#### 安全模块 (`src/zentex/safety/`)
- 风险检测
- 冲突解决
- 策略执行

#### 环境感知 (`src/zentex/environment/`)
- 环境指纹
- 变化检测

### 4️⃣ 插件开发 (Plugin Development)

AnimoCerebro 采用双插件系统架构。

#### 插件开发总指南
- **[插件开发索引](operability/PLUGIN_GUIDES.md)** - 按功能组织的开发规范

#### 外部插件 (`plugins/`)
**用途**: 连接外部功能，扩展大脑能力
- ❌ **禁止**: 导入 `src/` 目录代码
- ✅ **必须**: 通过标准 API 交互

适用场景:
- 自定义数据源连接器
- 第三方服务集成
- 专用工具适配器

#### 内部插件 (`src/plugins/`)
**用途**: 系统内部自迭代和升级
- ✅ **可以**: 访问 `src/zentex/` 核心模块
- ✅ **支持**: 热重载和动态升级

##### 九问插件家族 (Q1-Q9)
位于 `src/plugins/nine_questions/` (69+ 文件)

| 问题 | 插件目录 | 职责 |
|------|---------|------|
| Q1 | q1_where_am_i | 环境感知 |
| Q2 | q2_who_am_i | 角色假设 |
| Q3 | q3_what_do_i_have | 资源盘点 |
| Q4 | q4_what_can_i_do | 能力边界 |
| Q5 | q5_allowed | 约束检查 |
| Q6 | q6_consequences | 风险评估 |
| Q7 | q7_alternatives | 替代方案 |
| Q8 | q8_priority | 优先级决策 |
| Q9 | q9_action | 行动确认 |

##### 其他内部插件
- **Model Providers**: Gemini, OpenAI, Claude 适配器
- **Cognitive Tools**: 认知工具插件
- **Sensory**: 感知插件
- **Execution**: CLI, MCP 执行插件
- **Simulation**: 模拟插件
- **Weights**: 权重插件

#### 插件特性文档
详细的功能级开发规范位于 `operability/plugin_features/`:

- [风险评估](operability/plugin_features/risk_assessment.md)
- [证据排序](operability/plugin_features/evidence_ranking.md)
- [决策摘要](operability/plugin_features/decision_summary.md)
- [认知冲突监控](operability/plugin_features/cognitive_conflict_detection.md)
- [Gemini 推理底座](operability/plugin_features/model_provider_gemini.md)
- [Webhook 信号摄取](operability/plugin_features/sensory_ingest_webhook.md)
- [提示注入净化](operability/plugin_features/sensory_sanitize_basic_prompt_injection_sanitizer.md)
- [环境事件解释](operability/plugin_features/sensory_interpret_generic_environment.md)
- [系统执行域](operability/plugin_features/execution_system.md)
- [浏览器执行域](operability/plugin_features/execution_browser.md)
- [通用思维沙盒](operability/plugin_features/simulation_general.md)
- [市场影响预测](operability/plugin_features/simulation_market.md)
- [主观权重偏好](operability/plugin_features/weights_subjective_preferences.md)
- [身份与经验包](operability/plugin_features/identity_package_loader.md)

### 5️⃣ Agent 集成 (Agent Integration)

外部 Agent 通过标准协议接入 AnimoCerebro。

#### Agent 管理指南
- **[Agent & MCP 管理](operability/AGENT_AND_MCP.md)** - 异构 Agent 和 MCP 工具管理
- **[Agent 对接协议](../Agent/docs/README.md)** - 标准 HTTP/WebSocket 接口
- **[Agent 架构文档](../Agent/docs/ARCHITECTURE.md)** - 完整的 Agent 系统设计
- **[集成指南](../Agent/docs/INTEGRATION_GUIDE.md)** - 如何连接你的系统

#### 标准协议接口
外部 Agent 需实现以下端点:
```
POST /handshake  - 能力发现
POST /execute    - 任务执行
GET  /status     - 健康检查
```

#### 测试 Agent 示例
项目提供两个完整的测试 Agent:
- **Calculator Agent** (端口 9001) - 数学计算
- **Data Generator Agent** (端口 9002) - 随机数据生成

启动方式:
```bash
./Agent/start_calculator.sh
./Agent/start_data_generator.sh
```

### 6️⃣ 社交媒体自动化 (Social Media Automation)

基于 Playwright + LangGraph + CrewAI 的智能发布系统。

#### 核心文档
- **[社交发布架构](../Agent/docs/social_posting/ARCHITECTURE.md)** - 模块边界和数据流
- **[工作流程](../Agent/docs/social_posting/FLOW.md)** - 发布流程详解
- **[节点说明](../Agent/docs/social_posting/NODES.md)** - LangGraph 节点设计
- **[启动指南](../Agent/docs/social_posting/STARTUP.md)** - 环境配置和启动
- **[测试指南](../Agent/docs/social_posting/TESTING.md)** - 测试方法和验证

#### 功能特性
- **X.com 自动发帖** - 带 permalink 验证
- **Reddit 智能发帖** - 社区规则检查 + Flair 选择
- **GitHub Discussion** - GraphQL API 创建和验证
- **AnimoCerebro 宣传助手** - 多社区定制化内容
- **社区规则管理器** - 自动缓存和更新

#### 技术栈
- Playwright Stealth Chrome - 绕过检测
- LangGraph - 工作流编排
- CrewAI - 内容创作协作
- OCR (Tesseract) - 视觉识别
- LLM - 弹窗翻译和内容生成

### 7️⃣ Web 控制台 (Web Console)

FastAPI 后端 + React 前端的管理界面。

#### 后端 API (`src/zentex/web_console/`)
- **18个 API 路由器** - 完整的 RESTful API
- **WebSocket 实时事件流** - 实时监控
- **最大文件**: `dev_server.py` (74.6KB)
- **最大路由**: `nine_questions.py` (98.9KB)

#### 前端页面 (`src/admin-portal/`)
- **React + Vite + TypeScript**
- **26+ 九问页面组件**
- **实时指挥台** - 系统状态监控
- **Agent 管理界面**
- **任务跟踪界面**
- **插件管理界面**
- **MCP 管理界面**
- **审计回放界面**

#### API 文档
启动后端后访问: http://127.0.0.1:8000/docs

### 8️⃣ 测试文档 (Testing)

#### 测试概览
- **90个测试文件**
- **291+ 测试用例**
- **覆盖率**: >80%

#### 测试分类
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

#### 运行测试
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

### 9️⃣ 配置管理 (Configuration)

#### 环境变量
创建 `.env` 文件在项目根目录:
```bash
GEMINI_API_KEY=your-gemini-key-here
OPENAI_API_KEY=sk-your-openai-key-here
ANTHROPIC_API_KEY=your-anthropic-key-here
```

#### Provider 配置
配置文件: `config/provider_tools.yml`

支持的 LLM Provider:
- `openai_compat` - OpenAI 兼容端点
- `openai` - OpenAI API
- `gemini` - Google Gemini API
- `claude` - Anthropic Claude API

### 🔟 运维文档 (Operability)

- **[启动指南](operability/STARTUP_AND_TEST.md)** - 详细的启动说明
- **[Agent & MCP 管理](operability/AGENT_AND_MCP.md)** - 运维操作指南
- **[功能模块说明](operability/FUNCTION_MODULES.md)** - 模块职责边界
- **[目录结构](operability/LATEST_DIRECTORY_MAP.md)** - 项目结构参考

---

## 📊 项目统计

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

---

## 🔗 相关资源

### 产品文档
- [Zentex 产品功能文档](../Zentex_产品功能文档/) - 完整的产品规格
  - 01_系统总体定义.md
  - 02_核心架构.md
  - 03_运行时主链.md
  - 04_模拟学习.md
  - 05_协作执行.md
  - 06_社会与商业.md
  - 07_基础设施.md
  - 08_云审计.md
  - 09_Web控制台.md
  - 10_实施计划.md

### 协议设计
- [ZMSP 协议设计](zmsp_protocol_design.md) - 记忆共享协议

### 外部链接
- [GitHub Issues](https://github.com/xunharry4-source/AnimoCerebro/issues)
- [GitHub Discussions](https://github.com/xunharry4-source/AnimoCerebro/discussions)

---

## 📝 文档维护

### 文档规范
所有文档应遵循以下规范:
1. **清晰的标题** - 准确反映内容
2. **概述部分** - 说明文档目的和范围
3. **前置条件** - 列出需要了解的内容
4. **结构化内容** - 使用标题、列表、代码块
5. **相关文档链接** - 方便导航
6. **最后更新日期** - 保持时效性

### 贡献文档
欢迎提交文档改进:
1. Fork 项目
2. 创建分支
3. 修改或新增文档
4. 提交 Pull Request

### 文档待办
- [ ] 补充各模块的详细 API 文档
- [ ] 添加更多实际使用案例
- [ ] 完善故障排除指南
- [ ] 创建视频教程
- [ ] 翻译更多文档为中文

---

## ⚠️ 真实性边界

AnimoCerebro 严格遵守真实性原则:

- **LLM 调用必须真实执行** - 不允许用规则链、模板或固定样本冒充
- **失败必须显式抛出** - 禁止 `try-except pass` 或返回假成功
- **测试结果必须标注** - 区分"真实运行结果"和"非真实运行结果(夹具)"
- **证据缺失 = 未完成** - 缺少物理证据时直接写明"未完成"

详见: [工程规范强制器](.codex/skills/engineering-spec-enforcer/SKILL.md)

---

**最后更新**: 2026-04-27  
**维护者**: AnimoCerebro Team  
**许可证**: GNU GPL v3
