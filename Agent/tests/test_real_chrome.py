#!/usr/bin/env python3
"""
启动独立的 Google Chrome 实例进行发帖测试

文件用途:
    使用系统的 Google Chrome（不是 Chromium）启动一个独立实例，
    使用临时用户数据目录，与用户主 Chrome 完全隔离。

特点:
    - 使用真实 Google Chrome 浏览器
    - 独立的用户数据目录（不干扰主 Chrome）
    - 可以保留 cookies 和登录状态
    - Playwright 可以完全控制
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


def get_chrome_executable_path():
    """获取 macOS 上 Google Chrome 的可执行文件路径"""
    chrome_paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome",
        "/Applications/Google Chrome Dev.app/Contents/MacOS/Google Chrome",
    ]

    for path in chrome_paths:
        if Path(path).exists():
            return path

    raise FileNotFoundError("Google Chrome not found. Please install Google Chrome.")


def main():
    """主函数"""
    print("\n" + "=" * 80)
    print("  启动独立 Google Chrome 实例进行发帖测试")
    print("=" * 80)

    # 创建临时用户数据目录
    user_data_dir = Path("/tmp/chrome_profile_animocerebro_test")
    user_data_dir.mkdir(exist_ok=True)
    print(f"\n📂 用户数据目录: {user_data_dir}")
    print("   (此目录独立，不会影响您的主 Chrome)")

    # 获取 Chrome 可执行文件路径
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
        print("\n🚀 正在启动 Playwright...")
        playwright = sync_playwright().start()

        # 使用真实 Google Chrome 启动持久化上下文
        print("🌐 正在启动 Google Chrome（独立实例）...")
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            executable_path=chrome_path,  # 使用真实 Chrome
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
                '--disable-extensions',
            ],
            bypass_csp=True,
            ignore_default_args=['--enable-automation']
        )

        print("✅ Chrome 已启动")

        # 创建新页面
        print("📄 正在创建页面...")
        page = context.new_page()

        # 导航到 X.com
        print("\n📱 正在打开 X.com...")
        page.goto("https://x.com", wait_until="domcontentloaded", timeout=60000)
        print("✅ 页面已加载")

        print("\n" + "=" * 80)
        print("  💡 请在打开的 Chrome 窗口中登录 X 账号")
        print("=" * 80)
        print("  这个 Chrome 是独立的，不会影响您正在使用的 Chrome")
        print("  登录后，脚本会自动发布测试帖子")
        print("=" * 80)

        # 等待用户登录（最多 180 秒）
        print("\n⏳ 等待登录...（最多 180 秒）")
        login_timeout = 180
        start_time = time.time()
        logged_in = False

        while time.time() - start_time < login_timeout:
            current_url = page.url
            elapsed = int(time.time() - start_time)
            remaining = login_timeout - elapsed

            # 检查是否已登录
            if "login" not in current_url and "signin" not in current_url and "x.com/home" in current_url:
                print(f"\n✅ 检测到已登录！")
                logged_in = True
                break

            print(f"   剩余: {remaining}s | URL: {current_url[:50]}...", end='\r')
            time.sleep(2)

        if not logged_in:
            print("\n\n⚠️  未检测到登录，但仍将尝试发帖...")

        # 等待页面稳定
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
            print(f"  • Chrome 配置文件: {user_data_dir}")
            print("\n💡 提示:")
            print("  • 请在浏览器中确认帖子是否成功发布")
            print("  • 浏览器将保持打开 60 秒供您查看")
            print("  • 下次运行时，登录状态会被保留")

            # 保持浏览器打开
            print("\n⏳ 浏览器将在 60 秒后关闭...")
            time.sleep(60)

            return True

        except Exception as e:
            print(f"\n   ⚠️  自动发帖失败: {e}")
            import traceback
            traceback.print_exc()
            print("   请在浏览器中手动发帖")
            print("\n⏳ 浏览器将保持打开 120 秒供您操作...")
            time.sleep(120)
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
