# 测试脚本修复记录

## 🐛 发现的严重问题

### 问题 1: 用户数据目录不一致
**严重程度**: 🔴 严重  
**影响**: 登录信息丢失，每次都需要重新登录

**原因**:
- `test_social_media_automation.py` 使用了 `./chrome_social_profile`
- `test_auto_stealth_wait.py` 使用了 `./chrome_custom_profile`
- 两个不同的目录导致 Cookie 无法共享

**解决方案**:
```python
# 修复前
self.user_data_dir = Path("./chrome_social_profile").resolve()

# 修复后 - 与 test_auto_stealth_wait.py 保持一致
self.user_data_dir = Path("./chrome_custom_profile").resolve()
```

**验证**:
```bash
# 检查目录是否存在且包含 Cookie
ls -lah chrome_custom_profile/Default/Cookies
# 输出: -rw-------@ 1 harry staff 36K Apr 20 10:39 Cookies
```

---

### 问题 2: 隐身脚本简化
**严重程度**: 🟡 中等  
**影响**: 浏览器指纹可能暴露，增加被检测风险

**原因**:
- 新脚本使用了简化的隐身脚本（只有 5 项）
- 原脚本使用增强的隐身脚本（13 项）

**解决方案**:
完全复制 `test_auto_stealth_wait.py` 的增强版隐身脚本，包括：
1. 隐藏 WebDriver 标志
2. 模拟真实 Chrome 对象
3. 模拟真实插件列表
4. 模拟语言设置
5. 修复权限查询
6. 删除 webdriver 原型链
7. 模拟真实 User-Agent
8. 模拟硬件信息
9. 隐藏自动化相关属性
10. 覆盖 toString 方法
11. 模拟 WebGL 供应商
12. 移除 Playwright 特有变量
13. 模拟窗口尺寸

---

### 问题 3: CommunityRulesManager API 错误
**严重程度**: 🟡 中等  
**影响**: Reddit 规则获取和违规检测功能失败

**原因**:
- 使用了不存在的方法 `load_rule()` 和 `save_rule()`
- 正确的方法是 `get_community_rules()` 和 `save_rule_to_cache()`

**解决方案**:
```python
# 修复前
cached_rule = self.rules_manager.load_rule(subreddit)
self.rules_manager.save_rule(community_rule)

# 修复后
cached_rule = self.rules_manager.get_community_rules(subreddit, auto_download=False)
self.rules_manager.save_rule_to_cache(community_rule)
```

---

### 问题 4: X.com 发帖框定位器 strict mode violation
**严重程度**: 🟢 轻微  
**影响**: X 发帖功能失败

**原因**:
- 页面中有多个匹配的元素
- Playwright 的 strict mode 要求唯一匹配

**解决方案**:
```python
# 修复前
tweet_box = self.page.locator('div[role="textbox"][data-testid="tweetTextarea_0"]')

# 修复后 - 使用 first() 选择第一个匹配的元素
tweet_box = self.page.locator('div[role="textbox"][data-testid="tweetTextarea_0"]').first
```

---

## ✅ 修复后的配置对比

| 配置项 | test_auto_stealth_wait.py | test_social_media_automation.py (修复前) | test_social_media_automation.py (修复后) |
|--------|--------------------------|----------------------------------------|----------------------------------------|
| 用户数据目录 | `./chrome_custom_profile` | ❌ `./chrome_social_profile` | ✅ `./chrome_custom_profile` |
| 隐身脚本 | ✅ 增强版 (13项) | ❌ 简化版 (5项) | ✅ 增强版 (13项) |
| 启动参数 | ✅ 完整 (6个) | ⚠️ 部分 (4个) | ✅ 完整 (6个) |
| slow_mo | ✅ 500ms | ❌ 无 | ✅ 500ms |
| User-Agent | ✅ 自定义 | ✅ 自定义 | ✅ 自定义 |
| headless | ✅ False | ✅ False | ✅ False |

---

## 🧪 测试结果验证

### 修复前
```
❌ 每次运行都需要重新登录
❌ Reddit 规则获取失败 (API 错误)
❌ X 发帖失败 (strict mode violation)
⚠️  浏览器指纹可能暴露
```

### 修复后
```
✅ 登录状态保持成功
✅ X.com 自动检测到登录
✅ Reddit 规则获取正常
✅ X 发帖框定位修复
⚠️  Reddit 发帖按钮需要手动点击（网站界面变化）
```

---

## 📝 最佳实践建议

### 1. 统一配置文件
创建统一的浏览器配置文件，避免重复代码：

```python
# config/browser_config.py
BROWSER_CONFIG = {
    "user_data_dir": "./chrome_custom_profile",
    "chrome_path": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "headless": False,
    "slow_mo": 500,
    "viewport": {"width": 1920, "height": 1080},
    "args": [
        "--disable-blink-features=AutomationControlled",
        "--start-maximized",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--no-default-browser-check",
    ],
    "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
}
```

### 2. 使用相同的隐身脚本
将隐身脚本提取到单独的文件：

```python
# utils/stealth_script.py
STEALTH_JS = """
// 完整的隐身脚本（13项）
...
"""
```

### 3. 定期验证配置一致性
```bash
# 检查所有脚本是否使用相同的配置
grep -r "chrome_custom_profile" Agent/*.py
grep -r "user_data_dir" Agent/*.py
```

### 4. 文档化关键配置
在代码中添加清晰的注释：

```python
# ⚠️ 重要：必须与 test_auto_stealth_wait.py 使用相同的用户数据目录
# 否则登录状态无法保持
self.user_data_dir = Path("./chrome_custom_profile").resolve()
```

---

## 🔄 后续优化计划

1. **提取公共配置** - 创建统一的浏览器配置模块
2. **添加配置验证** - 启动时检查配置是否正确
3. **自动化测试** - 确保配置变更不会破坏现有功能
4. **文档更新** - 更新所有相关文档

---

**修复日期**: 2026-04-20  
**修复人员**: AI Assistant  
**验证状态**: ✅ 已验证登录状态保持成功
