#!/usr/bin/env python3
"""
自动启动 Playwright Chromium 并测试发帖

文件用途:
    自动启动带 CDP 端口的 Playwright Chromium，
    让用户手动登录，然后自动执行发帖操作。
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


def main():
    """主函数"""
    print("\n" + "=" * 80)
    print("  自动启动 Chromium 并测试发帖")
    print("=" * 80)

    playwright = None
    browser = None
    context = None
    page = None

    try:
        # 启动 Playwright
        print("\n🚀 正在启动 Playwright...")
        playwright = sync_playwright().start()

        # 启动 Chromium（非无头模式，显示浏览器窗口）
        print("🌐 正在启动 Chromium 浏览器...")
        browser = playwright.chromium.launch(
            headless=False,
            slow_mo=500,
            args=[
                '--disable-blink-features=AutomationControlled',
            ]
        )

        # 创建上下文
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # 创建页面
        page = context.new_page()

        # 选择平台
        print("\n请选择要测试的平台:")
        print("  1. X (Twitter)")
        print("  2. Reddit")

        # 自动选择 X
        choice = "1"
        print(f"\n自动选择: {choice}")

        if choice == "1":
            # 导航到 X
            print("\n📱 正在打开 X.com...")
            page.goto("https://x.com", wait_until="domcontentloaded", timeout=60000)

            print("\n💡 请在打开的浏览器窗口中:")
            print("   1. 登录您的 X 账号")
            print("   2. 完成任何 CAPTCHA 验证")
            print("   3. 确保能看到首页时间线")
            print("\n⏳ 等待 90 秒供您登录...")

            # 等待用户登录
            for i in range(90, 0, -5):
                print(f"   剩余时间: {i} 秒...", end='\r')
                time.sleep(5)
            print("\n   ✅ 等待完成")

            # 检查当前 URL
            current_url = page.url
            print(f"\n📍 当前 URL: {current_url}")

            if "login" in current_url or "signin" in current_url:
                print("⚠️  检测到仍在登录页面，再等待 30 秒...")
                time.sleep(30)

            # 发布测试帖子
            print("\n📤 正在发布测试帖子...")

            try:
                # 找到推文输入框
                tweet_box = page.locator('div[role="textbox"][data-testid="tweetTextarea_0"]')
                tweet_box.wait_for(state="visible", timeout=15000)

                test_content = "🧪 Testing AnimoCerebro Self-Promotion Agent\n\nAutomated test from AI brain project.\nGitHub: https://github.com/xunharry4-source/AnimoCerebro-external\n\n#AI #ML #OpenSource #Test"

                print("   📝 填写内容...")
                tweet_box.fill(test_content)

                # 等待一下让内容生效
                time.sleep(2)

                # 点击发布按钮
                print("   🚀 点击发布按钮...")
                post_button = page.locator('div[data-testid="tweetButton"]')
                post_button.wait_for(state="visible", timeout=10000)
                post_button.click()

                # 等待发布完成
                print("   ⏳ 等待发布完成...")
                time.sleep(8)

                # 截图作为证据
                screenshot_path = Path("screenshots/x_post_success.png")
                screenshot_path.parent.mkdir(exist_ok=True)
                page.screenshot(path=str(screenshot_path))
                print(f"   📸 截图保存: {screenshot_path}")

                print("\n✅ 发帖操作完成!")
                print("   请在浏览器中确认帖子是否成功发布")

                # 保持浏览器打开以便查看
                print("\n🔍 浏览器将保持打开 60 秒...")
                time.sleep(60)

                return True

            except Exception as e:
                print(f"   ⚠️  自动发帖失败: {e}")
                print("   请在浏览器中手动发帖")
                print("\n🔍 浏览器将保持打开 120 秒供您操作...")
                time.sleep(120)
                return False

        elif choice == "2":
            # Reddit 测试
            subreddit = "test"
            print(f"\n📱 正在打开 r/{subreddit}/submit...")
            page.goto(f"https://www.reddit.com/r/{subreddit}/submit", wait_until="domcontentloaded", timeout=60000)

            print("\n💡 请在浏览器中:")
            print("   1. 登录 Reddit")
            print("   2. 手动填写并发布帖子")
            print("\n⏳ 等待 120 秒供您操作...")
            time.sleep(120)

            # 截图
            screenshot_path = Path("screenshots/reddit_post_test.png")
            screenshot_path.parent.mkdir(exist_ok=True)
            page.screenshot(path=str(screenshot_path))
            print(f"   📸 截图保存: {screenshot_path}")

            return True

        else:
            print("无效选择")
            return False

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
            if page:
                page.close()
            if context:
                context.close()
            if browser:
                browser.close()
            if playwright:
                playwright.stop()
        except:
            pass


if __name__ == "__main__":
    try:
        success = main()
        if success:
            print("\n✅ 测试完成")
        else:
            print("\n⚠️  测试未完全成功")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
