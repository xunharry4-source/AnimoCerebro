# Agent 测试目录

## 📝 说明

此目录包含**独立的外部测试 Agent**，用于测试 Zentex 的 Agent 管理功能。

---

## ⚠️ 重要设计原则

### **禁止事项（红线）**

❌ **禁止引入 Zentex 代码**
- 外部 Agent **绝对不能** import 任何 `zentex.*` 模块
- 不能依赖 Zentex 的内部数据结构（如 `AgentAsset`, `AgentStatus` 等）
- 不能修改 Zentex 的核心代码来适配外部 Agent

❌ **禁止修改 Zentex 来适配**
- 不能为了注册外部 Agent 而修改 `dev_server.py` 或其他核心文件
- 不能侵入式地耦合外部实现与 Zentex 内部逻辑

### **正确方式：标准对接协议**

✅ **通过标准 API 接口对接**
- 外部 Agent 只需实现标准的 HTTP/WebSocket 接口
- Zentex 通过统一的协议层发现和调用外部 Agent
- 双方保持完全解耦，独立演进

---

## 🔌 标准对接协议

Zentex 提供三类外部能力接入方式，每种都有明确的标准化接口：

### **1️⃣ CLI 工具接入（最简单）**

**适用场景**：命令行工具、脚本、可执行文件

**注册信息**（只需提供以下内容）：
```json
{
  "tool_name": "my-cli-tool",
  "project_url": "https://github.com/user/my-tool",
  "project_name": "My CLI Tool",
  "description": "Tool description",
  "documentation_url": "https://docs.example.com",
  "command_executable": "/path/to/command",
  "read_only_flag": true,
  "arguments_schema": {
    "type": "object",
    "properties": {
      "--input": {"type": "string"}
    }
  }
}
```

**API 端点**：
```bash
POST /api/web/cli-tools/register
GET  /api/web/cli-tools          # 查看已注册工具
GET  /api/web/cli-adapters       # 查看适配器状态
```

**特点**：
- ✅ 零代码修改，只需配置
- ✅ 自动分类为认知工具（只读）或执行插件（有副作用）
- ✅ 强制安全门和审计追踪

---

### **2️⃣ MCP Server 接入（推荐用于 AI 工具）**

**适用场景**：Model Context Protocol 服务器，提供 AI 可调用的工具

**注册信息**（只需提供以下内容）：
```json
{
  "server_id": "my-mcp-server",
  "server_name": "My MCP Server",
  "description": "Server description and capabilities",
  "documentation_url": "https://docs.example.com/mcp",
  "endpoint": "http://localhost:3001/mcp",
  "transport_type": "http",  // 或 "stdio", "streamable"
  "protocol_version": "2024-11-05",
  "auth_mode": "bearer_token",  // 或 "none", "api_key"
  "scope": ["read", "write"]
}
```

**API 端点**：
```bash
POST /api/web/mcp-servers/register
GET  /api/web/mcp-servers          # 查看所有 MCP Server
GET  /api/web/mcp-servers/{id}/health  # 健康检查
```

**MCP 协议交互流程**：
```
1. Zentex → MCP: 初始化握手 (initialize)
2. MCP → Zentex: 返回能力和工具清单
3. Zentex → MCP: 周期性健康检查
4. Zentex → MCP: 调用工具 (call_tool)
5. MCP → Zentex: 返回执行结果
```

**特点**：
- ✅ 标准化协议，生态丰富
- ✅ 自动工具发现和能力协商
- ✅ 完整的 schema 管理和版本控制

---

### **3️⃣ Agent 接入（完整 Agent 系统）**

**适用场景**：独立的智能体系统，需要双向交互和任务调度

