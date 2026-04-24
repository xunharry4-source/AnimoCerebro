# Self-Promotion Agent

基于 LLM 的智能社交媒体推广 Agent，能够自主为 AnimoCerebro 项目生成周度推广计划并通过浏览器自动化发布到 Reddit 和 X (Twitter)。

## 功能特性

- 🤖 **LLM 驱动的内容生成**：使用 Gemini/OpenAI/Claude 智能分析项目特点并生成推广内容
- 📅 **周计划自动生成**：一键生成7天的详细推广计划，覆盖不同平台和社区
- 🌐 **浏览器自动化**：通过 Playwright 模拟真实浏览器操作，支持人工协助处理 CAPTCHA
- 🔧 **智能错误修复**：Reddit 发帖失败时自动分析原因并修正内容
- 👥 **人机协作**：支持人类中途指定推广内容和干预决策
- 📊 **完整审计追踪**：所有操作记录审计日志，符合 Zentex 红线要求
- 🚀 **Zentex 远程 Agent**：标准 HTTP REST API 接口，易于集成

## 快速开始

### 1. 安装依赖

```bash
# 安装 Python 依赖
pip install fastapi uvicorn[standard] pydantic

# 安装 Playwright（用于浏览器自动化）
# 方法一：使用 pip
pip install playwright
playwright install chromium

# 方法二：使用官方 CLI（推荐，更可靠）
# 详见: https://playwright.dev/docs/getting-started-cli
npm init playwright@latest
# 或
npx playwright install chromium
```

**验证安装**：
```bash
# 检查 Playwright 是否安装成功
python -c "from playwright.sync_api import sync_playwright; print('✅ Playwright installed')"

# 查看已安装的浏览器
playwright install --dry-run
```

### 2. 配置 LLM API 密钥

Self-Promotion Agent 会自动使用 `config/provider_tools.yml` 中配置的 `default_provider`。

**当前默认配置**：
```yaml
default_provider: openai_compat  # 本地代理（推荐用于开发）
```

**配置 API 密钥**：

在项目根目录创建 `.env` 文件：

```bash
# 如果使用 openai_compat（本地代理）
your-api-key=your-local-proxy-key

# 如果使用 Google Gemini
GEMINI_API_KEY=your-gemini-api-key

# 如果使用 OpenAI
OPENAI_API_KEY=sk-your-openai-key

# 如果使用 Anthropic Claude
ANTHROPIC_API_KEY=your-anthropic-key
```

**切换默认提供商**：

修改 `config/provider_tools.yml` 中的 `default_provider` 字段，或设置环境变量：

```bash
export ZENTEX_DEFAULT_PROVIDER=gemini
```

### 3. 启动 Agent 服务器

```bash
./scripts/start_self_promotion_agent.sh
```

服务器将在 `http://127.0.0.1:9004` 运行。

### 4. 验证安装

```bash
# 健康检查
curl http://127.0.0.1:9004/status

# 握手测试
curl -X POST http://127.0.0.1:9004/handshake

# 查看 API 文档
open http://127.0.0.1:9004/docs
```

## 使用方式

### 方式一：直接导入使用

```python
from Agent.self_promotion_agent import self_promotion_agent

# 获取 Agent 信息
info = self_promotion_agent.get_info()
print(f"Agent: {info['name']}")

# 提交人类干预请求
result = self_promotion_agent.submit_human_request(
    content="请推广我们的新功能：实时协作编辑",
    platform="both",
    priority="high"
)

# 查询审计日志
logs = self_promotion_agent.get_audit_log(limit=10)
```

### 方式二：通过 FastAPI HTTP 接口

```python
import httpx

async def use_agent():
    async with httpx.AsyncClient() as client:
        # 生成周计划
        response = await client.post(
            "http://127.0.0.1:9004/execute",
            json={
                "task_id": "task-001",
                "action": "generate_weekly_plan",
                "params": {
                    "project_info": {
                        "name": "AnimoCerebro",
                        "description": "AI brain for agents",
                        "tech_stack": ["Python", "FastAPI"],
                        "features": ["Nine-question cognitive cycle"]
                    },
                    "target_audience": "AI developers",
                    "goals": ["increase awareness"],
                    "target_communities": ["r/MachineLearning"],
                    "week_start": "2026-04-20T00:00:00+00:00"
                }
            }
        )

        result = response.json()
        if result["success"]:
            plan_id = result["result"]["plan_id"]
            print(f"Plan generated: {plan_id}")
```

### 方式三：通过 Zentex Web Console

1. 启动 Zentex 后端：`make dev`
2. 访问 Web Console：`http://127.0.0.1:5173`
3. 在 Agents 页面注册 Self-Promotion Agent
4. 通过界面触发任务

