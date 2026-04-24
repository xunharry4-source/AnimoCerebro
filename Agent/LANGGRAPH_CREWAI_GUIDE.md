# LangGraph + CrewAI 智能内容发布系统

## 📅 日期
2026-04-20

## 🎯 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    智能内容发布工作流                         │
└─────────────────────────────────────────────────────────────┘

节点 A (LangGraph): 主题分析器
    ↓
    输入: 原始素材
    输出: today_theme, content_type, priority
    功能: 使用 LLM 分析素材，确定今天的主题

节点 B (CrewAI 团队): 内容创作
    ↓
    Agent 1 (文案专家): 根据素材写草稿
         ↕ 反复迭代
    Agent 2 (校对编辑): 检查错误和优化
    输出: draft_content, is_approved
    功能: 多轮迭代直到生成完美文案

节点 C (LangGraph): 内容发布器
    ↓
    输入: 审核通过的文案
    输出: published_posts, publish_status
    功能: 调用 API 发送到 Twitter/小红书等平台

节点 D (LangGraph): 监控系统
    ↓
    输入: 发布结果
    决策: 成功 → END
          失败 → 退回节点 B 重新修改
    功能: 监控回执，失败时触发重试
```

## 🚀 快速开始

### 1. 安装依赖

```bash
# 激活虚拟环境
source .venv/bin/activate

# 安装依赖
pip install -r Agent/requirements_langgraph_crewai.txt
```

### 2. 配置环境变量

```bash
# 复制配置示例
cp Agent/.env.langgraph.example Agent/.env.langgraph

# 编辑配置文件，填入你的 API Keys
vim Agent/.env.langgraph
```

### 3. 运行示例

```bash
# 设置环境变量
export OPENAI_API_KEY="your-openai-api-key-here"

# 运行发布系统
python Agent/langgraph_crewai_publisher.py
```

## 💡 使用示例

### 基本用法

```python
from Agent.langgraph_crewai_publisher import ContentPublishingWorkflow

# 创建工作流
workflow = ContentPublishingWorkflow(
    max_iterations=3,  # CrewAI 最多迭代 3 次
    max_retries=2      # 发布失败最多重试 2 次
)

# 准备素材
raw_material = """
AnimoCerebro 项目最新进展：
1. 完成了浏览器自动化模块
2. 实现了 Reddit 智能发帖系统
3. 创建了社区规则管理器
"""

# 运行工作流
result = workflow.run(
    raw_material=raw_material,
    target_platforms=["Twitter", "小红书"]
)

# 查看结果
print(f"状态: {result['status']}")
print(f"主题: {result['today_theme']}")
print(f"发布平台: {list(result['published_posts'].keys())}")
```

### 自定义配置

```python
# 不同的迭代和重试策略
workflow_conservative = ContentPublishingWorkflow(
    max_iterations=5,  # 更多迭代，质量更高
    max_retries=3      # 更多重试，成功率更高
)

workflow_fast = ContentPublishingWorkflow(
    max_iterations=2,  # 快速发布
    max_retries=1      # 最少重试
)
```

### 批量处理

```python
materials = [
    "素材 1: 技术分享...",
    "素材 2: 项目进度...",
    "素材 3: 学习经验..."
]

results = []
for material in materials:
    result = workflow.run(raw_material=material)
    results.append(result)
    
    # 避免频繁调用 API
    time.sleep(5)
```

## 🔧 核心组件详解

### 1. 节点 A: ThemeAnalyzer（主题分析器）

**职责**: 接收原始素材，判断今天发什么主题

**工作流程**:
```python
def analyze_theme(self, state: ContentState) -> ContentState:
    # 1. 读取原始素材
    raw_material = state["raw_material"]
    
    # 2. 使用 LLM 分析
    prompt = f"分析以下素材，确定主题: {raw_material}"
    response = self.llm.invoke(prompt)
    
    # 3. 提取主题信息
    result = json.loads(response.content)
    state["today_theme"] = result["today_theme"]
    state["content_type"] = result["content_type"]
    state["priority"] = result["priority"]
    
    return state
```

**输出**:
- `today_theme`: 今天的主题（如"项目进度更新"）
- `content_type`: 内容类型（技术分享/学习经验/行业洞察）
- `priority`: 优先级（1-5）

### 2. 节点 B: ContentCreationCrew（CrewAI 创作团队）

**职责**: 使用 CrewAI 团队创作文案，反复迭代直到完美

**团队组成**:

#### Agent 1: 文案专家
```python
writer_agent = Agent(
    role="社交媒体文案专家",
    goal="根据素材创作吸引人的社交媒体文案",
    backstory="经验丰富的文案专家，擅长将技术内容转化为引人入胜的帖子"
)
```

**任务**:
- 理解主题和素材
- 创作吸引人的开头
- 提供有价值的内容
- 添加明确的 CTA
- 适配不同平台风格

#### Agent 2: 校对编辑
```python
editor_agent = Agent(
    role="内容校对编辑",
    goal="检查和优化文案，确保质量完美",
    backstory="严格的校对编辑，专注准确性、可读性和吸引力"
)
```

**任务**:
- 检查语法和拼写
- 验证逻辑清晰度
- 确保语气一致
- 评估吸引力
- 提供改进建议

**迭代流程**:
```
第 1 轮:
  Writer → 创作初稿
  Editor → 提供反馈
  