**注册信息**（只需提供以下内容）：
```json
{
  "agent_id": "agent-calculator",
  "agent_name": "Calculator Agent",
  "version": "1.0.0",
  "description": "Provides mathematical calculation capabilities",
  "documentation_url": "https://docs.example.com/agent",
  "endpoint": "http://localhost:9001/api",
  "protocol_type": "http",  // 或 "websocket", "grpc"
  "capabilities": [
    {
      "name": "calculate",
      "description": "Perform mathematical operations",
      "input_schema": {
        "operation": "string",
        "a": "number",
        "b": "number"
      },
      "output_schema": {
        "result": "number",
        "success": "boolean"
      }
    }
  ],
  "auth_token": "optional-token",
  "scope": ["calculation", "math"]
}
```

**标准交互接口**（Agent 需要实现的端点）：

```python
# Agent 侧需要实现的接口

# 1. 能力握手
@app.post("/handshake")
def handshake():
    return {
        "agent_id": "agent-calculator",
        "version": "1.0.0",
        "capabilities": [...],
        "status": "online"
    }

# 2. 心跳上报（可选，或由 Zentex 主动探测）
@app.post("/heartbeat")
def heartbeat():
    return {"status": "healthy", "timestamp": "..."}

# 3. 接收任务
@app.post("/execute")
def execute(request: dict):
    """
    接收 Zentex 分发的任务
    """
    task_id = request["task_id"]
    action = request["action"]
    params = request["params"]
    
    # 执行任务
    result = perform_action(action, params)
    
    # 返回执行回执
    return {
        "task_id": task_id,
        "success": True,
        "result": result,
        "timestamp": "..."
    }

# 4. 状态查询
@app.get("/status")
def status():
    return {
        "agent_id": "agent-calculator",
        "status": "online",  # online/degraded/offline/paused
        "uptime_seconds": 3600,
        "tasks_completed": 150
    }
```

**Zentex 提供的调用接口**：
```bash
# Zentex 会调用这些接口与 Agent 交互
POST http://your-agent/handshake   # 能力握手
POST http://your-agent/execute     # 执行任务
GET  http://your-agent/status      # 查询状态
POST http://your-agent/heartbeat   # 心跳上报（可选）
```

**API 端点**（在 Zentex 侧注册）：
```bash
POST /api/web/agents/register      # 注册 Agent
GET  /api/web/agents               # 查看所有 Agent
GET  /api/web/agents/{id}/status   # 查询 Agent 状态
POST /api/web/agents/{id}/task     # 分发任务到 Agent
```

**特点**：
- ✅ 完整的双向通信能力
- ✅ 支持任务调度和结果回执
- ✅ 健康监控和故障恢复
- ✅ 授信管理和权限控制

---

## 🎯 当前测试 Agent 示例

本目录中的 Agent 展示了如何设计**完全独立**的外部 Agent：

### 1. Calculator Agent (计算 Agent)

**功能**: 提供基本数学计算能力

**启动方式**:
```bash
./Agent/start_calculator.sh
```

**支持的操作**:
- add (加法)
- subtract (减法)
- multiply (乘法)
- divide (除法)
- power (幂运算)

**如果要通过标准协议接入 Zentex**，只需实现上述 HTTP 接口即可，无需修改任何 Zentex 代码。

---

### 2. Data Generator Agent (数据生成 Agent)

**功能**: 在 testdata 目录下随机生成 CSV 文件

**启动方式**:
```bash
./Agent/start_data_generator.sh
```

**生成内容**:
- 文件名: `agent_generated_data.csv`
- 位置: `testdata/` 目录
- 行数: 10 行随机数据
- 字段: id, name, value, category, status, created_at, score, description, is_valid, priority, tags

**注册为 CLI 工具示例**：
```bash
curl -X POST http://localhost:8000/api/web/cli-tools/register \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "data-generator",
    "project_url": "https://github.com/your-org/animocerebro/tree/main/Agent",
    "project_name": "Data Generator Agent",
    "description": "Generates random CSV data for testing",
    "documentation_url": "https://github.com/your-org/animocerebro/blob/main/Agent/README.md",
    "command_executable": "./Agent/start_data_generator.sh",
    "read_only_flag": false,
    "arguments_schema": {
      "type": "object",
      "properties": {
        "--rows": {"type": "integer", "default": 10},
        "--output": {"type": "string", "default": "random_data.csv"}
      }
    }
  }'
```

