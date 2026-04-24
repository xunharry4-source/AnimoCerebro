#!/usr/bin/env python3
"""
通过 CDP 连接到用户已登录的 Chrome

文件用途:
    1. 指导用户启动带远程调试的 Chrome
    2. 通过 CDP 连接到该 Chrome
    3. 自动执行发帖操作

优点:
    - 使用用户真实已登录的 Chrome
    - 完全不会被检测（就是真实的 Chrome）
    - 保留所有 cookies 和登录状态
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
    print("  通过 CDP 连接到您的 Chrome")
    print("=" * 80)

    print("\n📋 使用说明:")
    print("=" * 80)
    print("  第1步: 关闭所有 Chrome 窗口")
    print("  第2步: 在终端运行以下命令启动带调试的 Chrome:")
    print()
    print("  /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\")
    print("    --remote-debugging-port=9222 \\")
    print("    --user-data-dir=/tmp/chrome_debug_profile")
    print()
    print("  第3步: 在打开的 Chrome 中登录 Google/X")
    print("  第4步: 登录后按回车键，脚本将自动连接并发帖")
    print("=" * 80)

    input("\n准备好后按回车键...")

    # 检查 Chrome 是否已在调试模式运行
    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    # 尝试启动带调试的 Chrome
    print("\n🚀 尝试启动带调试的 Chrome...")
    try:
        subprocess.Popen([
            chrome_path,
            '--remote-debugging-port=9222',
            '--user-data-dir=/tmp/chrome_debug_profile',
            '--no-first-run',
            'https://x.com'
        ])
        print("✅ Chrome 已启动（调试模式）")
        print("   请在打开的窗口中登录")
    except Exception as e:
        print(f"⚠️  启动失败: {e}")
        print("   请手动启动带调试的 Chrome")

    print("\n⏳ 等待 60 秒供您登录...")
    time.sleep(60)

    # 通过 CDP 连接
    print("\n🔌 尝试通过 CDP 连接...")
    playwright = None
    browser = None
    context = None
    page = None

    try:
        playwright = sync_playwright().start()

        # 连接到已运行的 Chrome
        browser = playwright.chromium.connect_over_cdp("http://localhost:9222")
        print("✅ CDP 连接成功!")

        # 获取上下文和页面
        contexts = browser.contexts
        if not contexts:
            print("❌ 未找到浏览器上下文")
            return False

        context = contexts[0]
        pages = context.pages

        if pages:
            page = pages[-1]  # 使用最后一个页面
        else:
            page = context.new_page()
            page.goto("https://x.com", wait_until="domcontentloaded")

        print(f"📍 当前 URL: {page.url}")

        # 检查登录状态
        if "home" in page.url or "timeline" in page.url:
            print("✅ 检测到已登录")

            # 自动发帖
            print("\n📤 开始发帖...")
            try:
                tweet_box = page.locator('div[role="textbox"][data-testid="tweetTextarea_0"]')
                tweet_box.wait_for(state="visible", timeout=15000)

                test_content = "🧪 AnimoCerebro Test via CDP\n\nPosted through real Chrome instance.\n#AI #Test"

                print("   📝 填写...")
                tweet_box.fill(test_content)
                time.sleep(2)

                print("   🚀 发布...")
                post_button = page.locator('div[data-testid="tweetButton"]')
                post_button.click()
                time.sleep(10)

                screenshot_path = Path("screenshots/x_cdp_post_SUCCESS.png")
                screenshot_path.parent.mkdir(exist_ok=True)
                page.screenshot(path=str(screenshot_path), full_page=True)
                print(f"   📸 截图: {screenshot_path.absolute()}")
                print("\n✅ 发帖完成!")

            except Exception as e:
                print(f"   ❌ 失败: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("⚠️  未检测到登录")
            print("   请在浏览器中完成登录后重新运行")

        print("\n⏳ 30秒后断开连接...")
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
            print("✅ CDP 连接已断开（Chrome 保持打开）")
        except:
            pass


if __name__ == "__main__":
    main()
