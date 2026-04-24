#!/usr/bin/env python3
"""
连接到已运行的 Chrome 浏览器

文件用途:
    通过 CDP (Chrome DevTools Protocol) 连接到用户已打开的 Chrome 浏览器。
    这样可以直接使用用户已登录的状态，无需重新启动浏览器。

使用方法:
    1. 启动 Chrome 并启用远程调试:
       /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
    2. 在 Chrome 中登录您的社交账号
    3. 运行此脚本
    4. 脚本会连接到您的 Chrome 并执行发帖测试
"""

import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

# 添加项目根目录和 src 目录到 Python 路径
project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(project_root))


def connect_to_running_chrome():
    """连接到已运行的 Chrome"""
    print("\n" + "=" * 80)
    print("  连接到已运行的 Chrome 浏览器")
    print("=" * 80)

    print("\n📋 使用说明:")
    print("   1. 请先启动 Chrome 并启用远程调试:")
    print("      /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222")
    print("   2. 在 Chrome 中登录 X 或 Reddit")
    print("   3. 按回车键继续...")
    input()

    playwright = None
    browser = None
    context = None
    page = None

    try:
        # 启动 Playwright
        print("\n🚀 正在启动 Playwright...")
        playwright = sync_playwright().start()

        # 连接到已运行的 Chrome
        print("🔌 正在连接到 Chrome (端口 9222)...")
        browser = playwright.chromium.connect_over_cdp("http://localhost:9222")

        # 获取默认上下文
        contexts = browser.contexts
        if not contexts:
            print("❌ 未找到浏览器上下文")
            return False

        context = contexts[0]

        # 获取所有页面
        pages = context.pages
        if pages:
            page = pages[0]
        else:
            # 创建新页面
            page = context.new_page()

        print(f"✅ 连接成功！当前有 {len(pages)} 个标签页")
        print(f"   当前 URL: {page.url}")

        # 选择平台
        print("\n请选择要测试的平台:")
        print("  1. X (Twitter)")
        print("  2. Reddit")
        choice = input("\n请选择 (1-2): ").strip()

        if choice == "1":
            # 测试 X
            print("\n📱 正在导航到 X.com...")
            page.goto("https://x.com", wait_until="domcontentloaded", timeout=30000)

            # 等待用户确认已登录
            print("\n💡 请确认已在浏览器中登录 X 账号")
            print("   按回车键继续发帖...")
            input()

            # 发布测试帖子
            print("\n📤 正在发布测试帖子...")

            # 尝试找到推文输入框
            try:
                tweet_box = page.locator('div[role="textbox"][data-testid="tweetTextarea_0"]')
                tweet_box.wait_for(state="visible", timeout=10000)

                test_content = "🧪 Testing AnimoCerebro Self-Promotion Agent\n\nAutomated test from AI brain project.\nGitHub: https://github.com/xunharry4-source/AnimoCerebro-external\n\n#AI #ML #OpenSource #Test"
                tweet_box.fill(test_content)
                print(f"   ✅ 已填写内容")

                # 点击发布按钮
                post_button = page.locator('div[data-testid="tweetButton"]')
                post_button.wait_for(state="visible", timeout=5000)
                print("   🚀 正在点击发布按钮...")
                post_button.click()

                # 等待发布完成
                time.sleep(5)

                # 截图
                screenshot_path = Path("screenshots/x_post_success.png")
                screenshot_path.parent.mkdir(exist_ok=True)
                page.screenshot(path=str(screenshot_path))
                print(f"   📸 截图保存: {screenshot_path}")

                print("\n✅ 发帖操作完成!")
                print("   请在浏览器中确认帖子是否成功发布")

            except Exception as e:
                print(f"   ⚠️  自动发帖失败: {e}")
                print("   请在浏览器中手动发帖")

        elif choice == "2":
            # 测试 Reddit
            subreddit = input("\n请输入 Subreddit (如 MachineLearning): ").strip()
            if not subreddit:
                subreddit = "test"

            print(f"\n📱 正在导航到 r/{subreddit}/submit...")
            page.goto(f"https://www.reddit.com/r/{subreddit}/submit", wait_until="domcontentloaded", timeout=30000)

            print("\n💡 请在浏览器中手动填写并发布帖子")
            print("   完成后按回车键继续...")
            input()

            # 截图
            screenshot_path = Path("screenshots/reddit_post_success.png")
            screenshot_path.parent.mkdir(exist_ok=True)
            page.screenshot(path=str(screenshot_path))
            print(f"   📸 截图保存: {screenshot_path}")

        else:
            print("无效选择")
            return False

        print("\n🔍 保持连接，您可以检查结果")
        print("   按 Ctrl+C 退出")

        while True:
            time.sleep(1)

        return True

    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断")
        return True
    except Exception as e:
        print(f"\n❌ 异常: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        try:
            if browser:
                browser.close()
            if playwright:
                playwright.stop()
        except:
            pass


if __name__ == "__main__":
    try:
        success = connect_to_running_chrome()
        if success:
            print("\n✅ 测试完成")
        else:
            print("\n❌ 测试失败")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
