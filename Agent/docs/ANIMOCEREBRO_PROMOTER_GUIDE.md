# AnimoCerebro 宣传发帖系统 - 使用指南

## 📅 日期
2026-04-20

## 🎯 功能概述

AnimoCerebro Promoter 是一个智能宣传系统，可以：

1. **在 r/AnimoCerebro 发布项目进度**
   - 详细介绍项目特点
   - 展示最新进展
   - 技术栈说明

2. **在其他技术社区宣传**
   - r/Python - Python 技术实现
   - r/MachineLearning - AI/ML 角度
   - r/artificial - AI 系统架构
   - r/compsci - 计算机科学视角
   - r/programming - 编程实践
   - r/learnprogramming - 学习经验分享

3. **智能内容生成**
   - 基于社区规则自动生成合规内容
   - 针对不同社区定制内容风格
   - 自动检测并避免违规

4. **反复纠错机制**
   - 最多 3 次重试
   - 错误分析和修正
   - 成功率优化

## 🚀 快速开始

### 基本用法

```python
from Agent.animocerebro_promoter import AnimoCerebroPromoter
from Agent.community_rules_manager import CommunityRulesManager
from playwright.sync_api import sync_playwright

# 初始化
playwright = sync_playwright().start()
browser = playwright.chromium.launch(headless=False)
context = browser.new_context()
page = context.new_page()

# 先登录 Reddit
page.goto("https://www.reddit.com/login")
# ... 手动登录 ...

rules_manager = CommunityRulesManager()
promoter = AnimoCerebroPromoter(page, rules_manager)

# 1. 在 r/AnimoCerebro 发布项目进度
promoter.promote_in_own_community("AnimoCerebro")

# 2. 在多个技术社区宣传
communities = ["Python", "MachineLearning", "artificial"]
results = promoter.promote_in_tech_communities(communities)

# 查看结果
for community, success in results.items():
    status = "✅" if success else "❌"
    print(f"{status} r/{community}")

browser.close()
playwright.stop()
```

### 集成到测试脚本

```python
def test_animocerebro_promotion(self):
    """测试 AnimoCerebro 宣传发帖"""
    
    from Agent.animocerebro_promoter import AnimoCerebroPromoter
    
    # 创建宣传助手
    promoter = AnimoCerebroPromoter(self.page, self.rules_manager)
    
    # 在自有社区发布进度
    print("\n📢 在 r/AnimoCerebro 发布项目进度...")
    own_success = promoter.promote_in_own_community("AnimoCerebro")
    
    # 在技术社区宣传
    print("\n🎯 在技术社区宣传...")
    tech_communities = ["Python", "learnprogramming"]
    tech_results = promoter.promote_in_tech_communities(tech_communities)
    
    # 汇总结果
    all_success = own_success and all(tech_results.values())
    
    if all_success:
        print("\n✅ AnimoCerebro 宣传发帖全部成功!")
    else:
        print("\n⚠️  部分发帖失败，请检查日志")
    
    return all_success
```

## 📝 内容策略

### 1. r/AnimoCerebro（自有社区）

**帖子类型**: 项目进度更新

**内容结构**:
```markdown
# AnimoCerebro 项目进展更新

## 📌 项目简介
- 项目名称和标语
- 核心描述

## ✨ 核心特点
1. 九问认知循环
2. 双插件系统
3. 外挂大脑
4. 真实性边界
5. MCP 协议集成
6. 记忆管理系统

## 🔧 技术栈
- 后端: FastAPI, Python, Kuzu, Faiss
- 前端: React, TypeScript, Vite
- AI: DSPy, PydanticAI, OpenAI, Google GenAI
- 自动化: Playwright, Stealth Chrome

## 📈 最新进展
- ✅ Stealth Chrome 自动化
- ✅ 社交媒体自动发帖
- ✅ 社区规则管理
- ✅ 反复纠错机制
- ✅ 浏览器指纹隐藏

## 🎯 项目目标
- 提升思考效率
- 知识管理
- 任务自动化
- 深度洞察

## 💡 核心理念
1. 九问认知循环
2. 双插件系统
3. 真实性边界
4. 人机协作

## 🔗 相关链接
- GitHub
- 文档

## 🙏 欢迎贡献
- 代码贡献
- 文档改进
- 问题反馈
- 功能建议
```

**Flair**: `Project Update`

### 2. r/Python（Python 社区）

**帖子类型**: 技术分享

**重点**:
- Python 技术栈详解
- FastAPI 最佳实践
- Playwright 优化技巧
- 代码示例
- 寻求 Python 开发者反馈

**Flair**: `Showcase`

### 3. r/MachineLearning（机器学习社区）

**帖子类型**: 研究项目

**重点**:
- LLM 集成架构
- 认知增强方法
- 知识表示策略
- 研究方向
- 学术讨论

**Flair**: `Project`

### 4. r/artificial（AI 社区）

**帖子类型**: AI 系统介绍

