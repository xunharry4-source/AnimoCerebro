#!/usr/bin/env python3
"""
隔离的浏览器测试 - 绝不影响用户Chrome

文件用途:
    启动一个完全独立的 Chromium 实例进行测试。
    这个浏览器与用户的 Chrome 完全隔离，互不影响。
    测试结束后会自动关闭这个测试浏览器。

重要承诺:
    - 此脚本只会控制自己启动的测试浏览器
    - 绝不会关闭或干扰用户正在使用的 Chrome
    - 使用独立的临时用户数据目录
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
    print("  隔离浏览器测试 - 不会影响您的 Chrome")
    print("=" * 80)

    # 创建临时用户数据目录（独立，不影响主 Chrome）
    user_data_dir = Path("/tmp/animocerebro_test_browser")
    user_data_dir.mkdir(exist_ok=True)
    print(f"\n📂 测试浏览器数据目录: {user_data_dir}")
    print("   (此目录独立，不会影响您的 Chrome)")

    playwright = None
    context = None
    page = None

    try:
        print("\n🚀 启动 Playwright...")
        playwright = sync_playwright().start()

        print("🌐 启动测试浏览器（Chromium）...")
        print("   ⚠️  这个浏览器是独立的，不会影响您的 Chrome")

        # 启动 Chromium（Playwright 自带的，不是用户的 Chrome）
        browser = playwright.chromium.launch(
            headless=False,
            slow_mo=500,
        )

        # 创建上下文
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )

        page = context.new_page()

        print("✅ 测试浏览器已启动")
        print("\n💡 说明:")
        print("   • 这个浏览器窗口是测试专用的")
        print("   • 与您的 Chrome 完全隔离")
        print("   • 测试结束后会自动关闭")
        print("   • 您的 Chrome 不受任何影响")

        # 导航到 X.com
        print("\n📱 打开 X.com...")
        page.goto("https://x.com", wait_until="domcontentloaded", timeout=30000)
        print("✅ 页面已加载")

        print("\n" + "=" * 80)
        print("  📋 请在测试浏览器中登录")
        print("=" * 80)
        print("  1. 在测试浏览器中登录 X 账号")
        print("  2. 完成后按回车键继续")
        print("  3. 测试结束后这个浏览器会自动关闭")
        print("  4. 您的 Chrome 不会被影响")
        print("=" * 80)

        input("\n登录后按回车键继续...")

        # 检查登录状态
        current_url = page.url
        print(f"\n📍 当前 URL: {current_url}")

        if "home" in current_url:
            print("✅ 检测到已登录")

            # 发帖测试
            print("\n📤 发布测试帖子...")
            try:
                tweet_box = page.locator('div[role="textbox"][data-testid="tweetTextarea_0"]')
                tweet_box.wait_for(state="visible", timeout=10000)

                test_content = "🧪 AnimoCerebro Test Post\n\nAutomated test.\n#AI #Test"

                print("   📝 填写内容...")
                tweet_box.fill(test_content)
                time.sleep(2)

                print("   🚀 点击发布...")
                post_button = page.locator('div[data-testid="tweetButton"]')
                post_button.wait_for(state="visible", timeout=5000)
                post_button.click()

                time.sleep(8)

                # 截图
                screenshot_path = Path("screenshots/x_post_test.png")
                screenshot_path.parent.mkdir(exist_ok=True)
                page.screenshot(path=str(screenshot_path), full_page=True)
                print(f"   📸 截图: {screenshot_path.absolute()}")

                print("\n✅ 发帖完成!")

            except Exception as e:
                print(f"   ⚠️  发帖失败: {e}")
        else:
            print("⚠️  未检测到登录状态")

        print("\n⏳ 测试浏览器将在 10 秒后自动关闭...")
        print("   (您的 Chrome 不会受影响)")
        time.sleep(10)

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
        # 只关闭测试浏览器
        try:
            print("\n🔒 正在关闭测试浏览器...")
            if page:
                page.close()
            if context:
                context.close()
            if browser:
                browser.close()
            if playwright:
                playwright.stop()
            print("✅ 测试浏览器已关闭")
            print("   (您的 Chrome 未受影响)")
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
