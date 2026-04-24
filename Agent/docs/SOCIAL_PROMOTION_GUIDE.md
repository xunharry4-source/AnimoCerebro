# 社交媒体宣传 Agent

通过浏览器自动化在 X (Twitter) 和 Reddit 上自动发帖宣传的 Agent。

## 功能特性

- ✅ **制定宣传计划**: 创建多平台、多社区的宣传活动计划
- ✅ **浏览器自动化**: 使用 Playwright 模拟真实用户操作，无需 API
- ✅ **智能内容验证**: 根据不同社区要求自动验证内容合规性
- ✅ **自动发帖**: 支持 X 和 Reddit 平台自动发布内容
- ✅ **定时发布**: 支持立即发布或定时调度发布
- ✅ **结果追踪**: 查看宣传效果和参与度指标
- ✅ **社区规则适配**: 根据不同 subreddit 的要求调整内容

## 安装依赖

```bash
pip install playwright
python3 -m playwright install chromium
```

## 快速开始

### 1. 启动 Agent

```bash
cd Agent
chmod +x start_social_promotion.sh
./start_social_promotion.sh
```

### 2. 基本使用示例

```python
import asyncio
from datetime import datetime, timezone, timedelta
from Agent.social_promotion_agent import social_promotion_agent, PostContent

async def main():
    # 初始化浏览器
    await social_promotion_agent.initialize_browser(headless=False)
    
    # 登录 X
    await social_promotion_agent.login_to_x("your_username", "your_password")
    
    # 登录 Reddit
    await social_promotion_agent.login_to_reddit("your_username", "your_password")
    
    # 创建宣传计划
    plan = social_promotion_agent.create_promotion_plan(
        campaign_name="Product Launch",
        platforms=["x", "reddit"],
        target_communities=["technology", "programming"],
        content_templates=[
            {
                "title": "New Product",
                "content": "Check out our new product! #tech #innovation",
                "platform": "x"
            }
        ],
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc) + timedelta(days=7)
    )
    
    plan_id = plan["plan_id"]
    
    # 发布到 X
    x_post = PostContent(
        content="🚀 Excited to launch our new product! Amazing features and great performance. #AI #Tech #Innovation",
        media_files=[]
    )
    await social_promotion_agent.post_to_x(x_post, plan_id)
    
    # 发布到 Reddit
    await social_promotion_agent.post_to_reddit(
        title="Launched a New AI Product",
        content="Hi everyone! We just launched our new AI product with amazing features...",
        subreddit="technology",
        flair="Discussion",
        plan_id=plan_id
    )
    
    # 查看结果
    results = social_promotion_agent.get_promotion_results(plan_id=plan_id)
    print(f"Total posts: {results['total_posts']}")
    print(f"Successful: {results['successful_posts']}")
    
    # 关闭浏览器
    await social_promotion_agent.close_browser()

if __name__ == "__main__":
    asyncio.run(main())
```

## 核心功能

### 1. 创建宣传计划

```python
plan_result = social_promotion_agent.create_promotion_plan(
    campaign_name="My Campaign",           # 活动名称
    platforms=["x", "reddit"],             # 目标平台
    target_communities=["technology", "programming"],  # 目标社区
    content_templates=[...],               # 内容模板
    start_date=datetime.now(timezone.utc), # 开始时间
    end_date=datetime.now(timezone.utc) + timedelta(days=7),  # 结束时间
    frequency="daily",                     # 发布频率
    budget=100.0                          # 预算（可选）
)
```

### 2. 分析社区要求

```python
# 获取特定社区的要求和建议
requirements = social_promotion_agent.analyze_community_requirements("technology")
print(requirements["requirements"])  # 社区规则
print(requirements["recommendations"])  # 内容建议
```

### 3. 验证内容合规性

```python
content = PostContent(
    title="My Post Title",
    content="Post content with #tags",
    tags=["tech", "innovation"]
)

validation = social_promotion_agent.validate_content_for_community(content, "technology")
if validation["valid"]:
    print("Content is valid!")
else:
    print(f"Issues: {validation['issues']}")
```

### 4. 登录平台

```python
# 登录 X
await social_promotion_agent.login_to_x("username", "password")

# 登录 Reddit
await social_promotion_agent.login_to_reddit("username", "password")
```

### 5. 发布内容

#### 发布到 X

```python
post = PostContent(
    content="Your tweet content here #hashtags",
    media_files=["/path/to/image.jpg"]  # 可选
)
result = await social_promotion_agent.post_to_x(post, plan_id="plan_xxx")
```

#### 发布到 Reddit

```python
result = await social_promotion_agent.post_to_reddit(
    title="Your post title",
    content="Your post content with proper formatting",
    subreddit="technology",
    flair="Discussion",  # 可选
    plan_id="plan_xxx"
)
```

