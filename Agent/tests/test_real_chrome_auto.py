#!/usr/bin/env python3
"""
独立 Google Chrome 实例 - 自动发帖测试

使用真实 Google Chrome，独立用户数据目录，自动执行发帖。
"""

import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(project_root))


def main():
    print("\n" + "=" * 80)
    print("  独立 Google Chrome - 自动发帖测试")
    print("=" * 80)

    user_data_dir = Path("/tmp/chrome_isolated_auto")
    user_data_dir.mkdir(exist_ok=True)
    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    if not Path(chrome_path).exists():
        print(f"❌ Chrome 未找到")
        return False

    print(f"\n📂 独立目录: {user_data_dir}")
    print(f"🌐 Chrome: {chrome_path}")

    playwright = None
    context = None
    page = None

    try:
        playwright = sync_playwright().start()

        print("\n🌐 启动独立 Chrome...")
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            executable_path=chrome_path,
            headless=False,
            slow_mo=500,
            viewport={"width": 1920, "height": 1080},
            args=['--no-first-run', '--no-default-browser-check'],
        )

        page = context.new_page()
        print("✅ Chrome 已启动")

        # 打开 X.com
        print("\n📱 打开 X.com...")
        page.goto("https://x.com", wait_until="domcontentloaded", timeout=30000)

        print("\n💡 请在打开的 Chrome 中登录 X 账号")
        print("   脚本将等待 120 秒...")

        # 等待 120 秒供用户登录
        for i in range(120, 0, -5):
            url = page.url
            print(f"   ⏳ {i}s | {url[:60]}...", end='\r')
            time.sleep(5)

        print("\n\n📤 尝试发帖...")

        try:
            tweet_box = page.locator('div[role="textbox"][data-testid="tweetTextarea_0"]')
            tweet_box.wait_for(state="visible", timeout=10000)

            test_content = "🧪 AnimoCerebro Test Post\n#AI #Test"
            tweet_box.fill(test_content)
            time.sleep(2)

            post_button = page.locator('div[data-testid="tweetButton"]')
            post_button.click()
            time.sleep(8)

            screenshot_path = Path("screenshots/x_post_evidence.png")
            screenshot_path.parent.mkdir(exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"✅ 截图: {screenshot_path.absolute()}")

        except Exception as e:
            print(f"⚠️  发帖失败: {e}")

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
            if playwright: playwright.stop()
            print("✅ 测试 Chrome 已关闭")
        except:
            pass


if __name__ == "__main__":
    main()