---

### 3. Browser Automation Agents (浏览器自动化 Agent) ⭐ 新增

**功能**: 基于 Playwright 的社交媒体自动化系统

#### 3.1 Stealth Chrome 自动化
- **文件**: `test_auto_stealth_wait.py`
- **功能**: 绕过检测的 Chrome 自动化，支持 X.com 和 Reddit 发帖
- **特点**:
  - ✅ 使用真实 Google Chrome 二进制文件
  - ✅ 持久化上下文（登录状态保持）
  - ✅ 增强的隐身脚本（13项指纹隐藏）
  - ✅ 禁用 AutomationControlled 标志
  - ✅ 与系统 Chrome 完全隔离

**使用方法**:
```bash
python Agent/test_auto_stealth_wait.py
```

#### 3.2 智能 Reddit 发帖器
- **文件**: `reddit_smart_poster.py` (975 行)
- **功能**: 带反复纠错机制的智能 Reddit 发帖
- **特点**:
  - ✅ 自动检查和下载社区规则
  - ✅ 每个社区规则单独保存
  - ✅ 基于规则生成合规内容
  - ✅ 最多 3 次重试机制
  - ✅ 错误检测和分类（6种类型）
  - ✅ 智能 Flair 选择

**核心 API**:
```python
from Agent.reddit_smart_poster import RedditSmartPoster

poster = RedditSmartPoster(page, rules_manager)

# 自动内容发帖
success = poster.post_with_retry("Python", max_retries=3)

# 自定义内容发帖
success = poster.post_custom_content(
    subreddit="Python",
    title="My Title",
    content="My Content",
    flair="Discussion",
    max_retries=3
)
```

#### 3.3 AnimoCerebro 宣传助手 ⭐ 新增
- **文件**: `animocerebro_promoter.py` (742 行)
- **功能**: 针对 AnimoCerebro 项目的智能宣传系统
- **特点**:
  - ✅ 双模式宣传策略
    - 模式 A: r/AnimoCerebro 发布项目进度
    - 模式 B: 技术社区定制化宣传
  - ✅ 支持 7 个技术社区（Python, ML, AI, CS, Programming, Learning）
  - ✅ 每个社区定制化内容模板
  - ✅ 基于规则的合规检查
  - ✅ 反复纠错和重试

**使用方法**:
```python
from Agent.animocerebro_promoter import AnimoCerebroPromoter

promoter = AnimoCerebroPromoter(page, rules_manager)

# 在 r/AnimoCerebro 发布项目进度
promoter.promote_in_own_community("AnimoCerebro")

# 在技术社区宣传
results = promoter.promote_in_tech_communities([
    "Python", 
    "MachineLearning", 
    "learnprogramming"
])
```

**支持的社区和内容策略**:

| 社区 | 内容重点 | Flair | 优先级 |
|------|---------|-------|--------|
| r/AnimoCerebro | 项目进度和特点 | Project Update | ⭐⭐⭐ |
| r/Python | Python 技术实现 | Showcase | ⭐⭐⭐ |
| r/MachineLearning | AI/ML 研究角度 | Project | ⭐⭐⭐ |
| r/artificial | AI 系统架构 | Discussion | ⭐⭐ |
| r/compsci | 计算机科学视角 | Systems | ⭐⭐ |
| r/programming | 编程实践分享 | Project | ⭐⭐ |
| r/learnprogramming | 学习经验分享 | Question | ⭐⭐ |

#### 3.4 社区规则管理器
- **文件**: `community_rules_manager.py` (517 行)
- **功能**: 自动管理和缓存 Reddit 社区规则
- **特点**:
  - ✅ 每个社区规则单独保存为 JSON
  - ✅ 自动从网页抓取规则
  - ✅ 规则过期检查和更新
  - ✅ 发帖前规则验证

**缓存位置**: `Agent/community_rules_cache/{subreddit}.json`