### 6. 批量调度发布

```python
posts = [
    {
        "platform": "x",
        "content": "Tweet content",
        "schedule_time": None  # None = 立即发布
    },
    {
        "platform": "reddit",
        "title": "Reddit title",
        "content": "Reddit content",
        "subreddit": "technology",
        "flair": "Discussion",
        "schedule_time": None
    }
]

result = await social_promotion_agent.schedule_posts(plan_id, posts)
```

### 7. 查看宣传结果

```python
# 获取所有结果
all_results = social_promotion_agent.get_promotion_results()

# 按计划在获取
plan_results = social_promotion_agent.get_promotion_results(plan_id="plan_xxx")

# 按平台过滤
x_results = social_promotion_agent.get_promotion_results(platform="x")

# 按日期范围过滤
from datetime import datetime, timezone
start = datetime(2024, 1, 1, tzinfo=timezone.utc)
end = datetime(2024, 12, 31, tzinfo=timezone.utc)
date_results = social_promotion_agent.get_promotion_results(date_range=(start, end))

# 获取计划详情
plan_details = social_promotion_agent.get_plan_details("plan_xxx")
```

## 支持的社区及要求

Agent 内置了以下社区的规则：

### Technology
- 最大标题长度: 300 字符
- 最大内容长度: 10000 字符
- 必需标签: tech, innovation
- 禁用词: spam, scam
- 发布限制: 每天 3 帖
- 内容类型: 信息性

### Science
- 最大标题长度: 300 字符
- 最大内容长度: 15000 字符
- 必需标签: science, research
- 禁用词: fake, pseudoscience
- 发布限制: 每天 2 帖
- 内容类型: 教育性

### Programming
- 最大标题长度: 300 字符
- 最大内容长度: 10000 字符
- 必需标签: code, programming
- 禁用词: hire, job
- 发布限制: 每天 5 帖
- 内容类型: 技术性

### General
- 最大标题长度: 300 字符
- 最大内容长度: 10000 字符
- 发布限制: 每天 10 帖
- 内容类型: 任意

## 数据存储

所有宣传计划和发帖结果会自动保存到：
```
testdata/promotion_data/
├── promotion_plans.json
└── post_results.json
```

数据会在每次操作后自动保存，重启后可继续查看历史记录。

## 运行测试

```bash
cd Agent
python3 test_social_promotion.py
```

## 注意事项

1. **浏览器模式**: 
   - `headless=False`: 显示浏览器窗口，可以看到自动化过程
   - `headless=True`: 后台运行，不可见

2. **登录状态**: 
   - 首次使用需要手动登录
   - 登录状态会保存在浏览器上下文中
   - 建议先运行测试脚本熟悉流程

3. **反检测**:
   - Agent 使用真实的浏览器操作
   - 添加了适当的延迟模拟人类行为
   - 避免频繁发帖触发风控

4. **内容合规**:
   - 发帖前会自动验证内容是否符合社区规则
   - 建议先在测试社区练习
   - 遵守各平台的社区准则

5. **速率限制**:
   - 遵循各社区的发帖频率限制
   - 避免短时间内大量发帖
   - 建议在宣传计划中合理分配发布时间

## 扩展开发

### 添加新社区规则

在 `social_promotion_agent.py` 的 `_load_community_requirements()` 方法中添加：

```python
"new_community": CommunityRequirement(
    name="new_community",
    max_title_length=300,
    max_content_length=10000,
    required_tags=["tag1", "tag2"],
    forbidden_words=["bad1", "bad2"],
    posting_frequency_limit="5 posts per day",
    content_type="any",
    special_rules="Community specific rules"
)
```

### 自定义浏览器配置

```python
# 修改 BrowserAutomationManager 类中的配置
self.context = await self.browser.new_context(
    viewport={'width': 1920, 'height': 1080},
    user_agent='Custom User Agent',
    # 添加其他配置
)
```

## 故障排除

### 浏览器无法启动
```bash
# 重新安装 Playwright
pip uninstall playwright
pip install playwright
python3 -m playwright install chromium
```

### 登录失败
- 检查用户名和密码是否正确
- 可能需要处理验证码（手动完成）
- 检查网络连接

### 发帖失败
- 确认已成功登录
- 检查内容是否符合社区规则
- 查看错误日志了解具体原因

## 最佳实践

1. **内容策略**
   - 为不同平台定制内容
   - X: 简短精炼，带话题标签
   - Reddit: 详细有价值，参与讨论

2. **发布时机**
   - 选择目标受众活跃时段
   - 避免高峰期拥堵
   - 分散发布时间

3. **互动管理**
   - 定期查看评论和回复
   - 积极参与讨论
   - 建立社区关系

4. **效果追踪**
   - 定期检查宣传结果
   - 分析哪些内容效果好
   - 优化后续策略

## License

MIT License