**重点**:
- AI 增强认知概念
- 人机协作模式
- 伦理考量
- 系统设计哲学
- 未来展望

**Flair**: `Discussion`

### 5. r/compsci（计算机科学社区）

**帖子类型**: 系统架构案例

**重点**:
- 系统架构设计
- 技术挑战解决
- 性能优化
- 教育价值
- 工程实践

**Flair**: `Systems`

### 6. r/programming（编程社区）

**帖子类型**: 项目开发分享

**重点**:
- 完整技术栈
- 酷炫功能演示
- 开发动机
- 开源邀请
- 代码审查请求

**Flair**: `Project`

### 7. r/learnprogramming（学习编程社区）

**帖子类型**: 学习经验分享

**重点**:
- 学习历程
- 技术收获
- 遇到的挑战
- 解决方案
- 向社区请教问题

**Flair**: `Question`

## 🔧 自定义内容

如果需要使用完全自定义的内容：

```python
from Agent.reddit_smart_poster import RedditSmartPoster

poster = RedditSmartPoster(page, rules_manager)

# 发布自定义内容
success = poster.post_custom_content(
    subreddit="Python",
    title="My Custom Title",
    content="My custom content here...",
    flair="Discussion",
    max_retries=3
)
```

## 📊 工作流程

```
开始
  ↓
📋 检查社区规则
  ├─ 本地缓存存在？
  │   ├─ Yes → 使用缓存
  │   └─ No ↓
  ├─ 从网页下载规则
  ├─ 保存到本地
  └─ 验证内容合规性
  ↓
📝 生成针对性内容
  ├─ r/AnimoCerebro → 项目进度
  ├─ r/Python → 技术实现
  ├─ r/MachineLearning → AI 研究
  ├─ r/artificial → AI 系统
  ├─ r/compsci → 系统架构
  ├─ r/programming → 开发分享
  └─ r/learnprogramming → 学习经验
  ↓
🔄 重试循环 (最多3次)
  ├─ 填写表单
  ├─ 选择 Flair
  ├─ 提交帖子
  ├─ 检查结果
  │   ├─ Success → ✅ 完成
  │   └─ Fail ↓
  ├─ 分析错误
  ├─ 应用修正
  └─ 下次尝试
  ↓
结束
```

## 🎨 内容示例

### r/Python 帖子示例

```markdown
大家好，

我想分享一个最近在用 Python 开发的项目：**AnimoCerebro**（外挂大脑）。

## 🐍 Python 技术栈

项目主要使用以下 Python 技术：

- **FastAPI** - 高性能异步 Web 框架
- **Playwright** - 浏览器自动化（实现了 Stealth 模式）
- **Kuzu** - 嵌入式图数据库
- **Faiss** - 向量相似度搜索
- **DSPy & PydanticAI** - LLM 应用开发框架

## 💡 技术亮点

### 1. Stealth Chrome 自动化
```python
# 绕过检测的浏览器自动化
context = playwright.chromium.launch_persistent_context(
    user_data_dir="./chrome_profile",
    executable_path="/path/to/chrome",
    args=["--disable-blink-features=AutomationControlled"]
)
```

### 2. 智能社区规则管理
自动下载和解析 Reddit 社区规则，确保发帖内容合规。

## 🔗 开源地址

GitHub: https://github.com/AnimoCerebro

欢迎 Python 开发者们交流和建议！
```

### r/MachineLearning 帖子示例

```markdown
Hi ML community,

I'd like to share a project that combines LLMs with cognitive science: **AnimoCerebro**.

## 🧠 Core Concept

AnimoCerebro implements a "Nine Questions Cognitive Loop" - a structured thinking framework enhanced by AI.

## 🛠️ Technical Implementation

### LLM Integration
- **DSPy** for prompt optimization
- **PydanticAI** for structured outputs
- **Multiple providers**: OpenAI, Google GenAI

### Memory & Knowledge
- **Faiss** for vector search
- **Kuzu Graph DB** for knowledge representation
- **Sentence Transformers** for embeddings

## 🎯 Research Questions

- How can LLMs augment human cognition?
- What structures improve AI-human collaboration?
- How to maintain truthfulness in AI systems?

Would love feedback from the ML community!
```

## ⚙️ 配置选项

### 推荐的技术社区列表

```python
recommended_communities = {
    "high_priority": [
        "Python",              # Python 开发者
        "MachineLearning",     # ML 研究者
        "artificial",          # AI 爱好者
    ],
    "medium_priority": [
        "compsci",             # 计算机科学家
        "programming",         # 程序员
        "learnprogramming",    # 学习者
    ],
    "low_priority": [
        "opensource",          # 开源社区
        "coding",              # 编码讨论
        "webdev",              # Web 开发
    ]
}
```

### 发帖间隔建议

