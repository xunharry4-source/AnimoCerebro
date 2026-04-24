#!/usr/bin/env python3
"""
完全自动化发帖测试 - 使用真实 Google Chrome

文件用途:
    使用真实 Google Chrome + 独立用户数据目录
    自动完成登录和发帖，无需人工干预

方法:
    1. 如果 .env 中有 X_USERNAME/X_PASSWORD，自动登录
    2. 否则尝试加载保存的 cookies
    3. 自动发布测试帖子并截图
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


def main():
    print("\n" + "=" * 80)
    print("  完全自动化发帖测试")
    print("=" * 80)

    # 加载环境变量
    load_env()

    user_data_dir = Path("/tmp/chrome_auto_test_final")
    user_data_dir.mkdir(exist_ok=True)
    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    if not Path(chrome_path).exists():
        print(f"❌ Chrome 未找到")
        return False

    print(f"\n📂 独立目录: {user_data_dir}")
    print(f"🌐 Chrome: {chrome_path}")

    # 获取凭据
    x_username = os.environ.get("X_USERNAME", "")
    x_password = os.environ.get("X_PASSWORD", "")

    has_credentials = x_username and x_password and "your-" not in x_username

    if has_credentials:
        print("✅ 检测到 X 凭据")
    else:
        print("⚠️  未配置 X 凭据，将尝试使用 cookies")

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

        # 尝试加载 cookies
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
        print(f"📍 URL: {current_url}")

        # 检查是否已登录
        is_logged_in = "home" in current_url or "timeline" in current_url

        if not is_logged_in and has_credentials:
            print("\n🔐 自动登录...")
            try:
                # 点击登录按钮
                login_btn = page.locator('text=Sign in').first
                login_btn.wait_for(state="visible", timeout=10000)
                login_btn.click()
                time.sleep(2)

                # 输入用户名
                username_field = page.locator('input[autocomplete="username"]')
                username_field.wait_for(state="visible", timeout=10000)
                username_field.fill(x_username)
                time.sleep(1)

                # 点击下一步
                next_btn = page.locator('div[role="button"]:has-text("Next")').first
                next_btn.click()
                time.sleep(2)

                # 输入密码
                password_field = page.locator('input[type="password"]')
                password_field.wait_for(state="visible", timeout=10000)
                password_field.fill(x_password)
                time.sleep(1)

                # 点击登录
                login_submit = page.locator('div[role="button"]:has-text("Log in")').first
                login_submit.click()
                time.sleep(5)

                print("✅ 登录操作已完成")
                is_logged_in = True

            except Exception as e:
                print(f"⚠️  自动登录失败: {e}")
                is_logged_in = False

        if not is_logged_in:
            print("\n⚠️  未检测到登录状态")
            print("   请在 .env 中配置 X_USERNAME 和 X_PASSWORD")
            print("   或在浏览器中手动登录后重新运行")

            # 等待 60 秒供手动登录
            print("\n⏳ 等待 60 秒供手动登录...")
            time.sleep(60)

        # 发帖
        print("\n📤 发布测试帖子...")
        try:
            tweet_box = page.locator('div[role="textbox"][data-testid="tweetTextarea_0"]')
            tweet_box.wait_for(state="visible", timeout=15000)

            test_content = f"🧪 AnimoCerebro Self-Promotion Agent Test\n\nAutomated posting test from AI brain project.\nGitHub: https://github.com/xunharry4-source/AnimoCerebro-external\n\n#AI #MachineLearning #OpenSource #Test"

            print("   📝 填写内容...")
            tweet_box.fill(test_content)
            time.sleep(2)

            print("   🚀 点击发布...")
            post_button = page.locator('div[data-testid="tweetButton"]')
            post_button.wait_for(state="visible", timeout=10000)
            post_button.click()

            # 等待发布完成
            print("   ⏳ 等待发布...")
            time.sleep(10)

            # 截图
            screenshot_path = Path("screenshots/x_post_evidence.png")
            screenshot_path.parent.mkdir(exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"   📸 截图: {screenshot_path.absolute()}")

            print("\n✅ 发帖完成!")

            # 保存 cookies
            cookies = context.cookies()
            cookies_file.parent.mkdir(exist_ok=True)
            with open(cookies_file, 'w') as f:
                json.dump(cookies, f)
            print(f"   💾 Cookies 已保存")

        except Exception as e:
            print(f"   ⚠️  发帖失败: {e}")
            import traceback
            traceback.print_exc()

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
