#!/usr/bin/env python3
"""
浏览器登录测试 - 自动打开浏览器等待用户手动登录

文件用途:
    打开浏览器到 X.com 或 Reddit.com 的登录页面，
    让用户手动登录，然后测试发帖功能。

使用方法:
    1. 运行此脚本
    2. 在打开的浏览器中手动登录
    3. 登录后，脚本会自动发布测试帖子
"""

import sys
import time
from pathlib import Path

# 添加项目根目录和 src 目录到 Python 路径
project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(project_root))

from Agent.browser_automation import BrowserAutomationManager


def test_x_posting():
    """测试 X 发帖"""
    print("\n" + "=" * 80)
    print("  X (Twitter) 发帖测试")
    print("=" * 80)

    browser_manager = BrowserAutomationManager(headless=False, slow_mo=500)

    try:
        # 启动浏览器
        print("\n🚀 正在启动 Chromium 浏览器...")
        browser_manager.start_browser("chromium")
        print("✅ 浏览器已启动")

        # 导航到 X
        print("\n📱 正在打开 X.com...")
        browser_manager.page.goto("https://x.com", wait_until="networkidle", timeout=60000)
        print("💡 请在打开的浏览器窗口中手动登录 X 账号")
        print("   登录完成后，脚本将等待 60 秒...")

        # 等待用户登录
        for i in range(60, 0, -5):
            print(f"   ⏳ 剩余等待时间: {i} 秒...", end='\r')
            time.sleep(5)
        print("\n   ✅ 等待完成，开始发帖")

        # 发布测试帖子
        print("\n📤 正在发布测试帖子...")
        test_content = f"🧪 Testing AnimoCerebro Self-Promotion Agent\n\nAutomated test from AI brain project.\n\nGitHub: https://github.com/xunharry4-source/AnimoCerebro-external\n\n#AI #ML #OpenSource #Test"

        result = browser_manager.post_to_x(content=test_content)

        if result["success"]:
            print("\n✅ 发帖成功!")
            print(f"   消息: {result.get('message', 'N/A')}")
            if result.get("url"):
                print(f"   帖子链接: {result['url']}")

            # 截图作为证据
            screenshot_path = browser_manager.take_screenshot("x_post_success")
            if screenshot_path:
                print(f"   📸 截图保存: {screenshot_path}")

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
        print("\n🔍 浏览器将保持打开 30 秒...")
        time.sleep(30)
        try:
            browser_manager.stop_browser()
        except:
            pass


if __name__ == "__main__":
    try:
        success = test_x_posting()
        if success:
            print("\n" + "=" * 80)
            print("  ✅ 真实发帖测试完成!")
            print("=" * 80)
        else:
            print("\n⚠️  发帖未成功，请检查错误信息")
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
