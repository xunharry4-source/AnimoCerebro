# AnimoCerebro 每周发帖计划系统 - 使用指南

## 📅 日期
2026-04-20

## 🎯 功能概述

每周发帖计划生成器可以：

1. ✅ **自动生成周一到周五的发帖计划**
2. ✅ **针对不同社区安排不同内容**
3. ✅ **检查历史发帖记录，防止重复**
4. ✅ **基于项目进展动态调整内容**
5. ✅ **导出为 JSON 或 Markdown 格式**

## 🚀 快速开始

### 基本用法

```python
from Agent.weekly_posting_planner import WeeklyPostingPlanner

# 创建计划生成器
planner = WeeklyPostingPlanner()

# 生成本周计划
plan = planner.generate_weekly_plan()

# 查看计划
import json
print(json.dumps(plan, indent=2, ensure_ascii=False))

# 导出为 Markdown
md_file = planner.save_markdown_plan(plan)
print(f"计划已保存: {md_file}")
```

### 指定周的开始日期

```python
from datetime import datetime

# 生成特定周的计刉
week_start = datetime(2026, 4, 20)  # 2026年4月20日（周一）
plan = planner.generate_weekly_plan(week_start)
```

## 📋 每周发帖策略

### 星期一：项目进度更新
- **主要社区**: r/AnimoCerebro
- **次要社区**: r/Python
- **内容类型**: Progress Update
- **最佳时间**: 10:00-12:00 EST
- **重点**: 本周焦点、最新成就、技术亮点

### 星期二：技术深度分享
- **主要社区**: r/MachineLearning
- **次要社区**: r/artificial
- **内容类型**: Technical Deep Dive
- **最佳时间**: 14:00-16:00 EST
- **重点**: LLM 集成、架构设计、研究成果

### 星期三：学习经验分享
- **主要社区**: r/learnprogramming
- **次要社区**: r/programming
- **内容类型**: Learning Experience
- **最佳时间**: 11:00-13:00 EST
- **重点**: 学习历程、挑战克服、建议分享

### 星期四：系统架构讨论
- **主要社区**: r/compsci
- **次要社区**: r/Python
- **内容类型**: Architecture Discussion
- **最佳时间**: 15:00-17:00 EST
- **重点**: 系统设计、技术选型、性能优化

### 星期五：周末预告和总结
- **主要社区**: r/AnimoCerebro
- **次要社区**: r/programming
- **内容类型**: Weekly Summary
- **最佳时间**: 16:00-18:00 EST
- **重点**: 本周回顾、社区互动、下周计划

## 🔍 重复检测机制

### 检测规则

系统会自动检查以下条件以防止重复：

1. **时间窗口**: 过去 7 天内的发帖记录
2. **社区匹配**: 同一 subreddit
3. **标题相似度**: 使用词集相似度算法（阈值 0.8）
4. **内容哈希**: MD5 哈希值完全匹配

### 工作原理

```python
def check_duplicate(subreddit, title, content_hash):
    # 获取过去 7 天的记录
    seven_days_ago = time.time() - (7 * 24 * 3600)
    
    for post in posting_history:
        if post["timestamp"] < seven_days_ago:
            continue
        
        # 检查同一社区
        if post["subreddit"] == subreddit:
            # 检查相似标题
            if is_similar_title(post["title"], title):
                return True
            
            # 检查相同内容
            if post["content_hash"] == content_hash:
                return True
    
    return False
```

### 自动备选方案

如果检测到重复，系统会：
1. 标记帖子为 "⚠️ 检测到相似内容"
2. 生成备选内容（添加时间戳和变化）
3. 在计划中标记注意事项

## 📊 数据结构

### 计划格式（JSON）

```json
{
  "week_start": "2026-04-20",
  "week_end": "2026-04-24",
  "generated_at": "2026-04-20 10:00:00",
  "schedule": {
    "Monday": {
      "date": "2026-04-20",
      "date_cn": "星期一",
      "theme": "项目进度更新",
      "primary_post": {
        "title": "🚀 AnimoCerebro Weekly Progress Update - 2026-04-20",
        "content": "...",
        "content_hash": "abc123...",
        "flair": "Project Update",
        "estimated_length": 1500,
        "posting_time": "10:00-12:00 EST"
      },
      "secondary_posts": [
        {
          "community": "Python",
          "suggested_time": "14:00-16:00 EST",
          "note": "可选，根据主要帖子反馈决定是否发布"
        }
      ],
      "best_posting_time": "10:00-12:00 EST (Monday morning)",
      "content_focus": "项目进展、新功能、成就展示"
    }
  }
}
```

