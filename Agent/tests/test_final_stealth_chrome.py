#!/usr/bin/env python3
"""
最终方案：真实Chrome + 独立目录 + 完全隐藏控制

使用 launch_persistent_context 启动真实 Google Chrome，
通过 init_script 完全隐藏自动化特征。
"""

import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(project_root))

# 完整的 stealth 脚本
STEALTH_JS = """
// 隐藏 webdriver
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// 隐藏 chrome 对象
window.chrome = { runtime: {}, csi: ()=>{}, loadTimes: ()=>{} };

// 隐藏 plugins
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });

// 隐藏 languages
Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });

// 伪装 permissions
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (p) => (
    p.name === 'notifications' ? Promise.resolve({ state: Notification.permission }) : originalQuery(p)
);

// 隐藏 automation
delete navigator.__proto__.webdriver;

// 伪装 userAgent
Object.defineProperty(navigator, 'userAgent', {
    get: () => 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
});

// 其他指纹
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });
"""


def main():
    print("\n" + "=" * 80)
    print("  真实 Chrome + 完全隐藏控制")
    print("=" * 80)

    user_data_dir = Path("/tmp/chrome_final_stealth_independent")
    user_data_dir.mkdir(exist_ok=True)
    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    if not Path(chrome_path).exists():
        print("❌ Chrome 未找到")
        return False

    print(f"\n📂 独立目录: {user_data_dir}")
    print(f"🌐 真实 Chrome: {chrome_path}")
    print("🛡️  完整 Stealth 保护")

    playwright = None
    context = None
    page = None

    try:
        playwright = sync_playwright().start()

        # 启动真实 Chrome + 独立目录
        print("\n🚀 启动独立 Chrome 实例...")
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            executable_path=chrome_path,  # 真实 Google Chrome
            headless=False,
            slow_mo=800,
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="America/New_York",
            args=[
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-blink-features=AutomationControlled',
            ],
            bypass_csp=True,
        )

        # 注入 stealth 脚本到所有页面
        context.add_init_script(STEALTH_JS)

        page = context.new_page()

        # 额外注入
        page.add_init_script(STEALTH_JS)

        print("✅ Chrome 已启动（完全隐藏模式）")

        # 打开 X
        print("\n📱 打开 X.com...")
        page.goto("https://x.com", wait_until="domcontentloaded", timeout=60000)

        # 检查是否被检测
        detected = page.evaluate("() => navigator.webdriver !== undefined")
        print(f"🔍 WebDriver 检测: {'❌ 被发现' if detected else '✅ 已隐藏'}")

        # 截图
        screenshot = Path("screenshots/x_stealth_check.png")
        screenshot.parent.mkdir(exist_ok=True)
        page.screenshot(path=str(screenshot), full_page=True)
        print(f"📸 截图: {screenshot}")

        print("\n" + "=" * 80)
        print("  📋 请在打开的 Chrome 中登录")
        print("=" * 80)
        print("  • 这是独立的 Chrome，不影响您的主 Chrome")
        print("  • Stealth 已启用，应该不会被检测")
        print("  • 登录后按回车继续自动发帖")
        print("=" * 80)

        input("\n登录后按回车...")

        current_url = page.url
        print(f"\n📍 URL: {current_url}")

        if "home" in current_url or "timeline" in current_url:
            print("✅ 已登录")
            time.sleep(3)

            # 发帖
            print("\n📤 发帖...")
            try:
                tweet_box = page.locator('div[role="textbox"][data-testid="tweetTextarea_0"]')
                tweet_box.wait_for(state="visible", timeout=15000)

                test_content = "🧪 AnimoCerebro Test - Stealth Mode\n\nPosted from independent Chrome instance.\n#AI #Test"
                tweet_box.fill(test_content)
                time.sleep(2)

                post_button = page.locator('div[data-testid="tweetButton"]')
                post_button.click()
                time.sleep(10)

                result_screenshot = Path("screenshots/x_stealth_post_FINAL.png")
                page.screenshot(path=str(result_screenshot), full_page=True)
                print(f"   📸 截图: {result_screenshot.absolute()}")
                print("\n✅ 发帖完成!")

            except Exception as e:
                print(f"   ❌ 失败: {e}")
        else:
            print("⚠️  未登录")

        print("\n⏳ 30秒后关闭...")
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
            if playwright: playwright.stop()
            print("✅ Chrome 已关闭")
        except:
            pass


if __name__ == "__main__":
    main()