#### 3.5 综合测试脚本
- **文件**: `test_social_media_automation.py` (901 行)
- **功能**: 完整的社交媒体自动化测试套件
- **测试内容**:
  1. X.com 自动发帖
  2. Reddit 社区规则获取
  3. Reddit 违规内容检测
  4. Reddit 自动发帖 + Flair 选择
  5. AnimoCerebro 宣传发帖

**使用方法**:
```bash
python Agent/tests/test_social_media_automation.py
```

---

### 4. LangGraph + CrewAI 智能工作流 ⭐⭐⭐ 最新

**功能**: 整合所有社交媒体自动化功能的智能工作流系统

#### 4.1 LangGraph + CrewAI 发布者
- **文件**: `langgraph_crewai_publisher.py` (652 行)
- **功能**: 基于 LangGraph + CrewAI 的内容发布系统
- **架构**:
  - **节点 A**: 主题分析器（LLM 判断今天发什么）
  - **节点 B**: CrewAI 团队（文案 + 校对，反复迭代）
  - **节点 C**: 内容发布器（调用 API 发送）
  - **节点 D**: 监控系统（失败时退回节点 B）

**使用方法**:
```python
from Agent.langgraph_crewai_publisher import ContentPublishingWorkflow

workflow = ContentPublishingWorkflow(max_iterations=3, max_retries=2)

result = workflow.run(
    raw_material="项目进展...",
    target_platforms=["Twitter", "小红书"]
)
```

#### 4.2 LangGraph 社交媒体工作流 ⭐ 核心整合
- **文件**: `langgraph_social_media_workflow.py` (855 行)
- **功能**: **整合所有现有功能的统一工作流**
  - ✅ 浏览器自动化（Playwright Stealth Chrome）
  - ✅ Reddit 智能发帖（带规则检查）
  - ✅ X.com 自动发帖
  - ✅ AnimoCerebro 宣传助手
  - ✅ 每周发帖计划
  - ✅ CrewAI 内容创作
  - ✅ 自动监控和错误恢复

**架构**:
```
节点 A: 计划生成（使用每周计划或 LLM 分析）
   ↓
节点 B: CrewAI 内容创作（文案 + 校对，反复迭代）
   ↓
节点 C: 浏览器自动化执行（Reddit + X.com 发帖）
   ↓
节点 D: 监控和错误恢复（失败时退回节点 B）
```

**使用方法**:
```python
from Agent.langgraph_social_media_workflow import SocialMediaPublishingWorkflow

workflow = SocialMediaPublishingWorkflow(
    max_iterations=3,
    max_retries=2
)

result = workflow.run(
    raw_material="""
    AnimoCerebro 项目重大更新：
    1. 完成了 LangGraph + CrewAI 集成
    2. 实现了智能内容创作工作流
    3. 整合了浏览器自动化
    """,
    target_platforms=["reddit", "x"],
    target_subreddits=["AnimoCerebro", "Python"],
    use_weekly_plan=False
)
```

**核心特性**:
- ✅ **智能计划**: 支持每周计划或实时分析
- ✅ **多平台**: 同时支持 Reddit 和 X.com
- ✅ **CrewAI 协作**: 文案专家和校对编辑反复迭代
- ✅ **浏览器自动化**: 使用 Stealth Chrome 绕过检测
- ✅ **规则合规**: 自动检查和遵守社区规则
- ✅ **错误恢复**: 失败时自动重试和修正
- ✅ **完整监控**: 实时监控发布状态和结果

---

## 📁 文件结构

