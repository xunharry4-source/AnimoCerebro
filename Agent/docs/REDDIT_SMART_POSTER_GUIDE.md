# Reddit 智能发帖助手 - 完整工作流程

## 🎯 核心流程

```
1. 检查社区规则是否存在于本地缓存
   ↓
2. 如果不存在或已过期 → 自动下载社区规则
   ↓
3. 基于社区规则生成合规内容
   ↓
4. 尝试发帖
   ↓
5. 如果失败 → 分析错误原因
   ↓
6. 根据错误调整内容策略
   ↓
7. 重试（最多3次）
```

## 📁 社区规则存储

### 存储结构

每个社区的规则单独保存为一个 JSON 文件：

```
Agent/community_rules_cache/
├── Python.json          # r/Python 的规则
├── MachineLearning.json # r/MachineLearning 的规则
├── learnprogramming.json
├── AskReddit.json
└── ...
```

### 规则文件格式

```json
{
  "subreddit": "Python",
  "rules": [
    {
      "title": "Rule 1: No low-effort posts",
      "description": "Posts must show effort and research..."
    },
    {
      "title": "Rule 2: No self-promotion",
      "description": "Do not promote your own content..."
    }
  ],
  "last_updated": "2026-04-20T10:30:00+00:00",
  "source": "scraped",
  "rule_count": 8
}
```

## 🔧 使用示例

### 基本用法

```python
from Agent.reddit_smart_poster import RedditSmartPoster
from Agent.community_rules_manager import CommunityRulesManager
from playwright.sync_api import sync_playwright

# 初始化
playwright = sync_playwright().start()
browser = playwright.chromium.launch(headless=False)
context = browser.new_context()
page = context.new_page()

rules_manager = CommunityRulesManager()
poster = RedditSmartPoster(page, rules_manager)

# 智能发帖（自动处理规则检查和下载）
success = poster.post_with_retry("Python", max_retries=3)

if success:
    print("✅ 发帖成功!")
else:
    print("❌ 发帖失败")

# 清理
browser.close()
playwright.stop()
```

### 集成到测试脚本

```python
def test_reddit_posting_with_rules(self, subreddit="Python"):
    """测试 Reddit 发帖（带规则检查和下载）"""
    
    print(f"\n📋 检查 r/{subreddit} 社区规则...")
    
    # 创建智能发帖助手
    smart_poster = RedditSmartPoster(self.page, self.rules_manager)
    
    # 执行智能发帖
    # 内部会自动：
    # 1. 检查本地是否有规则
    # 2. 如果没有，自动下载
    # 3. 基于规则生成合规内容
    # 4. 多次重试
    success = smart_poster.post_with_retry(subreddit, max_retries=3)
    
    if success:
        self.test_results["reddit_posting"] = True
        print(f"✅ r/{subreddit} 发帖成功")
    else:
        print(f"❌ r/{subreddit} 发帖失败")
    
    return success
```

## 📊 工作流程详解

### 步骤 1: 检查社区规则

```python
# 内部实现
def _ensure_community_rules(self, subreddit: str):
    # 1. 检查本地缓存
    cached_rules = self.rules_manager.get_community_rules(
        subreddit, 
        auto_download=False
    )
    
    if cached_rules and not cached_rules.is_expired(max_age_days=7):
        print("✅ 使用缓存的规则")
        return cached_rules
    
    # 2. 缓存不存在或已过期，需要下载
    print("⚠️  需要下载社区规则")
    
    # 3. 从网页抓取
    downloaded_rules = self._download_community_rules_from_web(subreddit)
    
    if downloaded_rules:
        # 4. 保存到本地（每个社区单独保存）
        self.rules_manager.save_rule_to_cache(downloaded_rules)
        print(f"💾 规则已保存到: community_rules_cache/{subreddit}.json")
        return downloaded_rules
    
    # 5. 降级方案：使用 API
    api_rules = self.rules_manager.download_community_rules(subreddit)
    
    return api_rules or cached_rules
```

### 步骤 2: 分析规则限制

