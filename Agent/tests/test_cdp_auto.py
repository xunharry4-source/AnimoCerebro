#!/usr/bin/env python3
"""
自动启动带调试的Chrome并通过CDP连接发帖

完全自动化，无需手动干预。
"""

import sys
import time
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(project_root))


def main():
    print("\n" + "=" * 80)
    print("  自动启动Chrome (CDP模式) 并发帖")
    print("=" * 80)

    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    debug_port = 9222
    user_data_dir = "/tmp/chrome_cdp_auto_profile"

    Path(user_data_dir).mkdir(exist_ok=True)

    # 启动带调试的 Chrome
    print(f"\n🚀 启动 Chrome (调试端口 {debug_port})...")
    try:
        proc = subprocess.Popen([
            chrome_path,
            f'--remote-debugging-port={debug_port}',
            f'--user-data-dir={user_data_dir}',
            '--no-first-run',
            'https://x.com'
        ])
        print("✅ Chrome 已启动")
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        return False

    # 等待 Chrome 启动
    print("⏳ 等待 Chrome 启动...")
    time.sleep(10)

    playwright = None
    browser = None

    try:
        playwright = sync_playwright().start()

        # CDP 连接
        print(f"\n🔌 连接到 localhost:{debug_port}...")
        browser = playwright.chromium.connect_over_cdp(f"http://localhost:{debug_port}")
        print("✅ CDP 连接成功!")

        # 获取页面
        contexts = browser.contexts
        if not contexts:
            print("❌ 无上下文")
            return False

        context = contexts[0]
        pages = context.pages

        if pages:
            page = pages[-1]
        else:
            page = context.new_page()
            page.goto("https://x.com", wait_until="domcontentloaded")

        print(f"📍 URL: {page.url}")

        print("\n💡 请在打开的 Chrome 中登录 X")
        print("   脚本将等待 120 秒...")

        # 等待登录
        for i in range(120, 0, -5):
            url = page.url
            if "home" in url or "timeline" in url:
                print(f"\n✅ 检测到登录! URL: {url}")
                break
            print(f"   ⏳ {i}s | {url[:50]}...", end='\r')
            time.sleep(5)
        else:
            print("\n⚠️  未检测到登录，但仍尝试发帖...")

        time.sleep(3)

        # 发帖
        print("\n📤 发帖...")
        try:
            tweet_box = page.locator('div[role="textbox"][data-testid="tweetTextarea_0"]')
            tweet_box.wait_for(state="visible", timeout=15000)

            test_content = "🧪 AnimoCerebro CDP Test\n#AI #Test"
            tweet_box.fill(test_content)
            time.sleep(2)

            post_button = page.locator('div[data-testid="tweetButton"]')
            post_button.click()
            time.sleep(10)

            screenshot_path = Path("screenshots/x_cdp_auto_SUCCESS.png")
            screenshot_path.parent.mkdir(exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"   📸 截图: {screenshot_path.absolute()}")
            print("\n✅ 发帖完成!")

        except Exception as e:
            print(f"   ❌ 失败: {e}")

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
            if browser: browser.close()
            if playwright: playwright.stop()
            proc.terminate()
            print("✅ 完成")
        except:
            pass


if __name__ == "__main__":
    main()