### 发帖历史格式

```json
{
  "posts": [
    {
      "subreddit": "AnimoCerebro",
      "title": "Weekly Progress Update",
      "content_hash": "abc123...",
      "timestamp": 1713580800,
      "date": "2026-04-20",
      "success": true
    }
  ]
}
```

## 💡 高级用法

### 1. 手动记录发帖

```python
# 发帖后记录
planner.record_post(
    subreddit="Python",
    title="My Post Title",
    content="Post content here...",
    success=True
)
```

### 2. 检查特定内容是否重复

```python
is_dup = planner.check_duplicate(
    subreddit="Python",
    title="My Title",
    content_hash="hash_value"
)

if is_dup:
    print("⚠️ 内容重复，请调整")
else:
    print("✅ 可以发布")
```

### 3. 自定义项目信息

编辑 `weekly_posting_planner.py` 中的 `_load_project_info()` 方法：

```python
def _load_project_info(self) -> Dict:
    return {
        "name": "AnimoCerebro",
        "version": "1.0.0",
        "github": "https://github.com/AnimoCerebro",
        "current_focus": [
            "你的当前焦点",
            # ...
        ],
        "recent_achievements": [
            "你的最新成就",
            # ...
        ]
    }
```

### 4. 添加新的内容模板

在 `_generate_post_content()` 中添加新的生成器：

```python
def _generate_custom_post(self, date: datetime) -> Dict:
    """生成自定义帖子"""
    title = "Custom Title"
    content = "Custom content..."
    
    import hashlib
    return {
        "title": title,
        "content": content,
        "content_hash": hashlib.md5(content.encode()).hexdigest(),
        "flair": "Discussion",
        "estimated_length": len(content),
        "posting_time": "12:00-14:00 EST"
    }
```

然后在 `content_templates` 中注册：

```python
content_templates = {
    "YourCommunity": {
        "your_content_type": self._generate_custom_post
    }
}
```

## 📁 文件说明

### 生成的文件

1. **`Agent/weekly_posting_plan.json`**
   - 当前周的计划（JSON 格式）
   - 每次生成计划时自动更新

2. **`Agent/weekly_plan_YYYY-MM-DD.md`**
   - Markdown 格式的计划
   - 便于阅读和分享
   - 文件名包含周开始日期

3. **`Agent/posting_history.json`**
   - 发帖历史记录
   - 用于重复检测
   - 自动维护

### 文件位置

```
Agent/
├── weekly_posting_planner.py      # 计划生成器核心代码
├── weekly_posting_plan.json       # 当前周计划（JSON）
├── weekly_plan_2026-04-20.md      # Markdown 格式计划
├── posting_history.json           # 发帖历史记录
└── WEEKLY_PLANNER_GUIDE.md        # 本文档
```

## 🔄 工作流程

### 完整流程

```
1. 生成本周计划
   ↓
2. 检查每天的内容是否重复
   ↓
3. 如果重复 → 生成备选方案
   ↓
4. 保存计划到 JSON
   ↓
5. 导出为 Markdown
   ↓
6. 根据计划执行发帖
   ↓
7. 记录发帖结果
   ↓
8. 下周重新生成（自动考虑历史）
```

### 每日执行

```python
# 早上：查看当天计划
with open("Agent/weekly_posting_plan.json") as f:
    plan = json.load(f)

today = datetime.now().strftime("%A")  # Monday, Tuesday, etc.
daily_plan = plan["schedule"][today]

# 准备发帖内容
title = daily_plan["primary_post"]["title"]
content = daily_plan["primary_post"]["content"]

# 发帖...
# ...

# 记录结果
planner.record_post(
    subreddit=daily_plan["primary_community"],
    title=title,
    content=content,
    success=True
)
```

## ⚙️ 配置选项

### 调整重复检测阈值

```python
def _is_similar_title(self, title1, title2, threshold=0.8):
    # 降低阈值会更严格（更容易判定为重复）
    # 提高阈值会更宽松
    ...
```

### 修改时间窗口

```python
# 默认 7 天
seven_days_ago = time.time() - (7 * 24 * 3600)

# 改为 14 天
fourteen_days_ago = time.time() - (14 * 24 * 3600)
```

### 自定义发帖时间

编辑 `_get_best_posting_time()` 方法：

```python
def _get_best_posting_time(self, day_offset):
    times = {
        0: "你的周一时间",
        1: "你的周二时间",
        # ...
    }
    return times.get(day_offset, "默认时间")
```

## 📈 最佳实践

### 1. 每周一生成新计划

```python
# 设置定时任务或使用 cron
# 每周一早上 9 点运行
0 9 * * 1 cd /path/to/project && python Agent/weekly_posting_planner.py
```

