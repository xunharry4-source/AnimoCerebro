#!/usr/bin/env python3
"""
等待用户登录后自动发帖

流程:
1. 打开独立 Chrome 到 X.com
2. 等待用户手动登录（最多 300 秒）
3. 检测到登录后，自动发布测试帖子
4. 截图保存证据
5. 自动关闭浏览器
"""

import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(project_root))


def main():
    print("\n" + "=" * 80)
    print("  等待登录后自动发帖")
    print("=" * 80)

    user_data_dir = Path("/tmp/chrome_wait_login_test")
    user_data_dir.mkdir(exist_ok=True)
    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    if not Path(chrome_path).exists():
        print(f"❌ Chrome 未找到")
        return False

    print(f"\n📂 独立目录: {user_data_dir}")
    print("🌐 启动真实 Google Chrome...")

    playwright = None
    context = None
    page = None

    try:
        playwright = sync_playwright().start()

        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            executable_path=chrome_path,
            headless=False,
            slow_mo=500,
            viewport={"width": 1920, "height": 1080},
            args=['--no-first-run'],
        )

        page = context.new_page()
        print("✅ Chrome 已启动")

        # 打开 X.com
        print("\n📱 打开 X.com...")
        page.goto("https://x.com", wait_until="domcontentloaded", timeout=30000)
        print("✅ 页面已加载")

        print("\n" + "=" * 80)
        print("  📋 请在打开的 Chrome 中登录 X 账号")
        print("=" * 80)
        print("  • 这个 Chrome 是独立的，不影响您的 Chrome")
        print("  • 登录后脚本会自动检测并发布测试帖子")
        print("  • 最多等待 300 秒（5 分钟）")
        print("=" * 80)

        # 等待登录（最多 300 秒）
        print("\n⏳ 等待登录...")
        max_wait = 300
        start_time = time.time()
        logged_in = False

        while time.time() - start_time < max_wait:
            current_url = page.url
            elapsed = int(time.time() - start_time)
            remaining = max_wait - elapsed

            # 检查是否已登录
            if "home" in current_url or "timeline" in current_url:
                print(f"\n✅ 检测到已登录！URL: {current_url}")
                logged_in = True
                break

            print(f"   剩余 {remaining}s | URL: {current_url[:60]}...", end='\r')
            time.sleep(2)

        if not logged_in:
            print("\n\n❌ 超时：未在 300 秒内检测到登录")
            print("   请确认是否已完成登录")
            return False

        # 等待页面稳定
        time.sleep(3)

        # 自动发帖
        print("\n" + "=" * 80)
        print("  📤 开始自动发帖")
        print("=" * 80)

        try:
            # 查找推文输入框
            print("\n   📝 查找输入框...")
            tweet_box = page.locator('div[role="textbox"][data-testid="tweetTextarea_0"]')
            tweet_box.wait_for(state="visible", timeout=15000)
            print("   ✅ 找到输入框")

            # 填写内容
            test_content = "🧪 AnimoCerebro Self-Promotion Agent Test\n\nAutomated posting test from AI brain project.\nGitHub: https://github.com/xunharry4-source/AnimoCerebro-external\n\n#AI #MachineLearning #OpenSource #Test"

            print("   📝 填写内容...")
            tweet_box.fill(test_content)
            time.sleep(2)

            # 点击发布
            print("   🚀 点击发布按钮...")
            post_button = page.locator('div[data-testid="tweetButton"]')
            post_button.wait_for(state="visible", timeout=10000)
            post_button.click()

            # 等待发布完成
            print("   ⏳ 等待发布完成...")
            time.sleep(10)

            # 截图作为证据
            screenshot_path = Path("screenshots/x_post_SUCCESS_EVIDENCE.png")
            screenshot_path.parent.mkdir(exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"   📸 截图保存: {screenshot_path.absolute()}")

            print("\n" + "=" * 80)
            print("  ✅ 发帖成功！")
            print("=" * 80)
            print(f"\n📋 物理证据:")
            print(f"  • 截图: {screenshot_path.absolute()}")
            print(f"  • 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            print("\n💡 请在浏览器中确认帖子已成功发布")

        except Exception as e:
            print(f"\n   ❌ 发帖失败: {e}")
            import traceback
            traceback.print_exc()

            # 即使失败也截图
            screenshot_path = Path("screenshots/x_post_FAILED.png")
            screenshot_path.parent.mkdir(exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"   📸 失败截图: {screenshot_path.absolute()}")

        print("\n⏳ 浏览器将在 30 秒后关闭...")
        time.sleep(30)
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
            print("\n🔒 关闭测试 Chrome...")
            if page: page.close()
            if context: context.close()
            if playwright: playwright.stop()
            print("✅ 测试 Chrome 已关闭（您的 Chrome 未受影响）")
        except:
            pass


if __name__ == "__main__":
    try:
        success = main()
        if success:
            print("\n✅ 测试完成")
        else:
            print("\n❌ 测试未完成")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
