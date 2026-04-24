#!/usr/bin/env python3
"""
使用 Stealth Chrome 配置测试 Reddit 和 X.com 发帖

完全复用 test_auto_stealth_wait.py 的配置，确保登录状态保持
"""

import os
import sys
import time
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

def get_chrome_path():
    """获取系统中 Google Chrome 的路径"""
    system = sys.platform
    
    if system == "darwin":  # macOS
        paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    elif system == "win32":  # Windows
        paths = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        ]
    else:  # Linux
        paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
        ]
    
    for path in paths:
        if Path(path).exists():
            return path
    
    raise FileNotFoundError("未找到 Google Chrome")


def test_with_stealth_config():
    """使用 Stealth Chrome 配置测试"""
    print("\n" + "="*80)
    print("🧪 使用 Stealth Chrome 配置测试")
    print("="*80)
    
    from playwright.sync_api import sync_playwright
    from Agent.browser_automation.test_auto_stealth_wait import STEALTH_JS
    
    try:
        # 1. 指定独立用户数据目录（与 test_auto_stealth_wait.py 相同）
        user_data_dir = Path("./chrome_custom_profile").resolve()
        user_data_dir.mkdir(exist_ok=True)
        
        print(f"\n📂 用户数据目录: {user_data_dir}")
        print("   ✓ 使用与 test_auto_stealth_wait.py 相同的目录")
        
        # 2. 获取 Chrome 路径
        executable_path = get_chrome_path()
        print(f"🔍 Chrome 路径: {executable_path}")
        
        playwright = None
        context = None
        page = None
        
        try:
            # 3. 启动 Playwright
            playwright = sync_playwright().start()
            
            # 4. 启动持久化上下文（关键！）
            print("\n🚀 正在启动 Chrome (Stealth 模式)...")
            
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                executable_path=executable_path,
                headless=False,
                slow_mo=500,
                viewport={"width": 1920, "height": 1080},
                no_viewport=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            )
            
            # 5. 注入隐身脚本
            context.add_init_script(STEALTH_JS)
            print("   ✓ 已注入 Stealth 脚本")
            
            page = context.new_page()
            print("   ✅ 浏览器启动成功")
            
            # 6. 测试访问 Reddit
            print("\n📝 测试 1: 访问 Reddit...")
            page.goto("https://www.reddit.com", wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
            
            # 截图
            screenshot_path = Path("screenshots/test_reddit_stealth.png")
            screenshot_path.parent.mkdir(exist_ok=True)
            page.screenshot(path=str(screenshot_path))
            print(f"   📸 Reddit 截图: {screenshot_path}")
            
            # 检查是否登录
            current_url = page.url
            if "login" not in current_url.lower():
                print("   ✅ 似乎已登录 Reddit")
            else:
                print("   ⚠️  需要登录 Reddit")
                print("   💡 请在打开的浏览器中登录")
                input("   按 Enter 继续...")
            
            # 7. 测试访问 X.com
            print("\n📝 测试 2: 访问 X.com...")
            page.goto("https://twitter.com/home", wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
            
            # 截图
            screenshot_path = Path("screenshots/test_x_stealth.png")
            page.screenshot(path=str(screenshot_path))
            print(f"   📸 X.com 截图: {screenshot_path}")
            
            # 检查是否登录
            current_url = page.url
            if "login" not in current_url.lower() and "signin" not in current_url.lower():
                print("   ✅ 似乎已登录 X.com")
            else:
                print("   ⚠️  需要登录 X.com")
                print("   💡 请在打开的浏览器中登录")
                input("   按 Enter 继续...")
            
            # 8. 测试 Reddit 发帖
            print("\n📝 测试 3: Reddit 发帖...")
            from Agent.social_promotion.reddit_smart_poster import RedditSmartPoster
            from Agent.social_promotion.community_rules_manager import CommunityRulesManager
            
            rules_manager = CommunityRulesManager()
            poster = RedditSmartPoster(page, rules_manager)
            
            test_title = f"Test Post (Stealth) - {time.strftime('%Y-%m-%d %H:%M:%S')}"
            test_content = """
This is a test post using Stealth Chrome configuration.

Testing with the same setup as test_auto_stealth_wait.py to ensure login persistence.

Please ignore this test.
"""
            
            print(f"   标题: {test_title}")
            print(f"   社区: r/AnimoCerebro")
            
            success = poster.post_custom_content(
                subreddit="AnimoCerebro",
                title=test_title,
                content=test_content,
                flair="Discussion",
                max_retries=1
            )
            
            if success:
                print("   ✅ Reddit 发帖成功！")
            else:
                print("   ❌ Reddit 发帖失败")
            
            print("\n✅ 所有测试完成！")
            print("💡 提示: 浏览器将保持打开，你可以手动检查登录状态")
            input("\n按 Enter 关闭浏览器...")
            
            return True
            
        finally:
            # 清理
            if page:
                page.close()
            if context:
                context.close()
            if playwright:
                playwright.stop()
            print("\n✅ 浏览器已关闭")
            
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "🎯"*40)
    print("Stealth Chrome 配置测试")
    print("🎯"*40)
    
    success = test_with_stealth_config()
    
    if success:
        print("\n🎉 测试成功！")
    else:
        print("\n❌ 测试失败")
    
    sys.exit(0 if success else 1)
