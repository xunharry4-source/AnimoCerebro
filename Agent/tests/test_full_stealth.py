#!/usr/bin/env python3
"""
使用 Playwright-Stealth 完全隐藏自动化特征

文件用途:
    使用 playwright-stealth 库完全隐藏浏览器自动化特征，
    避免被 X/Twitter 检测为机器人。
"""

import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth

project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(project_root))


def main():
    print("\n" + "=" * 80)
    print("  Playwright-Stealth 完全隐藏模式")
    print("=" * 80)

    user_data_dir = Path("/tmp/chrome_full_stealth")
    user_data_dir.mkdir(exist_ok=True)
    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    if not Path(chrome_path).exists():
        print(f"❌ Chrome 未找到")
        return False

    print(f"\n📂 独立目录: {user_data_dir}")
    print("🛡️  启用完整 Stealth 保护...")

    playwright = None
    browser = None
    context = None
    page = None

    try:
        playwright = sync_playwright().start()

        # 启动浏览器
        print("🌐 启动 Chrome...")
        browser = playwright.chromium.launch(
            executable_path=chrome_path,
            headless=False,
            slow_mo=1000,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-first-run',
            ]
        )

        # 创建上下文
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="America/New_York",
        )

        page = context.new_page()

        # 应用 stealth 保护
        print("🛡️  应用 Stealth 保护...")
        stealth(page)
        print("✅ Stealth 保护已启用")

        # 打开 X.com
        print("\n📱 打开 X.com...")
        page.goto("https://x.com", wait_until="domcontentloaded", timeout=60000)
        print("✅ 页面已加载")

        # 检查是否被检测
        is_detected = page.evaluate("""
            () => {
                return navigator.webdriver !== undefined ||
                       document.documentElement.getAttribute('webdriver') !== null;
            }
        """)

        if is_detected:
            print("⚠️  警告: 仍可能检测到自动化特征")
        else:
            print("✅ 未检测到自动化特征")

        # 截图
        screenshot_before = Path("screenshots/x_stealth_mode.png")
        screenshot_before.parent.mkdir(exist_ok=True)
        page.screenshot(path=str(screenshot_before), full_page=True)
        print(f"📸 截图: {screenshot_before}")

        print("\n" + "=" * 80)
        print("  📋 Stealth 模式已启用")
        print("=" * 80)
        print("  • playwright-stealth 已应用")
        print("  • 浏览器指纹已修改")
        print("  • 请在打开的浏览器中登录")
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

                test_content = "🧪 AnimoCerebro Test via Stealth Mode\n#AI #Test"
                tweet_box.fill(test_content)
                time.sleep(2)

                post_button = page.locator('div[data-testid="tweetButton"]')
                post_button.click()
                time.sleep(10)

                screenshot_path = Path("screenshots/x_stealth_post_SUCCESS.png")
                page.screenshot(path=str(screenshot_path), full_page=True)
                print(f"   📸 截图: {screenshot_path.absolute()}")
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
            if browser: browser.close()
            if playwright: playwright.stop()
            print("✅ 已关闭")
        except:
            pass


if __name__ == "__main__":
    main()