## 核心功能

### 1. 生成周度推广计划

```python
result = self_promotion_agent.generate_weekly_plan(
    project_info={
        "name": "Your Project",
        "description": "Project description",
        "tech_stack": ["Python", "React"],
        "features": ["Feature 1", "Feature 2"]
    },
    target_audience="Target audience description",
    goals=["Goal 1", "Goal 2"],
    target_communities=["r/Subreddit", "#Hashtag"],
    week_start=datetime.now(timezone.utc)
)
```

### 2. 提交人类干预请求

允许人类中途指定要推广的内容：

```python
result = self_promotion_agent.submit_human_request(
    content="Please promote our new feature: real-time collaboration",
    platform="x",  # or "reddit", "both"
    priority="high"  # or "normal", "low"
)
```

### 3. 查询审计日志

```python
# 获取所有日志
logs = self_promotion_agent.get_audit_log(limit=50)

# 过滤特定类型的日志
human_requests = self_promotion_agent.get_audit_log(
    action_filter="human_intervention_request"
)
```

### 4. 追踪推广效果

```python
stats = self_promotion_agent.track_promotion_results(plan_id="plan-xxx")
print(f"Total posts: {stats['results']['total_posts']}")
print(f"Published: {stats['results']['published']}")
print(f"Error rate: {stats['results']['error_rate']:.2%}")
```

## 架构设计

### 核心组件

```
SelfPromotionAgent
├── WeeklyPlanGenerator      # 周计划生成器（LLM 驱动）
├── ContentStrategyEngine    # 内容策略引擎（优化和修复）
├── BrowserAutomationManager # 浏览器自动化（Playwright）
└── AuditLogger              # 审计日志系统
```

### 数据流

```
用户请求 → FastAPI Server → SelfPromotionAgent
                              ↓
                      WeeklyPlanGenerator (LLM)
                              ↓
                      生成周计划 → 保存到内存
                              ↓
                      BrowserAutomation (可选)
                              ↓
                      发布到社交平台
                              ↓
                      审计日志记录
```

## 测试

运行单元测试：

```bash
pytest Agent/test_self_promotion_agent.py -v
```

运行使用示例：

```bash
python Agent/example_self_promotion_usage.py
```

## 注意事项

### Fail-Closed 原则

- LLM 调用失败时会抛出异常，不会静默降级
- 浏览器自动化不可用时，相关功能会返回错误而非伪造结果
- 所有关键操作都有审计日志记录

### 真实性边界

- **LLM 调用**：必须真实调用 Gemini/OpenAI/Claude，禁止 mock
- **浏览器操作**：必须真实打开浏览器窗口，可见操作过程
- **人工协助**：遇到 CAPTCHA 时必须暂停并等待人类操作
- **审计日志**：所有状态变更必须写入审计链，带 trace_id

### 限制和风险

1. **社交平台封号风险**：频繁发帖可能被判定为 spam
   - 缓解：遵守平台规则，控制发帖频率

2. **LLM 成本**：每次生成周计划需要多次 LLM 调用
   - 缓解：缓存计划结果，限制每日调用次数

3. **浏览器会话持久化**：cookies 过期后需要重新登录
   - 缓解：实现会话保存/加载机制

## 故障排除

### 问题：LLM 服务不可用

```
RuntimeError: LLM MANDATORY: ModelProvider not available
```

**解决**：
1. 检查 `.env` 文件中是否配置了 API 密钥
2. 确认网络连接正常
3. 验证 API 密钥有效

### 问题：Playwright 未安装

```
ImportError: Playwright is required for browser automation
```

**解决**：
```bash
pip install playwright
playwright install chromium
```

### 问题：无法连接到服务器

```
httpx.ConnectError: All connection attempts failed
```

**解决**：
1. 确认服务器已启动：`./scripts/start_self_promotion_agent.sh`
2. 检查端口 9004 是否被占用
3. 查看服务器日志是否有错误

## 开发指南

### 添加新的任务类型

1. 在 `self_promotion_server.py` 中添加新的处理器函数
2. 在 `/execute` 端点的路由中添加新的 action
3. 更新 `/handshake` 端点的 capabilities 列表

### 扩展内容优化策略

修改 `ContentStrategyEngine` 类中的方法：
- `_optimize_for_x()`：X 平台内容优化
- `_optimize_for_reddit()`：Reddit 内容优化
- `fix_reddit_post_error()`：错误修复逻辑

## 许可证

本项目采用 GNU GPL v3 开源协议。

## 贡献

欢迎提交 Issue 和 Pull Request！

---

**注意**：由于涉及真实的社交媒体发布，建议在测试环境中充分验证后再在生产环境使用。首次使用时应有人工监督整个流程。