```python
def _analyze_prohibited_items(self, rules) -> List[str]:
    """分析规则中的禁止事项"""
    
    prohibited = []
    
    # 检测常见禁止项
    rule_texts = ' '.join([r['title'] + ' ' + r['description'] 
                          for r in rules.rules]).lower()
    
    if 'self-promotion' in rule_texts:
        prohibited.append("self-promotion")
    
    if 'external link' in rule_texts or 'no links' in rule_texts:
        prohibited.append("external_links")
    
    if 'low effort' in rule_texts:
        prohibited.append("low_effort")
    
    # ... 更多检测
    
    return prohibited
```

### 步骤 3: 生成合规内容

```python
def _generate_compliant_content(self, rules, attempt: int):
    """基于规则生成合规内容"""
    
    # 分析禁止事项
    prohibited = self._analyze_prohibited_items(rules)
    
    if attempt == 1:
        # 标准内容
        return {
            "title": "Test Post - Automation Verification",
            "content": "This is a technical test...",
            "strategy": "standard"
        }
    
    elif attempt == 2:
        # 保守内容（如果有自我推广限制）
        if "self-promotion" in prohibited:
            return {
                "title": "Question about best practices",
                "content": "I'm looking for advice...",
                "strategy": "conservative"
            }
    
    else:
        # 最小化内容
        return {
            "title": "Quick question",
            "content": "Does anyone have experience?",
            "strategy": "minimal"
        }
```

## 🎨 实际运行示例

### 场景 1: 首次发帖到新社区

```
================================================================================
  🤖 Reddit 智能发帖 (r/Python)
  🔄 最多重试 3 次
================================================================================

📋 步骤 1: 检查 r/Python 社区规则...
   🔍 检查本地缓存...
   ⚠️  本地无缓存，需要下载

   🌐 正在下载 r/Python 社区规则...
      访问: https://www.reddit.com/r/Python/about/rules
      ✅ 提取到 8 条规则
   ✅ 成功下载 8 条规则
   💾 规则已保存到: community_rules_cache/Python.json

📝 步骤 2: 基于社区规则生成合规内容...
   🔍 分析规则限制...
   ⚠️  检测到以下限制:
      - self-promotion
      - external_links
      - low_effort
   ✅ 已生成合规内容

================================================================================
  🔄 尝试 1/3
================================================================================

🌐 访问 r/Python 提交页面...
   ✓ 使用策略: standard
📝 创建文本帖子...
   ✓ 已选择文本帖子类型

✍️  填写标题 (standard)...
   ✓ 标题: Test Post - Automation Verification #1234567890

✍️  填写内容...
   ✓ 内容已填写 (150 字符)

🏷️  尝试选择 Flair...
   ✓ 找到 Flair 按钮
   ✓ 已选择 Flair: Discussion

🚀 提交帖子...
   ✓ 找到发布按钮
   ✓ 已点击发布

⏳ 等待发布结果...
   ✅ 发帖成功!
   📸 截图: screenshots/reddit_post_success.png

✅ 第 1 次尝试成功!
```

### 场景 2: 规则已缓存

```
================================================================================
  🤖 Reddit 智能发帖 (r/MachineLearning)
  🔄 最多重试 3 次
================================================================================

📋 步骤 1: 检查 r/MachineLearning 社区规则...
   🔍 检查本地缓存...
   ✅ 使用缓存的规则 (更新于: 2026-04-18)
   ✅ 已加载 10 条社区规则

📋 关键规则摘要:
   1. Rule 1: No low-effort posts
      Posts must demonstrate significant effort...
   2. Rule 2: No self-promotion
      Do not promote your own work without permission...
   3. Rule 3: Stay on topic
      All posts must be related to machine learning...

📝 步骤 2: 基于社区规则生成合规内容...
   🔍 分析规则限制...
   ⚠️  检测到以下限制:
      - self-promotion
      - low_effort
   ✅ 已生成合规内容

... (继续发帖流程)
```

### 场景 3: 发帖失败并重试

