# 社交媒体自动化测试 - 配置说明

## ⚠️ 重要：用户数据目录配置

### 问题发现
之前的测试脚本使用了不同的用户数据目录，导致登录信息丢失。

### 解决方案
**所有测试脚本现在统一使用相同的用户数据目录：**

```python
self.user_data_dir = Path("./chrome_custom_profile").resolve()
```

这个目录与 `test_auto_stealth_wait.py` 完全相同，确保：
- ✅ 登录状态持久化
- ✅ Cookie 共享
- ✅ 会话保持

## 📁 用户数据目录结构

```
chrome_custom_profile/
├── Default/                    # Chrome 默认配置文件
│   ├── Cookies                # Cookie 数据库（包含登录信息）
│   ├── Local Storage/         # 本地存储
│   ├── Session Storage/       # 会话存储
│   ├── Cache/                 # 缓存
│   └── ...
├── playwright_tmp/            # Playwright 临时文件
│   ├── downloads/
│   └── traces/
```

## 🔑 关键配置参数

### 1. 浏览器启动配置（所有脚本统一）

```python
context = playwright.chromium.launch_persistent_context(
    user_data_dir="./chrome_custom_profile",  # ⚠️ 必须相同
    executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    headless=False,                             # 必须有头模式
    slow_mo=500,                                # 降低操作速度
    viewport={"width": 1920, "height": 1080},
    args=[
        "--disable-blink-features=AutomationControlled",
        "--start-maximized",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--no-default-browser-check",
    ],
    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)
```

### 2. 隐身脚本（所有脚本统一）

使用增强的隐身脚本，包含 13 项指纹隐藏：
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

## 🚀 使用流程

### 首次使用（需要登录）

1. **运行基础测试脚本进行登录**
   ```bash
   source .venv/bin/activate
   python Agent/test_auto_stealth_wait.py
   ```

2. **在打开的 Chrome 中手动登录**
   - X.com (Twitter)
   - Reddit.com
   
3. **登录成功后，Cookie 会自动保存到 `chrome_custom_profile/`**

### 后续使用（自动保持登录）

所有测试脚本都会自动使用已保存的登录状态：

```bash
# 综合测试（X + Reddit）
python Agent/test_social_media_automation.py

# 单独测试 X
python Agent/test_auto_stealth_wait.py

# 其他测试脚本...
```

## 📊 测试脚本对比

| 脚本 | 用户数据目录 | 隐身脚本 | 启动参数 | 登录状态 |
|------|------------|---------|---------|---------|
| test_auto_stealth_wait.py | ✅ chrome_custom_profile | ✅ 增强版 | ✅ 完整 | ✅ 保持 |
| test_social_media_automation.py | ✅ chrome_custom_profile | ✅ 增强版 | ✅ 完整 | ✅ 保持 |
| 其他旧脚本 | ❌ 不同目录 | ❌ 简化版 | ❌ 不完整 | ❌ 丢失 |

## ⚙️ 配置检查清单

运行测试前，请确认：

- [ ] 使用 `./chrome_custom_profile` 作为用户数据目录
- [ ] 使用真实的 Google Chrome 二进制文件
- [ ] 启用 `headless=False`（有头模式）
- [ ] 添加 `--disable-blink-features=AutomationControlled` 参数
- [ ] 注入完整的隐身脚本
- [ ] 使用正确的 User-Agent

## 🔍 验证登录状态

运行以下命令验证登录状态是否保持：

```python
from playwright.sync_api import sync_playwright
from pathlib import Path

playwright = sync_playwright().start()
context = playwright.chromium.launch_persistent_context(
    user_data_dir="./chrome_custom_profile",
    executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    headless=False,
)
page = context.new_page()
page.goto("https://x.com")
print(f"当前 URL: {page.url}")
print(f"是否登录: {'home' in page.url or 'timeline' in page.url}")
context.close()
playwright.stop()
```

## 💡 最佳实践

### 1. 统一管理用户数据目录
```python
# 在项目根目录创建配置文件
# config/browser_config.py
BROWSER_CONFIG = {
    "user_data_dir": "./chrome_custom_profile",
    "chrome_path": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "headless": False,
    "slow_mo": 500,
}
```

### 2. 定期检查 Cookie 有效性
```python
def check_login_status(page, platform="x"):
    """检查登录状态"""
    if platform == "x":
        return "home" in page.url or "timeline" in page.url
    elif platform == "reddit":
        return "login" not in page.url.lower()
    return False
```

### 3. 备份重要的用户数据目录
```bash
# 备份登录状态
tar -czf chrome_profile_backup.tar.gz chrome_custom_profile/

# 恢复登录状态
tar -xzf chrome_profile_backup.tar.gz
```

## 🐛 常见问题

### Q1: 登录后再次运行仍然要求登录？
**A:** 检查以下几点：
1. 确认使用的是相同的 `user_data_dir`
2. 确认 Chrome 正常关闭（Cookie 已保存）
3. 检查 `chrome_custom_profile/Default/Cookies` 文件是否存在

### Q2: 如何切换不同的账号？
**A:** 创建多个用户数据目录：
```python
# 账号 1
user_data_dir = "./chrome_custom_profile_account1"

# 账号 2
user_data_dir = "./chrome_custom_profile_account2"
```

### Q3: Cookie 何时会过期？
**A:** 
- X.com: 通常 30-90 天
- Reddit: 通常 30 天
- 取决于平台的会话策略

### Q4: 如何强制刷新登录状态？
**A:** 删除用户数据目录并重新登录：
```bash
rm -rf chrome_custom_profile/
python Agent/test_auto_stealth_wait.py
```

## 📝 更新日志

### 2026-04-20
- ✅ 统一所有测试脚本的用户数据目录
- ✅ 使用增强的隐身脚本（13 项指纹隐藏）
- ✅ 确保登录状态持久化
- ✅ 添加配置检查清单

---

**维护者**: AI Assistant  
**最后更新**: 2026-04-20  
**版本**: 1.1
