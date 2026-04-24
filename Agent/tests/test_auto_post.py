#!/usr/bin/env python3
"""
完全自动化的发帖测试 - 无需手动登录

文件用途:
    使用 Playwright 自动完成登录和发帖流程，无需人工干预。
    通过浏览器自动化模拟真实用户操作。

注意:
    由于 X/Twitter 有强大的反机器人保护，此脚本主要用于验证
    浏览器自动化功能是否正常工作。实际生产环境需要使用 API。
"""

import sys
import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

# 添加项目根目录和 src 目录到 Python 路径
project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(project_root))


def get_chrome_executable_path():
    """获取 macOS 上 Google Chrome 的可执行文件路径"""
    chrome_paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for path in chrome_paths:
        if Path(path).exists():
            return path
    raise FileNotFoundError("Google Chrome not found.")


def test_automated_posting():
    """自动化发帖测试"""
    print("\n" + "=" * 80)
    print("  完全自动化发帖测试")
    print("=" * 80)

    # 创建临时用户数据目录
    user_data_dir = Path("/tmp/chrome_profile_auto_test")
    user_data_dir.mkdir(exist_ok=True)
    print(f"\n📂 用户数据目录: {user_data_dir}")

    # 获取 Chrome 路径
    try:
        chrome_path = get_chrome_executable_path()
        print(f"🌐 Chrome 路径: {chrome_path}")
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return False

    playwright = None
    context = None
    page = None

    try:
        # 启动 Playwright
        print("\n🚀 启动 Playwright...")
        playwright = sync_playwright().start()

        # 启动 Chrome
        print("🌐 启动 Google Chrome...")
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            executable_path=chrome_path,
            headless=False,
            slow_mo=1000,  # 更慢的操作速度，更像真人
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-first-run',
            ],
            bypass_csp=True,
        )

        page = context.new_page()

        # 启用 stealth 模式
        print("🛡️  启用反检测措施...")
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        # 导航到 X.com
        print("\n📱 导航到 X.com...")
        page.goto("https://x.com", wait_until="networkidle", timeout=60000)
        print("✅ 页面加载完成")

        # 截图初始状态
        screenshot_path = Path("screenshots/x_initial.png")
        screenshot_path.parent.mkdir(exist_ok=True)
        page.screenshot(path=str(screenshot_path))
        print(f"📸 初始截图: {screenshot_path}")

        print("\n" + "=" * 80)
        print("  💡 自动化登录说明")
        print("=" * 80)
        print("  由于 X/Twitter 有强大的反机器人保护，完全自动化登录需要:")
        print("  1. 有效的账号凭据（用户名/邮箱 + 密码）")
        print("  2. 可能需要处理 2FA/CAPTCHA")
        print("  3. 可能触发安全验证")
        print("\n  建议方案:")
        print("  • 方案 A: 在 .env 文件中配置 X_USERNAME 和 X_PASSWORD")
        print("  • 方案 B: 手动登录后，脚本会保存 cookies 供下次使用")
        print("=" * 80)

        # 检查是否有保存的 cookies
        cookies_file = Path("browser_sessions/x_cookies.json")
        if cookies_file.exists():
            print(f"\n🍪 发现保存的 cookies: {cookies_file}")
            with open(cookies_file, 'r') as f:
                cookies = json.load(f)
            context.add_cookies(cookies)
            print("✅ Cookies 已加载")

            # 刷新页面以应用 cookies
            page.reload(wait_until="networkidle")
            time.sleep(5)

            # 检查是否已登录
            if "home" in page.url:
                print("✅ 通过 cookies 自动登录成功!")
            else:
                print("⚠️  Cookies 已过期，需要重新登录")
        else:
            print("\n⚠️  未找到保存的 cookies")

        # 等待一段时间让用户观察
        print("\n⏳ 浏览器将保持打开 90 秒...")
        print("   您可以:")
        print("   1. 手动登录账号")
        print("   2. 观察浏览器行为")
        print("   3. 登录后按 Ctrl+C 继续发帖测试")

        try:
            for i in range(90, 0, -5):
                print(f"   剩余: {i} 秒 | URL: {page.url[:60]}...", end='\r')
                time.sleep(5)
        except KeyboardInterrupt:
            print("\n\n⌨️  用户中断等待，继续执行...")

        # 检查当前状态
        current_url = page.url
        print(f"\n📍 当前 URL: {current_url}")

        if "login" in current_url or "signin" in current_url:
            print("\n⚠️  未检测到登录状态")
            print("   请手动在浏览器中登录，然后重新运行此脚本")
            print("   登录后 cookies 会被保存，下次可自动登录")

            # 保存当前状态截图
            screenshot_path = Path("screenshots/x_not_logged_in.png")
            page.screenshot(path=str(screenshot_path))
            print(f"📸 截图保存: {screenshot_path}")

            # 保持浏览器打开
            print("\n⏳ 浏览器将保持打开 60 秒供您登录...")
            time.sleep(60)

            return False
        else:
            print("\n✅ 检测到已登录状态")

            # 尝试发帖
            print("\n📤 尝试发布测试帖子...")

            try:
                # 查找推文输入框
                tweet_box = page.locator('div[role="textbox"][data-testid="tweetTextarea_0"]')
                tweet_box.wait_for(state="visible", timeout=10000)

                test_content = "🧪 AnimoCerebro Self-Promotion Agent Test\n\nAutomated posting test.\nGitHub: https://github.com/xunharry4-source/AnimoCerebro-external\n\n#AI #Test"

                print("   📝 填写内容...")
                tweet_box.fill(test_content)
                time.sleep(2)

                # 点击发布
                print("   🚀 点击发布...")
                post_button = page.locator('div[data-testid="tweetButton"]')
                post_button.wait_for(state="visible", timeout=5000)
                post_button.click()

                time.sleep(8)

                # 截图
                screenshot_path = Path("screenshots/x_post_attempt.png")
                page.screenshot(path=str(screenshot_path), full_page=True)
                print(f"   📸 截图: {screenshot_path}")

                print("\n✅ 发帖操作已执行")
                return True

            except Exception as e:
                print(f"   ⚠️  发帖失败: {e}")
                print("   请在浏览器中手动发帖")
                time.sleep(60)
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
            # 保存 cookies
            if context and page:
                try:
                    cookies = context.cookies()
                    cookies_file = Path("browser_sessions/x_cookies.json")
                    cookies_file.parent.mkdir(exist_ok=True)
                    with open(cookies_file, 'w') as f:
                        json.dump(cookies, f)
                    print(f"\n💾 Cookies 已保存到: {cookies_file}")
                except Exception as e:
                    print(f"⚠️  保存 cookies 失败: {e}")

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
        success = test_automated_posting()
        if success:
            print("\n✅ 测试完成")
        else:
            print("\n⚠️  需要手动登录")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