```
================================================================================
  🔄 尝试 1/3
================================================================================

... (发帖过程)

⏳ 等待发布结果...
   ⚠️  发帖状态未知
   ❌ 检测到错误: RULE_VIOLATION
      - Your submission has been removed
      - This violates Rule 2: No self-promotion

⚠️  第 1 次尝试失败

🔧 分析失败原因并准备修正...
🔍 分析第 1 次失败...
   错误类型: RULE_VIOLATION
   错误信息:
      - Your submission has been removed
      - This violates Rule 2: No self-promotion

💡 建议: 下次尝试将严格遵守社区规则
   - 移除所有外部链接
   - 避免自我推广
   - 使用更中性的语言

🔧 准备第 2 次重试...

================================================================================
  🔄 尝试 2/3
================================================================================

🌐 访问 r/Python 提交页面...
   ✓ 使用策略: conservative
...

✅ 第 2 次尝试成功!
```

## 🛡️ 安全特性

### 1. 规则验证

每次发帖前都会：
- ✅ 检查社区规则是否存在
- ✅ 分析规则中的禁止事项
- ✅ 生成符合规则的内容
- ✅ 避免明显的违规内容

### 2. 内容过滤

根据规则自动过滤：
- 外部链接（如果禁止）
- 自我推广内容（如果禁止）
- 低质量内容（如果禁止）
- 重复内容（如果禁止）

### 3. 渐进式策略

| 尝试次数 | 策略 | 特点 |
|---------|------|------|
| 1 | Standard | 标准测试内容，明确说明是测试 |
| 2 | Conservative | 更像真实用户，避免自动化特征 |
| 3 | Minimal | 最简单内容，最低风险 |

### 4. 错误学习

每次失败都会：
- 记录错误类型
- 分析失败原因
- 调整下次策略
- 保存尝试历史

## 📈 成功率优化建议

### 1. 选择合适的社区

**推荐用于测试的社区**:
- ✅ r/Python - 友好，规则清晰
- ✅ r/learnprogramming - 欢迎新手
- ✅ r/AskReddit - 宽松的规则
- ✅ r/test - 专门用于测试

**避免的社区**:
- ❌ r/news - 严格的内容审核
- ❌ r/politics - 高度监管
- ❌ r/technology - 严格的自我推广规则

### 2. 账号准备

```python
# 发帖前检查账号状态
def check_account_health(page):
    """检查账号健康状况"""
    
    # 检查 Karma
    karma = get_user_karma(page)
    if karma < 100:
        print("⚠️  Karma 较低，发帖可能被限制")
    
    # 检查账号年龄
    account_age = get_account_age(page)
    if account_age.days < 30:
        print("⚠️  账号较新，某些社区可能限制发帖")
    
    # 检查是否有违规历史
    violations = check_violation_history(page)
    if violations > 0:
        print(f"⚠️  有 {violations} 次违规记录")
```

### 3. 时间选择

```python
# 最佳发帖时间
best_times = {
    "weekday": "10:00-14:00 EST",  # 工作日美国东部时间
    "weekend": "12:00-16:00 EST",  # 周末稍晚
    "avoid": ["00:00-06:00", "周五晚上"]
}
```

## 🔍 调试和监控

### 查看规则缓存

```bash
# 列出所有缓存的规则
ls -lh Agent/community_rules_cache/

# 查看某个社区的规则
cat Agent/community_rules_cache/Python.json | jq .
```

### 查看尝试历史

```python
# 在代码中访问
for attempt in poster.attempt_history:
    print(f"尝试 {attempt['attempt']}:")
    print(f"  策略: {attempt.get('strategy', 'unknown')}")
    print(f"  错误: {attempt['errors']['error_type']}")
    print(f"  时间: {datetime.fromtimestamp(attempt['timestamp'])}")
```

### 截图位置

所有截图保存在 `screenshots/` 目录：
- `reddit_submit_attempt.png` - 提交前的页面
- `reddit_post_success.png` - 成功发帖
- `reddit_post_failed.png` - 发帖失败
- `reddit_post_error.png` - 错误页面

## 📝 维护指南

### 更新社区规则

```python
# 强制更新某个社区的规则
rules_manager.cache_dir.joinpath("Python.json").unlink()
poster._ensure_community_rules("Python")
```

### 清除所有缓存

```bash
# 删除所有缓存的规则
rm -rf Agent/community_rules_cache/*.json
```

### 添加新的社区

```python
# 只需调用发帖函数，会自动下载规则
poster.post_with_retry("NewCommunity", max_retries=3)
```

---

**创建日期**: 2026-04-20  
**版本**: 2.0  
**状态**: ✅ 完整实现
