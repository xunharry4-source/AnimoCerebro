#!/usr/bin/env python3
"""
使用 Stealth 模式隐藏自动化特征

文件用途:
    通过注入 JavaScript 和修改浏览器指纹，隐藏 Playwright 的自动化特征，
    避免被 X/Twitter 检测为机器人。
"""

import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(project_root))


# Stealth 脚本 - 隐藏自动化特征
STEALTH_SCRIPT = """
// 隐藏 webdriver
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});

// 隐藏 chrome.csi
window.chrome = {
    runtime: {},
    csi: function() {},
    loadTimes: function() {}
};

// 隐藏 navigator.plugins
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5]
});

// 隐藏 navigator.languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en']
});

// 隐藏 permissions
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);

// 隐藏 automation-controlled
Object.defineProperty(navigator, 'userAgent', {
    get: () => 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
});
"""


def main():
    print("\n" + "=" * 80)
    print("  Stealth 模式 - 隐藏自动化特征")
    print("=" * 80)

    user_data_dir = Path("/tmp/chrome_stealth_test")
    user_data_dir.mkdir(exist_ok=True)
    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    if not Path(chrome_path).exists():
        print(f"❌ Chrome 未找到")
        return False

    print(f"\n📂 独立目录: {user_data_dir}")
    print("🛡️  启用 Stealth 模式...")

    playwright = None
    context = None
    page = None

    try:
        playwright = sync_playwright().start()

        # 启动浏览器
        print("🌐 启动 Chrome...")
        browser = playwright.chromium.launch(
            executable_path=chrome_path,
            headless=False,
            slow_mo=1000,  # 更慢，更像真人
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--no-zygote',
                '--single-process',
                '--disable-gpu',
            ]
        )

        # 创建上下文（更接近真实浏览器）
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="America/New_York",
            permissions=["geolocation"],
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            }
        )

        # 添加 stealth 脚本
        context.add_init_script(STEALTH_SCRIPT)

        page = context.new_page()

        # 额外的 stealth 措施
        page.add_init_script("""
            // 覆盖所有可能的检测点
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
            Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
            Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });
        """)

        print("✅ Chrome 已启动（Stealth 模式）")

        # 打开 X.com
        print("\n📱 打开 X.com...")
        page.goto("https://x.com", wait_until="networkidle", timeout=60000)
        print("✅ 页面已加载")

        # 截图检查是否被检测
        screenshot_before = Path("screenshots/x_before_login.png")
        screenshot_before.parent.mkdir(exist_ok=True)
        page.screenshot(path=str(screenshot_before), full_page=True)
        print(f"📸 登录前截图: {screenshot_before}")

        print("\n" + "=" * 80)
        print("  📋 Stealth 模式已启用")
        print("=" * 80)
        print("  • 已隐藏 webdriver 特征")
        print("  • 已修改浏览器指纹")
        print("  • 已模拟真实用户行为")
        print("\n  请在打开的浏览器中手动登录 X 账号")
        print("  登录后按回车键继续自动发帖...")
        print("=" * 80)

        input("\n登录后按回车...")

        # 检查登录状态
        current_url = page.url
        print(f"\n📍 当前 URL: {current_url}")

        if "home" in current_url or "timeline" in current_url:
            print("✅ 检测到已登录")

            # 等待页面完全加载
            time.sleep(3)

            # 自动发帖
            print("\n📤 开始自动发帖...")
            try:
                tweet_box = page.locator('div[role="textbox"][data-testid="tweetTextarea_0"]')
                tweet_box.wait_for(state="visible", timeout=15000)

                test_content = "🧪 AnimoCerebro Self-Promotion Agent Test\n\nAutomated posting test.\nGitHub: https://github.com/xunharry4-source/AnimoCerebro-external\n\n#AI #ML #OpenSource #Test"

                print("   📝 填写内容...")
                tweet_box.fill(test_content)
                time.sleep(2)

                print("   🚀 点击发布...")
                post_button = page.locator('div[data-testid="tweetButton"]')
                post_button.click()
                time.sleep(10)

                # 截图
                screenshot_path = Path("screenshots/x_post_STEALTH_SUCCESS.png")
                page.screenshot(path=str(screenshot_path), full_page=True)
                print(f"   📸 截图: {screenshot_path.absolute()}")
                print("\n✅ 发帖完成!")

            except Exception as e:
                print(f"   ❌ 发帖失败: {e}")
        else:
            print("⚠️  未检测到登录")

        print("\n⏳ 30 秒后关闭...")
        time.sleep(30)
        return True

    except Exception as e:
        print(f"❌ {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        try:
            if page: page.close()
            if context: context.close()
            if browser: browser.close()
            if playwright: playwright.stop()
            print("✅ 测试 Chrome 已关闭")
        except:
            pass


if __name__ == "__main__":
    main()
