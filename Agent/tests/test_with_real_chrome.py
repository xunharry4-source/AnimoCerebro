#!/usr/bin/env python3
"""
使用用户真实 Chrome 配置进行发帖测试

文件用途:
    直接使用用户的 Chrome 用户数据目录，保留所有登录状态（包括 Google、X、Reddit）。
    这样就不需要每次重新登录。

重要:
    - 必须先关闭所有 Chrome 窗口
    - 脚本会使用您的真实 Chrome 配置
    - 所有 cookies 和登录状态都会被保留
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
    print("  使用真实 Chrome 配置进行发帖测试")
    print("=" * 80)

    # macOS Chrome 用户数据目录
    user_data_dir = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"

    if not user_data_dir.exists():
        print(f"❌ Chrome 用户数据目录不存在: {user_data_dir}")
        return False

    print(f"\n📂 Chrome 用户数据目录: {user_data_dir}")
    print("⚠️  重要: 此脚本会使用您的真实 Chrome 配置")

    # Chrome 可执行文件路径
    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if not Path(chrome_path).exists():
        print(f"❌ Chrome 未找到: {chrome_path}")
        return False

    print(f"🌐 Chrome 路径: {chrome_path}")

    print("\n" + "=" * 80)
    print("  📋 使用前准备")
    print("=" * 80)
    print("  1. 请先关闭所有 Chrome 窗口")
    print("  2. 确保您已在 Chrome 中登录 Google 账号")
    print("  3. 确保您已在 X.com 和 Reddit 登录")
    print("  4. 准备好后按回车键继续...")
    print("=" * 80)
    input("\n按回车键开始...")

    playwright = None
    context = None
    page = None

    try:
        print("\n🚀 启动 Playwright...")
        playwright = sync_playwright().start()

        print("🌐 启动 Chrome（使用您的真实配置）...")
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            executable_path=chrome_path,
            headless=False,
            slow_mo=500,
            viewport={"width": 1920, "height": 1080},
            args=[
                '--no-first-run',
                '--no-default-browser-check',
            ],
        )

        print("✅ Chrome 已启动（使用您的真实配置）")

        # 获取所有现有页面
        pages = context.pages
        if pages:
            page = pages[0]
            print(f"📄 使用现有标签页: {page.url}")
        else:
            page = context.new_page()
            print("📄 创建新标签页")

        # 选择平台
        print("\n请选择要测试的平台:")
        print("  1. X (Twitter)")
        print("  2. Reddit")
        choice = input("\n请选择 (1-2): ").strip() or "1"

        if choice == "1":
            # X 测试
            print("\n📱 导航到 X.com...")
            page.goto("https://x.com", wait_until="domcontentloaded", timeout=30000)

            # 检查登录状态
            current_url = page.url
            print(f"📍 当前 URL: {current_url}")

            if "login" in current_url or "signin" in current_url:
                print("\n⚠️  检测到未登录")
                print("   请在浏览器中登录 X 账号")
                print("   登录后按回车键继续...")
                input()
            else:
                print("✅ 检测到已登录状态")

            # 等待一下
            time.sleep(3)

            # 发帖
            print("\n📤 发布测试帖子...")

            try:
                tweet_box = page.locator('div[role="textbox"][data-testid="tweetTextarea_0"]')
                tweet_box.wait_for(state="visible", timeout=10000)

                test_content = "🧪 AnimoCerebro Self-Promotion Agent Test\n\nAutomated posting test.\nGitHub: https://github.com/xunharry4-source/AnimoCerebro-external\n\n#AI #Test"

                print("   📝 填写内容...")
                tweet_box.fill(test_content)
                time.sleep(2)

                print("   🚀 点击发布...")
                post_button = page.locator('div[data-testid="tweetButton"]')
                post_button.wait_for(state="visible", timeout=5000)
                post_button.click()

                time.sleep(8)

                # 截图
                screenshot_path = Path("screenshots/x_post_final.png")
                screenshot_path.parent.mkdir(exist_ok=True)
                page.screenshot(path=str(screenshot_path), full_page=True)
                print(f"   📸 截图: {screenshot_path.absolute()}")

                print("\n✅ 发帖完成!")
                print("   请在浏览器中确认帖子是否成功发布")

            except Exception as e:
                print(f"   ⚠️  自动发帖失败: {e}")
                print("   请在浏览器中手动发帖")

        elif choice == "2":
            # Reddit 测试
            subreddit = input("\nSubreddit: ").strip() or "test"
            print(f"\n📱 导航到 r/{subreddit}/submit...")
            page.goto(f"https://www.reddit.com/r/{subreddit}/submit", wait_until="domcontentloaded", timeout=30000)

            print("\n💡 请在浏览器中手动发帖")
            print("   完成后按回车键...")
            input()

            screenshot_path = Path("screenshots/reddit_post_final.png")
            screenshot_path.parent.mkdir(exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"📸 截图: {screenshot_path.absolute()}")

        print("\n⏳ 浏览器将保持打开，您可以检查结果")
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
            if page:
                page.close()
            if context:
                context.close()
            if playwright:
                playwright.stop()
        except:
            pass


if __name__ == "__main__":
    try:
        success = main()
        if success:
            print("\n✅ 测试完成")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