```
Agent/
├── README.md                      # 本文档（对接协议说明）
│
├── 🧮 基础 Agent
├── calculator_agent.py            # Calculator Agent 实现（完全独立）
├── data_generator_agent.py        # Data Generator Agent 实现（完全独立）
├── start_calculator.sh            # Calculator Agent 启动脚本
├── start_data_generator.sh        # Data Generator Agent 启动脚本
│
├── 🌐 浏览器自动化 Agent ⭐ 新增
├── browser_automation.py          # 浏览器自动化核心模块 (23KB)
├── reddit_smart_poster.py         # Reddit 智能发帖器 (975行/36KB) ⭐
├── animocerebro_promoter.py       # AnimoCerebro 宣传助手 (742行/21KB) ⭐
├── community_rules_manager.py     # 社区规则管理器 (517行/17KB) ⭐
├── test_auto_stealth_wait.py      # Stealth Chrome 测试 (17KB) ⭐
├── test_social_media_automation.py # 综合测试脚本 (901行/35KB) ⭐
│
├── 📂 数据缓存
├── community_rules_cache/         # 社区规则缓存目录 ⭐
│   ├── Python.json               # r/Python 规则
│   ├── MachineLearning.json      # r/MachineLearning 规则
│   └── ...
├── chrome_custom_profile/         # Chrome 用户数据目录 ⭐
│   └── Default/                  # 包含 Cookie 和会话数据
│
├── 📸 截图和日志
├── screenshots/                   # 自动化截图目录
│   ├── x_post_success.png
│   ├── reddit_post_success.png
│   └── ...
├── social_automation_test.log     # 测试日志
├── test_results_social_automation.json # 测试结果
│
├── 📚 文档 ⭐ 新增
├── ANIMOCEREBRO_PROMOTER_GUIDE.md       # AnimoCerebro 宣传指南 (12KB) ⭐
├── ANIMOCEREBRO_PROMOTION_SUMMARY.md    # 宣传系统总结 (11KB) ⭐
├── REDDIT_SMART_POSTER_GUIDE.md         # Reddit 发帖指南 (12KB) ⭐
├── REDDIT_POSTING_WITH_RULES_SUMMARY.md # 规则管理总结 (10KB) ⭐
├── SOCIAL_MEDIA_TEST_CONFIG.md          # 测试配置说明 (6KB) ⭐
├── SOCIAL_MEDIA_TEST_SUMMARY.md         # 测试总结 (7KB) ⭐
├── STEALTH_CHROME_TEST_REPORT.md        # Stealth 测试报告 (7KB) ⭐
├── TEST_FIX_RECORD.md                   # 问题修复记录 (5KB) ⭐
├── QUICK_REFERENCE.md                   # 快速参考卡片 (4KB) ⭐
│
├── 🔧 其他文件
├── __init__.py                    # 包初始化
├── example_browser_automation.py  # 浏览器自动化示例
├── quick_test.py                  # 快速测试脚本
└── ...                            # 其他测试和示例文件
```

**统计**:
- 核心代码: ~3,500+ 行
- 文档: ~2,500+ 行
- 总计: ~6,000+ 行
- 新增功能: 浏览器自动化、Reddit 智能发帖、AnimoCerebro 宣传系统

---

## 🔧 开发指南

### **创建新的外部 Agent**

1. **保持独立性**
   ```python
   # ✅ 正确：不引入 zentex 依赖
   class MyAgent:
       def __init__(self):
           self.agent_id = "my-agent"
           self.capabilities = ["feature1", "feature2"]
   
   # ❌ 错误：不要这样做
   from zentex.agents.manager import AgentAsset  # 禁止！
   ```

2. **实现标准接口**
   ```python
   from fastapi import FastAPI
   
   app = FastAPI()
   
   @app.post("/handshake")
   def handshake():
       return {"agent_id": "my-agent", "capabilities": [...]}
   
   @app.post("/execute")
   def execute(request: dict):
       # 执行任务并返回结果
       return {"success": True, "result": ...}
   ```

3. **提供必要信息**
   - Project URL
   - Project Name
   - Description
   - Documentation URL
   - Endpoint URL
   - Capabilities list

4. **注册到 Zentex**
   ```bash
   curl -X POST http://localhost:8000/api/web/agents/register \
     -d @agent-registration.json
   ```

### **关键原则**

