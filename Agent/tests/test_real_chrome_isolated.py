#!/usr/bin/env python3
"""
启动独立的 Google Chrome 实例（不是 Chromium）

文件用途:
    使用系统的真实 Google Chrome 浏览器，但使用独立的用户数据目录。
    这样不会与用户正在使用的 Chrome 冲突。

特点:
    - 使用真实 Google Chrome（不是 Chromium）
    - 独立的用户数据目录（不干扰主 Chrome）
    - 看起来和真实 Chrome 完全一样
    - Playwright 可以控制
    - 测试结束后自动关闭
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
    print("  启动独立 Google Chrome 实例")
    print("=" * 80)

    # 创建独立的用户数据目录
    user_data_dir = Path("/tmp/chrome_isolated_test_profile")
    user_data_dir.mkdir(exist_ok=True)
    print(f"\n📂 独立用户数据目录: {user_data_dir}")
    print("   (不会影响您正在使用的 Chrome)")

    # 真实 Google Chrome 路径
    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    if not Path(chrome_path).exists():
        print(f"❌ Google Chrome 未找到: {chrome_path}")
        return False

    print(f"🌐 使用真实 Google Chrome: {chrome_path}")

    playwright = None
    context = None
    page = None

    try:
        print("\n🚀 启动 Playwright...")
        playwright = sync_playwright().start()

        print("🌐 启动独立 Google Chrome 实例...")
        print("   ⚠️  这个 Chrome 是独立的，不会影响您的 Chrome")

        # 使用真实 Google Chrome + 独立用户数据目录
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            executable_path=chrome_path,  # 真实 Google Chrome
            headless=False,
            slow_mo=500,
            viewport={"width": 1920, "height": 1080},
            args=[
                '--no-first-run',
                '--no-default-browser-check',
            ],
        )

        page = context.new_page()
        print("✅ 独立 Chrome 实例已启动")

        # 导航到 X.com
        print("\n📱 打开 X.com...")
        page.goto("https://x.com", wait_until="domcontentloaded", timeout=30000)
        print("✅ 页面已加载")

        print("\n" + "=" * 80)
        print("  📋 请在打开的 Chrome 窗口中登录")
        print("=" * 80)
        print("  • 这个 Chrome 是独立的，不影响您的 Chrome")
        print("  • 登录后按回车键继续")
        print("  • 测试结束后这个 Chrome 会自动关闭")
        print("=" * 80)

        input("\n登录后按回车键...")

        # 检查登录状态
        current_url = page.url
        print(f"\n📍 当前 URL: {current_url}")

        if "home" in current_url:
            print("✅ 已登录")

            # 发帖
            print("\n📤 发布测试帖子...")
            try:
                tweet_box = page.locator('div[role="textbox"][data-testid="tweetTextarea_0"]')
                tweet_box.wait_for(state="visible", timeout=10000)

                test_content = "🧪 AnimoCerebro Test\n\nAutomated test post.\n#AI #Test"

                print("   📝 填写...")
                tweet_box.fill(test_content)
                time.sleep(2)

                print("   🚀 发布...")
                post_button = page.locator('div[data-testid="tweetButton"]')
                post_button.click()
                time.sleep(8)

                # 截图
                screenshot_path = Path("screenshots/x_post_final.png")
                screenshot_path.parent.mkdir(exist_ok=True)
                page.screenshot(path=str(screenshot_path), full_page=True)
                print(f"   📸 截图: {screenshot_path.absolute()}")
                print("\n✅ 发帖完成!")

            except Exception as e:
                print(f"   ⚠️  失败: {e}")
        else:
            print("⚠️  未登录")

        print("\n⏳ 10 秒后关闭此 Chrome 实例...")
        time.sleep(10)
        return True

    except KeyboardInterrupt:
        print("\n\n⚠️  中断")
        return True
    except Exception as e:
        print(f"\n❌ 异常: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        try:
            print("\n🔒 关闭测试 Chrome...")
            if page:
                page.close()
            if context:
                context.close()
            if playwright:
                playwright.stop()
            print("✅ 测试 Chrome 已关闭（您的 Chrome 未受影响）")
        except:
            pass


if __name__ == "__main__":
    try:
        success = main()
        if success:
            print("\n✅ 完成")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
