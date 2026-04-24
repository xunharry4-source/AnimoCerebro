#!/usr/bin/env python3
"""
使用用户现有 Chrome 浏览器进行测试

文件用途:
    连接到用户已登录的 Chrome 浏览器，保留所有登录状态和 cookies。
    这样就不需要每次重新登录社交平台。

使用方法:
    1. 关闭所有 Chrome 窗口
    2. 运行此脚本
    3. 脚本会启动带用户数据的 Chrome
    4. 在打开的浏览器中手动登录（只需一次）
    5. 后续运行会自动保持登录状态
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


def get_chrome_user_data_dir():
    """获取 Chrome 用户数据目录"""
    import platform
    system = platform.system()

    if system == "Darwin":  # macOS
        return str(Path.home() / "Library" / "Application Support" / "Google" / "Chrome")
    elif system == "Linux":
        return str(Path.home() / ".config" / "google-chrome")
    elif system == "Windows":
        return str(Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data")
    else:
        raise OSError(f"Unsupported OS: {system}")


def test_with_existing_chrome():
    """使用现有 Chrome 配置测试"""
    print("\n" + "=" * 80)
    print("  使用现有 Chrome 浏览器测试")
    print("=" * 80)

    user_data_dir = get_chrome_user_data_dir()
    print(f"\n📂 Chrome 用户数据目录: {user_data_dir}")

    # 检查目录是否存在
    if not Path(user_data_dir).exists():
        print(f"❌ Chrome 用户数据目录不存在: {user_data_dir}")
        print("   请确保已安装 Google Chrome 浏览器")
        return False

    playwright = None
    browser = None
    context = None
    page = None

    try:
        # 启动 Playwright
        print("\n🚀 正在启动 Playwright...")
        playwright = sync_playwright().start()

        # 使用现有 Chrome 用户数据启动浏览器
        print("🌐 正在启动 Chrome（保留用户数据）...")
        browser = playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            slow_mo=500,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-first-run',
                '--no-default-browser-check',
            ]
        )

        # browser 本身就是 context（persistent context）
        context = browser

        # 创建新页面
        print("📄 正在创建新页面...")
        page = context.new_page()

        # 选择平台
        print("\n请选择要测试的平台:")
        print("  1. X (Twitter)")
        print("  2. Reddit")
        choice = input("\n请选择 (1-2): ").strip()

        if choice == "1":
            # 测试 X
            print("\n📱 正在打开 X.com...")
            page.goto("https://x.com", wait_until="domcontentloaded", timeout=60000)

            print("\n💡 请在浏览器中:")
            print("   1. 如果未登录，请登录您的 X 账号")
            print("   2. 确保能看到首页时间线")
            print("\n⏳ 准备好后按回车键继续...")
            input()

            # 检查当前 URL
            current_url = page.url
            print(f"\n📍 当前 URL: {current_url}")

            if "login" in current_url or "signin" in current_url:
                print("⚠️  检测到仍在登录页面")
                print("   请完成登录后再按回车")
                input()

            # 发布测试帖子
            print("\n📤 正在发布测试帖子...")

            # 找到推文输入框
            tweet_box = page.locator('div[role="textbox"][data-testid="tweetTextarea_0"]')
            if tweet_box.count() > 0:
                test_content = "🧪 Testing AnimoCerebro Self-Promotion Agent - Automated Test\n\n#AI #ML #OpenSource #Test"
                tweet_box.fill(test_content)
                print(f"   ✅ 已填写内容: {test_content[:50]}...")

                # 点击发布按钮
                post_button = page.locator('div[data-testid="tweetButton"]')
                if post_button.count() > 0:
                    print("   🚀 正在点击发布按钮...")
                    post_button.click()

                    # 等待发布完成
                    time.sleep(5)

                    # 截图
                    screenshot_path = Path("screenshots/x_post_test.png")
                    screenshot_path.parent.mkdir(exist_ok=True)
                    page.screenshot(path=str(screenshot_path))
                    print(f"   📸 截图保存: {screenshot_path}")

                    print("\n✅ 发帖操作完成!")
                    print("   请在浏览器中确认帖子是否成功发布")
                else:
                    print("   ⚠️  未找到发布按钮")
            else:
                print("   ⚠️  未找到推文输入框")
                print("   可能未正确登录或页面结构已变化")

        elif choice == "2":
            # 测试 Reddit
            subreddit = input("\n请输入 Subreddit (如 MachineLearning): ").strip()
            if not subreddit:
                subreddit = "test"

            print(f"\n📱 正在打开 r/{subreddit}...")
            page.goto(f"https://www.reddit.com/r/{subreddit}/submit", wait_until="domcontentloaded", timeout=60000)

            print("\n💡 请在浏览器中:")
            print("   1. 如果未登录，请登录您的 Reddit 账号")
            print("   2. 手动填写标题和内容并发布")
            print("\n⏳ 完成后按回车键继续...")
            input()

            # 截图
            screenshot_path = Path("screenshots/reddit_post_test.png")
            screenshot_path.parent.mkdir(exist_ok=True)
            page.screenshot(path=str(screenshot_path))
            print(f"   📸 截图保存: {screenshot_path}")

        else:
            print("无效选择")
            return False

        # 保持浏览器打开
        print("\n🔍 浏览器将保持打开，您可以检查结果")
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
        # 清理
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
        success = test_with_existing_chrome()
        if success:
            print("\n✅ 测试完成")
        else:
            print("\n❌ 测试失败")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