✅ **DO**:
- 保持 Agent 完全独立
- 实现标准 HTTP/WebSocket 接口
- 提供完整的文档和元数据
- 处理错误和超时
- 返回结构化的执行结果

❌ **DON'T**:
- 引入 zentex 模块
- 修改 Zentex 核心代码
- 依赖 Zentex 内部数据结构
- 硬编码 Zentex 的实现细节

---

## 🚀 快速开始

### 单独启动 Agent

```bash
# 启动 Calculator Agent
./Agent/start_calculator.sh

# 启动 Data Generator Agent
./Agent/start_data_generator.sh
```

### 同时启动两个 Agent

```bash
# 在后台同时启动两个 Agent
./Agent/start_calculator.sh &
./Agent/start_data_generator.sh &
```

### 测试独立运行

```bash
# 验证 Agent 可以独立工作
python3 -c "
import sys
sys.path.insert(0, '.')
from Agent.calculator_agent import calculator_agent

result = calculator_agent.calculate('add', 10, 5)
print(f'Result: {result}')
"
```

### ⭐ 新增：浏览器自动化测试

```bash
# 激活虚拟环境
source .venv/bin/activate

# 运行 Stealth Chrome 测试
python Agent/test_auto_stealth_wait.py

# 运行综合社交媒体测试
python Agent/test_social_media_automation.py

# 运行 AnimoCerebro 宣传测试
python -c "
from Agent.animocerebro_promoter import AnimoCerebroPromoter
from Agent.community_rules_manager import CommunityRulesManager
from playwright.sync_api import sync_playwright

playwright = sync_playwright().start()
browser = playwright.chromium.launch(headless=False)
page = browser.new_page()
# ... 手动登录 Reddit ...

rules_manager = CommunityRulesManager()
promoter = AnimoCerebroPromoter(page, rules_manager)

# 在 r/AnimoCerebro 发布项目进度
promoter.promote_in_own_community('AnimoCerebro')

# 在技术社区宣传
promoter.promote_in_tech_communities(['Python', 'learnprogramming'])

browser.close()
playwright.stop()
"
```

---

## 📊 对接状态

| Agent | 独立性 | 标准接口 | 可注册 | 状态 |
|-------|--------|----------|--------|------|
| Calculator Agent | ✅ 完全独立 | ⏸️ 待实现 | ⏸️ 等待 API | 测试准备就绪 |
| Data Generator Agent | ✅ 完全独立 | ⏸️ 待实现 | ✅ 可作为 CLI | 测试准备就绪 |
| **Browser Automation** | ✅ 完全独立 | ✅ HTTP API | ✅ 可注册 | ✅ **已实现** ⭐ |
| **Reddit Smart Poster** | ✅ 完全独立 | ✅ HTTP API | ✅ 可注册 | ✅ **已实现** ⭐ |
| **AnimoCerebro Promoter** | ✅ 完全独立 | ✅ HTTP API | ✅ 可注册 | ✅ **已实现** ⭐ |
| **Community Rules Manager** | ✅ 完全独立 | ✅ File-based | ✅ 自动缓存 | ✅ **已实现** ⭐ |

---

## 🔗 相关文档

- **Zentex 产品功能文档**: `/Zentex_产品功能文档-v1.md`
  - Agent 管理: 第 1140-1178 行
  - MCP 管理: 第 3215-3268 行
  - CLI 管理: 第 1626-1665 行
  - 外部对接协议: 第 637-643 行

---

**创建时间**: 2026-04-07  
**最后更新**: 2026-04-20 ⭐  
**状态**: 测试环境 + **新增浏览器自动化功能** ⭐  
**独立性**: ✅ 完全独立，不依赖主项目  
**对接方式**: 🔌 标准协议接口（已实现）  
**新增功能**: 
- 🌐 浏览器自动化系统 (Stealth Chrome)
- 🤖 Reddit 智能发帖器 (带反复纠错)
- 📢 AnimoCerebro 宣传助手 (双模式策略)
- 📋 社区规则管理器 (自动缓存)
- 📸 完整的测试和文档体系