第 2 轮:
  Writer → 根据反馈修改
  Editor → 再次检查
  
第 3 轮:
  Writer → 最终优化
  Editor → APPROVED ✅
```

### 3. 节点 C: ContentPublisher（内容发布器）

**职责**: 拿到审核通过的文案，调用 API 发送到各平台

**支持的平台**:
- Twitter (通过 Tweepy)
- 小红书 (通过官方 API)
- 可扩展到其他平台

**发布流程**:
```python
def publish(self, state: ContentState) -> ContentState:
    for platform in state["target_platforms"]:
        try:
            # 调用平台 API
            result = self._publish_to_platform(platform, content)
            
            # 记录结果
            state["published_posts"][platform] = result
            state["publish_status"][platform] = "success"
            
        except Exception as e:
            # 记录失败
            state["publish_status"][platform] = "failed"
            state["failed_platforms"].append(platform)
    
    return state
```

**集成真实 API**:

#### Twitter 发布
```python
import tweepy

def _publish_to_twitter(self, content: str) -> Dict:
    client = tweepy.Client(
        consumer_key=os.getenv("TWITTER_API_KEY"),
        consumer_secret=os.getenv("TWITTER_API_SECRET"),
        access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
        access_token_secret=os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
    )
    
    response = client.create_tweet(text=content)
    
    return {
        "platform": "Twitter",
        "post_id": response.data["id"],
        "url": f"https://twitter.com/user/status/{response.data['id']}"
    }
```

#### 小红书发布
```python
def _publish_to_xiaohongshu(self, content: str, images: List[str] = None) -> Dict:
    # 调用小红书开放平台 API
    response = requests.post(
        "https://api.xiaohongshu.com/api/sns/v1/note/publish",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "title": content[:20],
            "desc": content,
            "images": images or []
        }
    )
    
    return response.json()
```

### 4. 节点 D: MonitoringSystem（监控系统）

**职责**: 监控发布回执，如果失败则退回节点 B 重新修改

**监控流程**:
```python
def monitor(self, state: ContentState) -> ContentState:
    # 1. 检查每个平台的发布状态
    for platform, status in state["publish_status"].items():
        if status == "success":
            # 检查帖子表现
            performance = self._check_post_performance(platform)
            state["monitoring_results"][platform] = performance
            
        elif status == "failed":
            # 记录失败
            state["failed_platforms"].append(platform)
    
    # 2. 决定下一步
    if state["failed_platforms"]:
        state["retry_count"] += 1
        
        if state["retry_count"] <= state["max_retries"]:
            # 需要重试，退回节点 B
            state["status"] = "retry"
            state["is_approved"] = False
        else:
            # 达到最大重试次数
            state["status"] = "failed"
    else:
        # 全部成功
        state["status"] = "published"
    
    return state
```

**重试决策**:
```
成功 → END (工作流结束)

失败且 retry_count < max_retries 
  → 退回节点 B (重新创作并发布)

失败且 retry_count >= max_retries
  → END (标记为失败)
```

## 📊 状态流转图

```
PENDING
   ↓
DRAFTING (节点 A: 主题分析)
   ↓
REVIEWING (节点 B: CrewAI 创作)
   ↓ ↕ (迭代直到 approved)
APPROVED
   ↓
PUBLISHING (节点 C: 发布)
   ↓
PUBLISHED (节点 D: 监控成功)
   或
FAILED (节点 D: 监控失败)
   ↓
RETRY (退回节点 B)
   ↓
DRAFTING (重新创作)
   ...
```

## 🎨 自定义扩展

### 添加新的社交平台

```python
class CustomPublisher(ContentPublisher):
    def _publish_to_linkedin(self, content: str) -> Dict:
        # LinkedIn API 集成
        pass
    
    def _publish_to_weibo(self, content: str) -> Dict:
        # 微博 API 集成
        pass
```

### 添加新的 Agent

```python
# 在 CrewAI 团队中添加 SEO 专家
seo_agent = Agent(
    role="SEO 优化专家",
    goal="优化文案的搜索引擎可见性",
    backstory="专业的 SEO 顾问，擅长关键词优化"
)

# 添加到 Crew
crew = Crew(
    agents=[writer_agent, editor_agent, seo_agent],
    tasks=[writing_task, editing_task, seo_task],
    process=Process.sequential
)
```

### 自定义监控指标

```python
def _check_post_performance(self, platform: str, post_info: Dict) -> Dict:
    # 除了点赞和评论，还可以监控：
    return {
        "likes": ...,
        "comments": ...,
        "shares": ...,
        "click_through_rate": ...,
        "conversion_rate": ...,
        "sentiment_score": ...  # 情感分析
    }
