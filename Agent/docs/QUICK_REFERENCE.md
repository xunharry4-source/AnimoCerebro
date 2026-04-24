# AnimoCerebro 宣传系统 - 快速参考

## 🚀 一键运行

```python
from Agent.animocerebro_promoter import AnimoCerebroPromoter
from Agent.community_rules_manager import CommunityRulesManager
from playwright.sync_api import sync_playwright

# 初始化
playwright = sync_playwright().start()
browser = playwright.chromium.launch(headless=False)
page = browser.new_page()
# ... 手动登录 Reddit ...

rules_manager = CommunityRulesManager()
promoter = AnimoCerebroPromoter(page, rules_manager)

# 1. 在 r/AnimoCerebro 发布项目进度
promoter.promote_in_own_community("AnimoCerebro")

# 2. 在技术社区宣传
promoter.promote_in_tech_communities(["Python", "MachineLearning", "learnprogramming"])

browser.close()
playwright.stop()
```

## 📋 支持的社区

| 社区 | 内容类型 | Flair | 优先级 |
|------|---------|-------|--------|
| r/AnimoCerebro | 项目进度 | Project Update | ⭐⭐⭐ |
| r/Python | 技术实现 | Showcase | ⭐⭐⭐ |
| r/MachineLearning | AI 研究 | Project | ⭐⭐⭐ |
| r/artificial | AI 系统 | Discussion | ⭐⭐ |
| r/compsci | 系统架构 | Systems | ⭐⭐ |
| r/programming | 开发分享 | Project | ⭐⭐ |
| r/learnprogramming | 学习经验 | Question | ⭐⭐ |

## 🎯 核心 API

### AnimoCerebroPromoter

```python
# 在自有社区发布
promoter.promote_in_own_community(subreddit="AnimoCerebro")

# 在技术社区宣传
results = promoter.promote_in_tech_communities(
    communities=["Python", "ML", ...]
)

# 返回: {"Python": True, "ML": False, ...}
```

### RedditSmartPoster

```python
# 自动内容发帖
poster.post_with_retry(subreddit="Python", max_retries=3)

# 自定义内容发帖
poster.post_custom_content(
    subreddit="Python",
    title="My Title",
    content="My Content",
    flair="Discussion",
    max_retries=3
)
```

## 📝 内容模板

### r/AnimoCerebro
- 项目简介
- 6 大核心特点
- 完整技术栈
- 最新进展
- 项目目标
- 核心理念
- 相关链接
- 贡献邀请

### r/Python
- Python 技术栈
- FastAPI + Playwright 示例
- 技术亮点
- 寻求反馈

### r/MachineLearning
- LLM 集成架构
- 认知增强方法
- 研究方向
- 学术讨论

### r/learnprogramming
- 学习历程
- 技术收获
- 遇到的挑战
- 向社区请教

## ⚙️ 配置

### 推荐社区列表
```python
communities = {
    "high": ["Python", "MachineLearning", "artificial"],
    "medium": ["compsci", "programming", "learnprogramming"],
    "low": ["opensource", "coding", "webdev"]
}
```

### 发帖间隔
```python
intervals = {
    "same_community": 3600,      # 1 小时
    "different_community": 300,  # 5 分钟
    "daily_limit": 5             # 每天最多 5 个
}
```

## 🛡️ 安全检查

发帖前自动检查：
- ✅ 社区规则是否存在
- ✅ 内容是否符合规则
- ✅ 是否包含禁止项
- ✅ Flair 是否合适

违规检测：
- 自我推广
- 外部链接
- 低质量内容
- 重复发帖
- 垃圾内容

## 🔄 重试机制

```
尝试 1/3 → 失败 → 分析错误 → 修正
尝试 2/3 → 失败 → 分析错误 → 修正  
尝试 3/3 → 成功/失败
```

错误类型：
- RULE_VIOLATION
- QUALITY_ISSUE
- AUTOMOD_REMOVAL
- SPAM_DETECTION
- ACCOUNT_AGE
- DUPLICATE_POST

## 📊 文件位置

```
Agent/
├── animocerebro_promoter.py          # 宣传助手 (742 行)
├── reddit_smart_poster.py            # Reddit 发帖器 (975 行)
├── community_rules_manager.py        # 规则管理器 (517 行)
├── community_rules_cache/            # 规则缓存
│   ├── Python.json
│   ├── MachineLearning.json
│   └── ...
├── ANIMOCEREBRO_PROMOTER_GUIDE.md    # 使用指南
├── ANIMOCEREBRO_PROMOTION_SUMMARY.md # 实现总结
└── QUICK_REFERENCE.md                # 本文件
```

## 💡 最佳实践

### DO ✅
- 发帖前阅读社区规则
- 提供有价值的信息
- 选择合适的 Flair
- 回复评论和问题
- 保持透明诚实
- 控制发帖频率

### DON'T ❌
- 不要 spam
- 不要硬推销
- 不要忽视规则
- 不要虚假宣传
- 不要忽略反馈
- 不要频繁发帖

## 🔍 调试

```bash
# 查看截图
ls -lh screenshots/reddit_*.png

# 查看规则缓存
ls -lh Agent/community_rules_cache/

# 查看日志
tail -f Agent/social_automation_test.log
```

## 📈 监控指标

- 发帖成功率
- 社区响应（upvotes, comments）
- GitHub stars 增长
- 新贡献者数量
- 社区反馈质量

## 🎯 目标

### 短期（1-2周）
- 在 r/AnimoCerebro 建立存在感
- 在 2-3 个技术社区获得关注
- 收集早期反馈

### 中期（1个月）
- 5+ 技术社区知名度
- 50+ GitHub stars
- 吸引早期贡献者

### 长期（3个月）
- AI 增强认知领域知名项目
- 200+ GitHub stars
- 活跃的贡献者社区

---

**版本**: 1.0  
**最后更新**: 2026-04-20  
**状态**: ✅ Ready to Use

🚀 **开始宣传 AnimoCerebro！**
