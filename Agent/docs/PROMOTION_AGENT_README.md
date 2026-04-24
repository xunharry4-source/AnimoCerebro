# Promotion Agent - 社交媒体宣传自动化代理

## 概述

Promotion Agent 是一个功能完整的社交媒体宣传自动化工具，支持在 X (Twitter) 和 Reddit 平台自动发帖、制定宣传计划、追踪宣传效果，并根据不同社区规则优化内容。

## 核心功能

### 1. 宣传计划管理
- 创建和管理每日/每周/每月宣传计划
- 设定目标受众和宣传目标
- 预算跟踪

### 2. 多平台支持
- **X (Twitter)**: 自动发布推文，支持话题标签
- **Reddit**: 根据不同 subreddit 规则发布帖子

### 3. 内容优化
- 根据平台特性自动优化内容长度
- 智能添加话题标签
- 生成内容变体用于 A/B 测试

### 4. 人工审核工作流
- 提交帖子进行审核
- 批准/拒绝/要求修改
- 批量审核功能
- 完整的审计日志（带 trace_id）

### 5. 浏览器自动化（基于 Playwright）
- 自动打开浏览器进行发帖
- 检测 CAPTCHA 机器人验证
- 等待人工协助完成验证
- 会话管理（保存/加载登录状态）
- 截图调试功能

### 6. 结果追踪和分析
- 实时追踪帖子表现（点赞、评论、分享、浏览）
- 按平台和计划分组统计
- 审计日志追踪所有操作

## 安装

### 基础安装

```bash
pip install -r requirements.txt
```

### 浏览器自动化（可选）

如果需要使用浏览器自动发帖功能：

```bash
pip install playwright
playwright install
```

## 快速开始

### 1. 基本使用

```python
from Agent.promotion_agent import PromotionAgent
from datetime import datetime, timezone, timedelta

# 创建 Agent
agent = PromotionAgent()

# 创建宣传计划
plan = agent.create_promotion_plan(
    title="Product Launch",
    description="Launch campaign for new product",
    platforms=["x", "reddit"],
    start_date=datetime.now(timezone.utc).isoformat(),
    end_date=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
    target_audience="Tech enthusiasts",
    goals=["Increase awareness", "Generate leads"]
)

plan_id = plan["plan"]["plan_id"]

# 调度帖子
agent.schedule_post(
    plan_id=plan_id,
    platform="x",
    content="Exciting new product launch! #Tech #Innovation"
)

# 执行每日计划
result = agent.execute_daily_plan()
print(f"Published: {result['successful']}/{result['total_posts']}")
```

### 2. 使用浏览器自动化发帖

```python
from Agent.promotion_agent import PromotionAgent
import os

agent = PromotionAgent()

# 启用浏览器自动化（显示浏览器窗口）
agent.enable_browser_automation(headless=False, slow_mo=500)

# 登录到平台
agent.login_to_platform("x", os.getenv("X_USERNAME"), os.getenv("X_PASSWORD"))

# 创建并调度帖子
plan = agent.create_promotion_plan(
    title="Browser Campaign",
    description="Campaign using browser automation",
    platforms=["x"],
    start_date=datetime.now(timezone.utc).isoformat(),
    end_date=datetime.now(timezone.utc).isoformat()
)

schedule_result = agent.schedule_post(
    plan_id=plan["plan"]["plan_id"],
    platform="x",
    content="Posting via browser automation!"
)

# 使用浏览器发布（如遇CAPTCHA会等待人工处理）
agent.publish_post_with_browser(schedule_result["post_id"])

# 保存会话以便下次使用
agent.save_browser_session("my_x_session")
```

### 3. 人工审核工作流

```python
# 提交审核
agent.submit_for_review(post_id=post_id, reviewer_id="manager_001")

# 查看审核队列
queue = agent.get_review_queue(status_filter="pending_review")
print(f"Pending reviews: {queue['statistics']['pending']}")

# 批准帖子
agent.review_post(
    post_id=post_id,
    reviewer_id="manager_001",
    decision="approved",
    notes="Content looks good"
)

# 或者批量批准
agent.bulk_approve_posts(
    post_ids=[post_id_1, post_id_2, post_id_3],
    reviewer_id="senior_manager",
    notes="Batch approved"
)
```

### 4. 内容优化