### 2. 定期检查发帖历史

```bash
# 查看历史记录
cat Agent/posting_history.json | python -m json.tool
```

### 3. 根据反馈调整

- 监控帖子的 upvotes 和评论
- 记录哪些内容受欢迎
- 调整后续的内容策略

### 4. 保持灵活性

- 计划是指导，不是硬性规定
- 根据社区反应调整
- 突发事件可以插队

## 🔍 调试和监控

### 查看当前计划

```python
import json

with open("Agent/weekly_posting_plan.json") as f:
    plan = json.load(f)

# 查看今天的计划
from datetime import datetime
today = datetime.now().strftime("%A")
print(json.dumps(plan["schedule"][today], indent=2))
```

### 检查重复检测

```python
# 测试重复检测
is_dup = planner.check_duplicate(
    subreddit="Python",
    title="Test Title",
    content_hash="test_hash"
)
print(f"是否重复: {is_dup}")
```

### 查看发帖统计

```python
# 统计本周发帖
from datetime import datetime, timedelta

week_ago = time.time() - (7 * 24 * 3600)
recent_posts = [
    p for p in planner.posting_history["posts"]
    if p["timestamp"] > week_ago
]

print(f"本周发帖数: {len(recent_posts)}")
print(f"成功率: {sum(p['success'] for p in recent_posts) / len(recent_posts) * 100:.1f}%")
```

## 🎯 示例输出

### Markdown 计划预览

```markdown
# AnimoCerebro 每周发帖计划

**周期**: 2026-04-20 至 2026-04-24  
**生成时间**: 2026-04-20 10:00:00

---

## 星期一 (2026-04-20)

### 📋 主题
项目进度更新

### 🎯 主要内容
- **社区**: r/Project Update
- **标题**: 🚀 AnimoCerebro Weekly Progress Update - 2026-04-20
- **最佳时间**: 10:00-12:00 EST (Monday morning)
- **内容重点**: 项目进展、新功能、成就展示

### 📝 帖子预览
**标题**: 🚀 AnimoCerebro Weekly Progress Update - 2026-04-20

**Flair**: Project Update

**预计长度**: 1500 字符

### 🔄 备选社区
- r/Python (14:00-16:00 EST)

---
```

## ❓ 常见问题

### Q: 如何重置发帖历史？

A: 删除或清空 `Agent/posting_history.json` 文件：

```bash
rm Agent/posting_history.json
# 或
echo '{"posts": []}' > Agent/posting_history.json
```

### Q: 计划可以修改吗？

A: 可以！直接编辑 JSON 或 Markdown 文件。但建议重新生成计划以保持一致性。

### Q: 如何处理特殊情况（如节假日）？

A: 手动调整当天的计划，或在生成后编辑 JSON 文件。

### Q: 可以提前生成多周计划吗？

A: 当前版本只支持单周计划。可以多次调用并保存不同文件：

```python
for week in range(4):
    week_start = datetime.now() + timedelta(weeks=week)
    plan = planner.generate_weekly_plan(week_start)
    planner.save_markdown_plan(plan, f"Agent/plan_week_{week+1}.md")
```

### Q: 如何集成到自动化流程？

A: 结合 `animocerebro_promoter.py` 使用：

```python
from Agent.weekly_posting_planner import WeeklyPostingPlanner
from Agent.animocerebro_promoter import AnimoCerebroPromoter

# 生成计划
planner = WeeklyPostingPlanner()
plan = planner.generate_weekly_plan()

# 获取今天的计划
today = datetime.now().strftime("%A")
daily_plan = plan["schedule"][today]

# 执行发帖
promoter = AnimoCerebroPromoter(page, rules_manager)
# ... 使用 daily_plan 中的内容发帖

# 记录结果
planner.record_post(...)
```

## 🚀 立即开始

```bash
# 激活虚拟环境
source .venv/bin/activate

# 生成本周计划
python Agent/weekly_posting_planner.py

# 查看生成的文件
ls -lh Agent/weekly_plan_*.md
cat Agent/weekly_posting_plan.json | python -m json.tool
```

---

**创建者**: AI Assistant  
**最后更新**: 2026-04-20  
**版本**: 1.0  
**状态**: ✅ 完整实现

## 🎉 总结

每周发帖计划系统提供了：

- ✅ 自动化的周计划生成
- ✅ 智能的重复检测
- ✅ 灵活的内容定制
- ✅ 完整的文档和示例
- ✅ 易于集成和使用

开始使用，让 AnimoCerebro 的宣传更有条理和效率！🚀