```python
# 避免频繁发帖被识别为 spam
posting_intervals = {
    "same_community": 3600,      # 同一社区至少间隔 1 小时
    "different_community": 300,  # 不同社区至少间隔 5 分钟
    "daily_limit": 5,            # 每天最多 5 个社区
}
```

## 🛡️ 安全和合规

### 1. 规则遵守

- ✅ 发帖前自动检查社区规则
- ✅ 内容符合社区要求
- ✅ 选择合适的 Flair
- ✅ 避免自我推广限制

### 2. 透明度

- ✅ 明确说明是 AnimoCerebro 项目
- ✅ 提供 GitHub 链接
- ✅ 欢迎反馈和贡献
- ✅ 不伪装成普通用户

### 3. 频率控制

- ✅ 不在短时间内大量发帖
- ✅ 尊重每个社区的规则
- ✅ 避免跨多个社区同时发帖
- ✅ 监控账号健康状况

## 📈 成功率优化

### 最佳实践

1. **选择合适的时间**
   - 工作日 10:00-14:00 EST
   - 避免周末和节假日
   - 考虑时区差异

2. **账号准备**
   - Karma > 100
   - 账号年龄 > 30 天
   - 无违规历史
   - 在社区有一定活跃度

3. **内容质量**
   - 提供有价值的信息
   - 格式清晰易读
   - 包含代码示例（技术社区）
   - 提出问题促进讨论

4. **互动参与**
   - 回复评论
   - 回答问题
   - 感谢反馈
   - 持续跟进

## 🔍 调试和监控

### 查看发帖结果

```python
# 检查截图
ls -lh screenshots/reddit_*.png

# 查看规则缓存
ls -lh Agent/community_rules_cache/

# 检查日志
cat Agent/social_automation_test.log
```

### 常见问题

**Q: 发帖被移除怎么办？**

A: 
1. 检查社区规则
2. 查看 AutoMod 消息
3. 联系版主了解原因
4. 修改内容后重试

**Q: 如何选择合适的 Flair？**

A:
1. 浏览社区热门帖子
2. 查看常用 Flair
3. 选择最相关的类别
4. 不确定时选择 "Discussion"

**Q: 发帖频率多少合适？**

A:
- 同一社区：每周不超过 1-2 次
- 不同社区：每天不超过 3-5 个
- 新账号：更保守的频率

## 📝 维护指南

### 更新项目信息

编辑 `animocerebro_promoter.py` 中的 `_load_project_info()` 方法：

```python
def _load_project_info(self) -> Dict:
    return {
        "name": "AnimoCerebro",
        "recent_progress": [
            "✅ 新功能 1",
            "✅ 新功能 2",
            # 添加新的进展
        ],
        # ... 其他信息
    }
```

### 添加新的社区支持

在 `_generate_tech_promo_post()` 中添加新的社区：

```python
elif community == "NewCommunity":
    return self._generate_new_community_post()
```

然后实现对应的方法：

```python
def _generate_new_community_post(self) -> Dict:
    title = "..."
    content = "..."
    return {"title": title, "content": content, "flair": "..."}
```

## 🎓 经验总结

### 成功经验

1. ✅ **针对性内容** - 不同社区不同风格
2. ✅ **规则优先** - 发帖前检查规则
3. ✅ **透明诚实** - 明确说明项目目的
4. ✅ **价值导向** - 提供有用信息
5. ✅ **持续互动** - 回复评论和问题

### 需要避免

1. ❌ **垃圾式发帖** - 不要大量重复发帖
2. ❌ **硬推销** - 避免明显的促销语言
3. ❌ **忽视规则** - 严格遵守社区规定
4. ❌ **虚假宣传** - 如实介绍项目
5. ❌ **忽略反馈** - 重视社区意见

---

**创建者**: AI Assistant  
**最后更新**: 2026-04-20  
**版本**: 1.0  
**状态**: ✅ 完整实现

## 🚀 立即开始

```bash
# 激活虚拟环境
source .venv/bin/activate

# 运行宣传测试
python -c "
from Agent.animocerebro_promoter import AnimoCerebroPromoter
from Agent.community_rules_manager import CommunityRulesManager
from playwright.sync_api import sync_playwright

# 初始化并运行
playwright = sync_playwright().start()
browser = playwright.chromium.launch(headless=False)
page = browser.new_page()

# 登录后运行
rules_manager = CommunityRulesManager()
promoter = AnimoCerebroPromoter(page, rules_manager)

# 在自有社区发布
promoter.promote_in_own_community('AnimoCerebro')

# 在技术社区宣传
promoter.promote_in_tech_communities(['Python', 'learnprogramming'])

browser.close()
playwright.stop()
"
```

---

**🎉 AnimoCerebro 宣传系统已就绪！**

核心特性：
- ✅ 针对 r/AnimoCerebro 的项目进度发布
- ✅ 针对 6+ 技术社区的定制化宣传
- ✅ 基于规则的合规内容生成
- ✅ 智能重试和纠错机制
- ✅ 完整的文档和示例