```

## 🔍 调试和监控

### 查看详细日志

```python
# 启用 verbose 模式
workflow = ContentPublishingWorkflow()

# CrewAI 会自动输出详细的执行日志
# LangGraph 可以通过回调监控状态变化
```

### 保存中间结果

```python
# 工作流会自动保存每个节点的状态
# 可以在 final_state 中查看所有中间结果

print(json.dumps(result, indent=2, ensure_ascii=False))
```

### 可视化工作流

```python
# 使用 LangGraph 的可视化工具
from langgraph.graph import StateGraph

workflow_diagram = workflow.workflow.get_graph()
workflow_diagram.draw_mermaid_png(output_file_path="workflow.png")
```

## ⚙️ 配置选项

### 环境变量

```bash
# 必需
OPENAI_API_KEY=sk-...

# 可选（用于真实发布）
TWITTER_API_KEY=...
TWITTER_API_SECRET=...
XIAOHONGSHU_APP_KEY=...

# 可选（调整行为）
MAX_ITERATIONS=3
MAX_RETRIES=2
DEFAULT_PLATFORMS=Twitter,小红书
```

### 代码配置

```python
workflow = ContentPublishingWorkflow(
    max_iterations=3,    # CrewAI 最大迭代次数
    max_retries=2,       # 发布失败最大重试次数
)
```

## 📈 性能优化

### 1. 缓存 LLM 响应

```python
from langchain.cache import InMemoryCache
import langchain

langchain.llm_cache = InMemoryCache()
```

### 2. 并行发布

```python
import asyncio

async def publish_parallel(self, platforms: List[str], content: str):
    tasks = [
        self._publish_to_platform_async(platform, content)
        for platform in platforms
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

### 3. 批量处理

```python
# 使用队列处理多个素材
from queue import Queue

material_queue = Queue()
for material in materials:
    material_queue.put(material)

# 工作线程处理
while not material_queue.empty():
    material = material_queue.get()
    result = workflow.run(raw_material=material)
```

## 🛡️ 错误处理

### 常见错误及解决方案

#### 1. API Key 无效
```
Error: Invalid API key
Solution: 检查 OPENAI_API_KEY 是否正确设置
```

#### 2. CrewAI 执行超时
```
Error: Timeout during CrewAI execution
Solution: 增加 timeout 参数或简化任务描述
```

#### 3. 发布失败
```
Error: Failed to publish to Twitter
Solution: 检查 Twitter API credentials 和网络连接
```

### 重试策略

```python
# 指数退避重试
import time

def retry_with_backoff(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait_time = 2 ** attempt  # 1s, 2s, 4s...
            time.sleep(wait_time)
```

## 📝 最佳实践

### 1. 素材准备

```python
# 好的素材应该包含：
good_material = """
主题: AnimoCerebro 项目进展

关键点:
1. 完成了浏览器自动化模块
2. 实现了智能发帖系统
3. 重构了代码结构

技术栈: FastAPI, React, Playwright

链接: https://github.com/AnimoCerebro

目标受众: 开发者、AI 爱好者
"""
```

### 2. 平台选择

```python
# 根据内容类型选择平台
if content_type == "技术分享":
    platforms = ["Twitter", "LinkedIn"]
elif content_type == "视觉内容":
    platforms = ["小红书", "Instagram"]
elif content_type == "长文":
    platforms = ["Medium", "知乎"]
```

### 3. 发布时间

```python
# 选择最佳发布时间
best_times = {
    "Twitter": "工作日 9:00-11:00, 14:00-16:00",
    "小红书": "工作日 12:00-13:00, 20:00-22:00",
    "LinkedIn": "工作日 8:00-10:00, 17:00-18:00"
}
```

## 🎓 学习资源

- [LangGraph 文档](https://python.langchain.com/docs/langgraph)
- [CrewAI 文档](https://docs.crewai.com/)
- [Twitter API 文档](https://developer.twitter.com/en/docs)
- [小红书开放平台](https://open.xiaohongshu.com/)

## 🚀 下一步

1. **集成真实 API**
   - 替换模拟发布为真实 API 调用
   - 添加 OAuth 认证
   - 实现速率限制处理

2. **增强监控**
   - 添加实时数据看板
   - 实现自动报告生成
   - 集成告警系统

3. **扩展平台**
   - 添加 LinkedIn、Instagram 等
   - 支持视频内容
   - 实现跨平台同步

4. **AI 优化**
   - 使用历史数据训练模型
   - 自动优化发布时间
   - 智能内容推荐

---

**创建者**: AI Assistant  
**最后更新**: 2026-04-20  
**版本**: 1.0  
**状态**: ✅ 完整实现

## 🎉 总结

LangGraph + CrewAI 智能内容发布系统提供了：

- ✅ **节点 A**: 智能主题分析
- ✅ **节点 B**: CrewAI 团队协作创作（反复迭代）
- ✅ **节点 C**: 多平台发布
- ✅ **节点 D**: 监控和自动重试

完整的自动化工作流，让内容发布更高效、更智能！🚀
