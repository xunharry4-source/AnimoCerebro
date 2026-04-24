#!/usr/bin/env python3
"""
真实发帖测试 - 打开浏览器让用户手动登录

文件用途:
    启动浏览器，让用户手动登录社交平台，然后自动执行发帖操作。

使用方法:
    1. 运行此脚本
    2. 在打开的浏览器中手动登录 X 或 Reddit
    3. 按回车键继续
    4. 脚本会自动发布测试帖子
"""

import sys
from pathlib import Path

# 添加项目根目录和 src 目录到 Python 路径
project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(project_root))

from Agent.browser_automation import BrowserAutomationManager


def test_real_x_posting():
    """测试真实的 X 发帖"""
    print("\n" + "=" * 80)
    print("  真实 X (Twitter) 发帖测试")
    print("=" * 80)

    # 创建浏览器管理器
    browser_manager = BrowserAutomationManager(headless=False, slow_mo=500)

    try:
        # 启动浏览器
        print("\n🚀 正在启动 Chromium 浏览器...")
        browser_manager.start_browser("chromium")
        print("✅ 浏览器已启动")

        # 导航到 X 登录页面
        print("\n📱 正在打开 X.com 登录页面...")
        browser_manager.page.goto("https://x.com/login", wait_until="networkidle")
        print("💡 请在打开的浏览器窗口中:")
        print("   1. 输入您的 X 账号和密码")
        print("   2. 完成任何 CAPTCHA 验证")
        print("   3. 确保已成功登录（能看到首页时间线）")
        print("\n⏳ 准备好后，请按回车键继续...")
        input()

        # 检查是否已登录
        page = browser_manager.page
        if page:
            current_url = page.url
            print(f"\n📍 当前 URL: {current_url}")

            if "login" in current_url or "signin" in current_url:
                print("⚠️  检测到仍在登录页面，请确认已完成登录")
                print("   如果已登录，请按回车继续；否则请完成登录后再按回车")
                input()

        # 发布测试帖子
        print("\n📤 正在发布测试帖子到 X...")
        test_content = f"🧪 Testing AnimoCerebro Self-Promotion Agent\n\nThis is an automated test post from the AnimoCerebro AI brain project.\n\nProject: https://github.com/xunharry4-source/AnimoCerebro-external\n\n#AI #MachineLearning #OpenSource #Test"

        result = browser_manager.post_to_x(content=test_content)

        if result["success"]:
            print("\n✅ 发帖成功!")
            print(f"   消息: {result.get('message', 'N/A')}")
            if result.get("url"):
                print(f"   帖子链接: {result['url']}")

            # 截图作为证据
            screenshot_path = browser_manager.take_screenshot("x_post_success")
            if screenshot_path:
                print(f"   截图保存: {screenshot_path}")

            return True
        else:
            print(f"\n❌ 发帖失败: {result.get('error')}")
            print("\n💡 提示:")
            print("   - 如果遇到错误，请在浏览器中手动尝试发帖")
            print("   - 检查是否遇到 CAPTCHA 或其他验证")
            return False

    except Exception as e:
        print(f"\n❌ 异常: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # 保持浏览器打开，让用户查看结果
        print("\n🔍 浏览器将保持打开 30 秒，以便您查看结果...")
        import time
        time.sleep(30)
        browser_manager.stop_browser()


def test_real_reddit_posting():
    """测试真实的 Reddit 发帖"""
    print("\n" + "=" * 80)
    print("  真实 Reddit 发帖测试")
    print("=" * 80)

    # 创建浏览器管理器
    browser_manager = BrowserAutomationManager(headless=False, slow_mo=500)

    try:
        # 启动浏览器
        print("\n🚀 正在启动 Chromium 浏览器...")
        browser_manager.start_browser("chromium")
        print("✅ 浏览器已启动")

        # 导航到 Reddit 登录页面
        print("\n📱 正在打开 Reddit.com 登录页面...")
        browser_manager.page.goto("https://www.reddit.com/login", wait_until="networkidle")
        print("💡 请在打开的浏览器窗口中:")
        print("   1. 输入您的 Reddit 账号和密码")
        print("   2. 完成任何 CAPTCHA 验证")
        print("   3. 确保已成功登录（能看到首页）")
        print("\n⏳ 准备好后，请按回车键继续...")
        input()

        # 检查是否已登录
        page = browser_manager.page
        if page:
            current_url = page.url
            print(f"\n📍 当前 URL: {current_url}")

        # 询问要发布到哪个 subreddit
        subreddit = input("\n请输入要发布的 Subreddit (如 MachineLearning): ").strip()
        if not subreddit:
            subreddit = "test"

        # 输入帖子标题和内容
        title = input("\n请输入帖子标题: ").strip()
        if not title:
            title = "🧪 [Test] AnimoCerebro Self-Promotion Agent Test"

        print("\n请输入帖子内容 (输入 END 结束):")
        content_lines = []
        while True:
            line = input()
            if line.strip() == "END":
                break
            content_lines.append(line)
        content = "\n".join(content_lines)

        if not content:
            content = """This is an automated test post from the AnimoCerebro AI brain project.

AnimoCerebro provides an external brain for autonomous agents with a nine-question cognitive cycle (Q1-Q9).

GitHub: https://github.com/xunharry4-source/AnimoCerebro-external

#Test #Automated"""

        # 发布帖子
        print(f"\n📤 正在发布到 r/{subreddit}...")
        result = browser_manager.post_to_reddit(
            subreddit=subreddit,
            title=title,
            content=content,
            post_type="text"
        )

        if result["success"]:
            print("\n✅ 发帖成功!")
            print(f"   消息: {result.get('message', 'N/A')}")
            if result.get("url"):
                print(f"   帖子链接: {result['url']}")

            # 截图作为证据
            screenshot_path = browser_manager.take_screenshot("reddit_post_success")
            if screenshot_path:
                print(f"   截图保存: {screenshot_path}")

            return True
        else:
            print(f"\n❌ 发帖失败: {result.get('error')}")
            return False

    except Exception as e:
        print(f"\n❌ 异常: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # 保持浏览器打开
        print("\n🔍 浏览器将保持打开 30 秒，以便您查看结果...")
        import time
        time.sleep(30)
        browser_manager.disable()


def main():
    """主函数"""
    print("\n" + "🌐" * 40)
    print("  Self-Promotion Agent - 真实发帖测试")
    print("🌐" * 40)

    print("\n请选择要测试的平台:")
    print("  1. X (Twitter)")
    print("  2. Reddit")
    print("  3. 两者都测试")

    choice = input("\n请选择 (1-3): ").strip()

    if choice == "1":
        success = test_real_x_posting()
    elif choice == "2":
        success = test_real_reddit_posting()
    elif choice == "3":
        success_x = test_real_x_posting()
        print("\n" + "-" * 80)
        success_reddit = test_real_reddit_posting()
        success = success_x and success_reddit
    else:
        print("无效选择")
        return

    if success:
        print("\n" + "=" * 80)
        print("  ✅ 真实发帖测试完成!")
        print("=" * 80)
        print("\n📋 物理证据:")
        print("  • 浏览器自动化操作记录")
        print("  • 帖子截图（保存在 screenshots/ 目录）")
        print("  • 审计日志（可通过 get_audit_log() 查询）")
    else:
        print("\n" + "=" * 80)
        print("  ⚠️  发帖测试未完全成功")
        print("=" * 80)
        print("\n可能的原因:")
        print("  • 登录未完成或会话过期")
        print("  • 遇到 CAPTCHA 需要人工处理")
        print("  • 社区规则限制（如 karma 要求、新账号限制等）")
        print("  • 网络连接问题")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断，退出")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ 未预期的错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
