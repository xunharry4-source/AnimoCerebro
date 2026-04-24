#!/usr/bin/env python3
"""
Reddit 发帖功能修复测试

测试新的选择器和 Shadow DOM 支持
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

def test_reddit_posting_fix():
    """测试修复后的 Reddit 发帖功能"""
    print("\n" + "="*80)
    print("🧪 Reddit 发帖功能修复测试")
    print("="*80)
    
    try:
        from playwright.sync_api import sync_playwright
        from Agent.browser_automation.test_auto_stealth_wait import STEALTH_JS, get_chrome_path
        from Agent.social_promotion.reddit_smart_poster import RedditSmartPoster
        from Agent.social_promotion.community_rules_manager import CommunityRulesManager
        
        # 启动浏览器
        print("\n1️⃣  启动浏览器...")
        user_data_dir = Path("./chrome_custom_profile").resolve()
        executable_path = get_chrome_path()
        
        playwright = sync_playwright().start()
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            executable_path=executable_path,
            headless=False,
            slow_mo=500,
        )
        
        context.add_init_script(STEALTH_JS)
        page = context.new_page()
        
        print("   ✅ 浏览器启动成功")
        
        # 确保已登录
        print("\n2️⃣  检查登录状态...")
        page.goto("https://www.reddit.com", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)
        
        if "login" in page.url.lower():
            print("   ⚠️  需要登录，请在打开的浏览器中登录")
            input("   按 Enter 继续...")
        
        print("   ✅ 已登录")
        
        # 创建发帖器
        rules_manager = CommunityRulesManager()
        poster = RedditSmartPoster(page, rules_manager)
        
        # 测试发帖
        print("\n3️⃣  测试发帖...")
        test_title = f"Test Post (Fixed) - {time.strftime('%Y-%m-%d %H:%M:%S')}"
        test_content = """
This is a test post with the fixed selectors.

Testing:
- Shadow DOM support
- Multiple selector fallback
- Keyboard simulation fallback

Please ignore this test.
"""
        
        print(f"   标题: {test_title}")
        print(f"   社区: r/AnimoCerebro")
        
        success = poster.post_custom_content(
            subreddit="AnimoCerebro",
            title=test_title,
            content=test_content,
            flair="Discussion",
            max_retries=2  # 增加重试次数
        )
        
        if success:
            print("\n✅ Reddit 发帖成功！")
        else:
            print("\n❌ Reddit 发帖失败")
            print("💡 请查看上面的错误信息和截图")
        
        # 清理
        print("\n4️⃣  关闭浏览器...")
        page.close()
        context.close()
        playwright.stop()
        
        return success
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "🎯"*40)
    print("Reddit 发帖修复测试")
    print("🎯"*40)
    
    success = test_reddit_posting_fix()
    
    if success:
        print("\n🎉 测试成功！")
    else:
        print("\n⚠️  测试失败，需要进一步调试")
    
    sys.exit(0 if success else 1)
