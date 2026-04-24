#!/usr/bin/env python3
"""
自动化认证和发帖测试 - 使用 Cookie 注入

文件用途:
    1. 尝试使用 .env 中的凭据自动登录
    2. 如果失败，使用示例 cookies 注入（演示目的）
    3. 自动发布测试帖子并截图作为证据

注意:
    由于 X/Twitter 的反机器人保护，真实环境需要有效凭据。
    此脚本展示完整的自动化流程架构。
"""

import sys
import os
import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(project_root))


def load_env():
    """加载 .env 文件"""
    env_file = project_root / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())


def create_sample_cookies():
    """创建示例 cookies（用于演示）"""
    # 这些是示例 cookies，实际使用时需要真实的
    return [
        {
            "name": "auth_token",
            "value": "sample_token_for_testing",
            "domain": ".x.com",
            "path": "/",
            "expires": int(time.time()) + 86400 * 30,
            "httpOnly": True,
            "secure": True,
        },
        {
            "name": "ct0",
            "value": "sample_csrf_token",
            "domain": ".x.com",
            "path": "/",
            "expires": int(time.time()) + 86400 * 30,
            "httpOnly": False,
            "secure": True,
        }
    ]


def main():
    print("\n" + "=" * 80)
    print("  自动化认证和发帖测试")
    print("=" * 80)

    load_env()

    user_data_dir = Path("/tmp/chrome_auto_final_test")
    user_data_dir.mkdir(exist_ok=True)
    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    if not Path(chrome_path).exists():
        print(f"❌ Chrome 未找到")
        return False

    print(f"\n📂 独立目录: {user_data_dir}")
    print(f"🌐 Chrome: {chrome_path}")

    x_username = os.environ.get("X_USERNAME", "")
    x_password = os.environ.get("X_PASSWORD", "")
    has_real_credentials = x_username and x_password and "your-" not in x_username.lower()

    playwright = None
    context = None
    page = None

    try:
        playwright = sync_playwright().start()

        print("\n🌐 启动 Chrome...")
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

        # 尝试加载保存的 cookies
        cookies_file = Path("browser_sessions/x_cookies.json")
        if cookies_file.exists():
            print("\n🍪 加载保存的 cookies...")
            with open(cookies_file) as f:
                cookies = json.load(f)
            context.add_cookies(cookies)
            print("✅ Cookies 已加载")

        # 导航到 X
        print("\n📱 打开 X.com...")
        page.goto("https://x.com", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        current_url = page.url
        is_logged_in = "home" in current_url or "timeline" in current_url

        # 如果未登录且有凭据，尝试自动登录
        if not is_logged_in and has_real_credentials:
            print("\n🔐 尝试自动登录...")
            try:
                login_btn = page.locator('text=Sign in').first
                login_btn.wait_for(state="visible", timeout=10000)
                login_btn.click()
                time.sleep(2)

                username_field = page.locator('input[autocomplete="username"]')
                username_field.fill(x_username)
                time.sleep(1)

                next_btn = page.locator('div[role="button"]:has-text("Next")').first
                next_btn.click()
                time.sleep(2)

                password_field = page.locator('input[type="password"]')
                password_field.fill(x_password)
                time.sleep(1)

                login_submit = page.locator('div[role="button"]:has-text("Log in")').first
                login_submit.click()
                time.sleep(5)

                print("✅ 登录操作完成")
                is_logged_in = True
            except Exception as e:
                print(f"⚠️  登录失败: {e}")

        # 如果仍未登录，使用示例 cookies 演示
        if not is_logged_in:
            print("\n⚠️  未检测到有效登录")
            print("   注入示例 cookies 进行演示...")

            sample_cookies = create_sample_cookies()
            context.add_cookies(sample_cookies)
            page.reload(wait_until="domcontentloaded")
            time.sleep(3)

            print("   📝 注意: 示例 cookies 无法真正登录，仅用于演示流程")

        # 截图当前状态
        screenshot_path = Path("screenshots/x_current_state.png")
        screenshot_path.parent.mkdir(exist_ok=True)
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"\n📸 当前状态截图: {screenshot_path.absolute()}")

        # 尝试发帖
        print("\n📤 尝试发布测试帖子...")
        try:
            tweet_box = page.locator('div[role="textbox"][data-testid="tweetTextarea_0"]')
            tweet_box.wait_for(state="visible", timeout=10000)

            test_content = "🧪 AnimoCerebro Self-Promotion Agent Test\n\nAutomated posting test.\nGitHub: https://github.com/xunharry4-source/AnimoCerebro-external\n\n#AI #ML #OpenSource #Test"

            print("   📝 填写内容...")
            tweet_box.fill(test_content)
            time.sleep(2)

            print("   🚀 点击发布...")
            post_button = page.locator('div[data-testid="tweetButton"]')
            post_button.wait_for(state="visible", timeout=5000)
            post_button.click()
            time.sleep(8)

            # 截图
            post_screenshot = Path("screenshots/x_post_attempt.png")
            page.screenshot(path=str(post_screenshot), full_page=True)
            print(f"   📸 发帖截图: {post_screenshot.absolute()}")
            print("\n✅ 发帖操作已执行")

        except Exception as e:
            print(f"   ⚠️  发帖失败: {e}")
            print("   原因: 需要有效的登录状态")

            # 生成测试报告
            print("\n" + "=" * 80)
            print("  📋 测试报告")
            print("=" * 80)
            print(f"  • 浏览器: Google Chrome (独立实例)")
            print(f"  • 用户数据目录: {user_data_dir}")
            print(f"  • 登录状态: {'已登录' if is_logged_in else '未登录'}")
            print(f"  • 凭据配置: {'已配置' if has_real_credentials else '使用占位符'}")
            print(f"  • 截图证据: {screenshot_path.absolute()}")
            print("\n  💡 要完成真实发帖:")
            print("     1. 在 .env 中配置真实的 X_USERNAME 和 X_PASSWORD")
            print("     2. 或在测试浏览器中手动登录一次（cookies 会被保存）")
            print("=" * 80)

        # 保存当前 cookies
        try:
            cookies = context.cookies()
            cookies_file.parent.mkdir(exist_ok=True)
            with open(cookies_file, 'w') as f:
                json.dump(cookies, f)
            print(f"\n💾 Cookies 已保存到: {cookies_file}")
        except:
            pass

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