```python
# 为 X 优化内容（自动截断并添加标签）
optimized = agent.content_optimizer.optimize_for_x(
    content="Very long content here...",
    category="tech"
)

# 为 Reddit 优化内容
optimized = agent.content_optimizer.optimize_for_reddit(
    title="My Title",
    body="Content body...",
    subreddit="technology"
)

# 生成内容变体
variations = agent.generate_content_variations(
    base_content="Base message",
    count=3
)
```

### 5. 查看结果和审计日志

```python
# 获取宣传结果
results = agent.get_promotion_results(plan_id=plan_id)
print(f"Total posts: {results['summary']['total_posts']}")
print(f"Engagement: {results['summary']['total_metrics']}")

# 查看审计日志
audit = agent.get_audit_log(post_id=post_id)
for entry in audit["audit_log"]:
    print(f"[{entry['timestamp']}] {entry['action']} by {entry['user_id']}")

# 查看干预历史
summary = agent.get_intervention_summary(post_id=post_id)
print(f"Total interventions: {summary['summary']['total_interventions']}")
```

## 配置

### 环境变量

```bash
# X (Twitter) API 凭据（如果使用 API 方式）
export X_API_KEY="your_api_key"
export X_API_SECRET="your_api_secret"
export X_ACCESS_TOKEN="your_access_token"
export X_ACCESS_TOKEN_SECRET="your_access_token_secret"
export X_BEARER_TOKEN="your_bearer_token"

# X 浏览器自动化凭据
export X_USERNAME="your_username"
export X_PASSWORD="your_password"

# Reddit API 凭据
export REDDIT_CLIENT_ID="your_client_id"
export REDDIT_CLIENT_SECRET="your_client_secret"
export REDDIT_USER_AGENT="PromotionAgent/1.0"
export REDDIT_USERNAME="your_username"
export REDDIT_PASSWORD="your_password"
```

### 配置文件

复制 `promotion_config.example.json` 并填入你的配置：

```bash
cp Agent/promotion_config.example.json promotion_config.json
```

## 运行示例

```bash
# 基本使用示例
python Agent/example_promotion_usage.py

# 浏览器自动化示例
python Agent/example_browser_automation.py
```

## 运行测试

```bash
# 运行所有测试
python -m pytest Agent/test_promotion_agent.py Agent/test_browser_automation.py -v

# 只运行宣传 Agent 测试
python -m pytest Agent/test_promotion_agent.py -v

# 只运行浏览器自动化测试
python -m pytest Agent/test_browser_automation.py -v
```

## 架构说明

### 主要组件

```
PromotionAgent
├── ContentOptimizer          # 内容优化器
├── BrowserAutomationManager  # 浏览器自动化管理器（可选）
│   └── BotDetectionHandler   # 机器人检测处理器
├── PromotionPlan             # 宣传计划模型
└── RedditCommunityRule       # Reddit 社区规则
```

### 文件结构

```
Agent/
├── promotion_agent.py              # 主宣传 Agent
├── browser_automation.py           # 浏览器自动化模块
├── test_promotion_agent.py         # 宣传 Agent 测试
├── test_browser_automation.py      # 浏览器自动化测试
├── example_promotion_usage.py      # 基本使用示例
├── example_browser_automation.py   # 浏览器自动化示例
└── promotion_config.example.json   # 配置示例
```

## 重要注意事项

### 安全
- 不要将 API 密钥或密码硬编码在代码中
- 使用环境变量或安全的配置管理
- 定期轮换凭据

### 合规性
- 遵守各平台的服务条款
- 尊重 subreddit 的社区规则
- 避免过度频繁的发帖（可能被标记为垃圾邮件）

### 浏览器自动化
- 首次使用需要手动登录以建立会话
- CAPTCHA 出现时系统会暂停等待人工处理
- 建议保存会话以避免重复登录
- 使用 `headless=False` 便于观察和调试

### Fail-Closed 原则
- LLM 调用、网络请求、插件装配失败时，必须显式抛出结构化异常
- 禁止返回 None/{} /空字符串冒充成功
- 所有操作都有完整的审计日志追踪

## 故障排除

### Playwright 未安装
```bash
pip install playwright
playwright install
```

### 登录失败
- 检查凭据是否正确
- 尝试手动登录确认账号状态
- 检查是否有两步验证需要处理

### CAPTCHA 超时
- 增加等待时间（默认10分钟）
- 确保在浏览器窗口中完成验证
- 检查截图了解当前状态

### 发帖失败
- 检查内容是否符合平台规则
- 验证 subreddit 是否允许该类型帖子
- 查看审计日志了解详细错误信息

## 许可证

本项目遵循与主项目相同的许可证。
