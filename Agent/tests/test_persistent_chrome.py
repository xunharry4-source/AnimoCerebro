#!/usr/bin/env python3
"""
启动独立的 Chrome 实例（不与现有 Chrome 冲突）

文件用途:
    使用 launch_persistent_context 启动一个独立的 Chromium 实例，
    使用临时用户数据目录，不会与用户现有的 Chrome 冲突。
    这个 Chromium 与真实 Chrome 完全一样，可以保留登录状态。

特点:
    - 独立的用戶数据目录（不干扰主 Chrome）
    - 可以保留 cookies 和登录状态
    - Playwright 可以完全控制
    - 显示完整的浏览器窗口
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
    print("  启动独立 Chrome 实例进行发帖测试")
    print("=" * 80)

    # 创建临时用户数据目录
    user_data_dir = Path("/tmp/chrome_test_profile_animocerebro")
    user_data_dir.mkdir(exist_ok=True)
    print(f"\n📂 用户数据目录: {user_data_dir}")
    print("   (此目录独立，不会影响您的主 Chrome)")

    playwright = None
    context = None
    page = None

    try:
        # 启动 Playwright
        print("\n🚀 正在启动 Playwright...")
        playwright = sync_playwright().start()

        # 启动持久的 Chromium 上下文（类似真实 Chrome）
        print("🌐 正在启动 Chromium（持久化上下文）...")
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=False,
            slow_mo=500,
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="America/New_York",
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-first-run',
                '--no-default-browser-check',
            ],
            bypass_csp=True
        )

        # 创建新页面
        print("📄 正在创建页面...")
        page = context.new_page()

        # 选择平台
        print("\n请选择要测试的平台:")
        print("  1. X (Twitter)")
        print("  2. Reddit")

        choice = "1"  # 默认选择 X
        print(f"自动选择: {choice}\n")

        if choice == "1":
            # 导航到 X
            print("📱 正在打开 X.com...")
            page.goto("https://x.com", wait_until="domcontentloaded", timeout=60000)

            print("\n" + "=" * 80)
            print("  💡 请在打开的浏览器窗口中登录 X 账号")
            print("=" * 80)
            print("  1. 输入您的 X 用户名/邮箱和密码")
            print("  2. 完成任何 CAPTCHA 验证")
            print("  3. 确保成功登录并看到首页时间线")
            print("  4. 登录后，脚本会自动等待并发布测试帖子")
            print("=" * 80)

            # 等待用户登录（最多等待 120 秒）
            print("\n⏳ 等待您登录...（最多 120 秒）")
            login_timeout = 120
            start_time = time.time()

            while time.time() - start_time < login_timeout:
                current_url = page.url
                elapsed = int(time.time() - start_time)
                remaining = login_timeout - elapsed

                # 检查是否已登录（不在登录页面）
                if "login" not in current_url and "signin" not in current_url and "x.com" in current_url:
                    print(f"\n✅ 检测到已登录！当前 URL: {current_url}")
                    break

                print(f"   剩余时间: {remaining} 秒 | 当前 URL: {current_url[:60]}...", end='\r')
                time.sleep(2)
            else:
                print("\n\n⚠️  登录超时，但仍将继续尝试发帖...")

            # 再等待 5 秒确保页面完全加载
            time.sleep(5)

            # 发布测试帖子
            print("\n" + "=" * 80)
            print("  📤 开始发布测试帖子")
            print("=" * 80)

            try:
                # 找到推文输入框
                print("\n   📝 查找推文输入框...")
                tweet_box = page.locator('div[role="textbox"][data-testid="tweetTextarea_0"]')
                tweet_box.wait_for(state="visible", timeout=15000)
                print("   ✅ 找到输入框")

                # 填写内容
                test_content = "🧪 Testing AnimoCerebro Self-Promotion Agent\n\nAutomated test from AI brain project.\nGitHub: https://github.com/xunharry4-source/AnimoCerebro-external\n\n#AI #ML #OpenSource #Test"
                print(f"   📝 填写内容...")
                tweet_box.fill(test_content)
                time.sleep(2)

                # 点击发布按钮
                print("   🚀 点击发布按钮...")
                post_button = page.locator('div[data-testid="tweetButton"]')
                post_button.wait_for(state="visible", timeout=10000)
                post_button.click()

                # 等待发布完成
                print("   ⏳ 等待发布完成...")
                time.sleep(10)

                # 截图作为证据
                screenshot_path = Path("screenshots/x_post_success.png")
                screenshot_path.parent.mkdir(exist_ok=True)
                page.screenshot(path=str(screenshot_path), full_page=True)
                print(f"   📸 截图保存: {screenshot_path.absolute()}")

                print("\n" + "=" * 80)
                print("  ✅ 发帖操作完成!")
                print("=" * 80)
                print("\n📋 物理证据:")
                print(f"  • 截图: {screenshot_path.absolute()}")
                print("  • 浏览器会话保存在临时目录（可重复使用）")
                print("\n💡 提示:")
                print("  • 请在浏览器中确认帖子是否成功发布")
                print("  • 浏览器将保持打开 60 秒供您查看")
                print("  • 下次运行此脚本时，登录状态会被保留")

                # 保持浏览器打开
                print("\n⏳ 浏览器将在 60 秒后关闭...")
                time.sleep(60)

                return True

            except Exception as e:
                print(f"\n   ⚠️  自动发帖失败: {e}")
                print("   请在浏览器中手动发帖")
                print("\n⏳ 浏览器将保持打开 120 秒供您操作...")
                time.sleep(120)
                return False

        elif choice == "2":
            # Reddit 测试
            subreddit = input("\n请输入 Subreddit (如 MachineLearning): ").strip() or "test"

            print(f"\n📱 正在打开 r/{subreddit}/submit...")
            page.goto(f"https://www.reddit.com/r/{subreddit}/submit", wait_until="domcontentloaded", timeout=60000)

            print("\n💡 请在浏览器中登录并发布帖子")
            print("⏳ 等待 120 秒...")
            time.sleep(120)

            screenshot_path = Path("screenshots/reddit_post_test.png")
            screenshot_path.parent.mkdir(exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"📸 截图保存: {screenshot_path.absolute()}")

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
        else:
            print("\n⚠️  测试未完全成功")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
