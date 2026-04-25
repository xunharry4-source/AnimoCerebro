#!/usr/bin/env python3
"""
完整的 Reddit 自动发帖测试 - 严格按照流程执行

文件用途:
    作为手动运行的 Reddit 完整发帖验证脚本，使用已登录的 Chrome profile
    打开 Reddit 发帖页、填写内容、选择 Flair 并提交。

主要职责:
    - 启动持久化 Chrome 上下文
    - 调用 RedditVisualRecognizer 选择 Flair
    - 调用 RedditVisualRecognizer 提交并验证发帖结果
    - 输出截图路径、帖子 URL 或明确失败原因

不负责:
    - 不管理 Reddit 账号登录和密码
    - 不绕过 CAPTCHA、风控或社区限制
    - 不在没有帖子 URL 证据时宣称发帖成功
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright
from Agent.reddit_visual_recognizer import RedditVisualRecognizer
from Agent.browser_automation.test_auto_stealth_wait import get_chrome_path, STEALTH_JS


TEST_SUBREDDIT = "AnimoCerebro"
TEST_TITLE = "Tesseract OCR 视觉识别测试"
TEST_BODY = "这是一个使用 Tesseract OCR 进行视觉识别和自动发帖的测试。"
TARGET_FLAIR = "不适合工作场合"


def test_complete_posting():
    """完整的发帖流程测试"""
    
    print("\n" + "="*80)
    print("🚀 Reddit 完整自动发帖测试")
    print("="*80)
    
    executable_path = get_chrome_path()
    user_data_dir = Path("./chrome_custom_profile").resolve()
    user_data_dir.mkdir(exist_ok=True)
    
    playwright = sync_playwright().start()
    
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(user_data_dir),
        executable_path=executable_path,
        headless=False,
        slow_mo=500,
        viewport={"width": 1920, "height": 1080},
        args=[
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
        ],
    )
    
    context.add_init_script(STEALTH_JS)
    page = context.pages[0]
    
    try:
        # 初始化识别器
        print("\n🤖 初始化视觉识别器...")
        recognizer = RedditVisualRecognizer(page)
        
        # Step 1: 访问发帖页面
        print("\n📝 Step 1: 访问发帖页面...")
        page.goto(f"https://www.reddit.com/r/{TEST_SUBREDDIT}/submit",
                 wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        
        # Step 2: 填写标题
        print("\n📝 Step 2: 填写标题...")
        title_input = page.locator('textarea[name="title"]').first
        if title_input.count() > 0:
            title_input.fill(TEST_TITLE)
            print("   ✅ 标题已填写")
        else:
            print("   ❌ 未找到标题输入框")
            return False
        
        # Step 3: 填写内容
        print("\n📝 Step 3: 填写内容...")
        composer = page.locator('shreddit-composer').first
        if composer.count() > 0:
            composer.click()
            page.wait_for_timeout(1000)
            page.keyboard.type(TEST_BODY, delay=30)
            print("   ✅ 内容已填写")
        else:
            print("   ❌ 未找到内容编辑器")
            return False
        
        # Step 4: 选择 Flair
        print("\n🏷️  Step 4: 选择 Flair...")
        flair_success = recognizer.recognize_and_select_flair(
            target_flair=TARGET_FLAIR,
            max_attempts=1
        )
        
        if flair_success:
            print("   ✅ Flair 选择成功")
        else:
            print("   ❌ Flair 选择失败，停止发帖")
            return False
        
        # Step 5: 提交并验证。只接受 Reddit 帖子 URL 作为成功证据。
        print("\n🖱️  Step 5: 提交并验证发帖结果...")
        result = recognizer.submit_post_and_verify(
            subreddit=TEST_SUBREDDIT,
            wait_time=20,
            title=TEST_TITLE,
            content=TEST_BODY,
            target_flair=TARGET_FLAIR,
            max_retries=2
        )

        if result["success"]:
            print("\n✅✅✅ 发帖成功！")
            print(f"   帖子 URL: {result['post_url']}")
            print(f"   截图证据: {result.get('screenshot_path')}")
        else:
            print("\n❌ 发帖失败或未验证")
            print(f"   状态: {result.get('status')}")
            print(f"   原因: {result.get('error_message')}")
            print(f"   点击结果: {result.get('click')}")
            print(f"   截图证据: {result.get('screenshot_path')}")
        
        print("\n" + "="*80)
        print("测试完成")
        print("="*80)
        return result["success"]
        
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        print("\n🧹 清理资源...")
        context.close()
        playwright.stop()
        print("✅ 完成")


if __name__ == "__main__":
    test_complete_posting()
